/**
 * Captures call audio as interleaved stereo linear16 PCM @ 16 kHz for Deepgram
 * multichannel streaming:
 *
 *   channel 0 = microphone (the rep) · channel 1 = meeting-tab audio (the customer)
 *
 * Channel identity is how the backend tells rep and customer apart — the two
 * streams are never mixed. Without a tab share, channel 1 is silence and the
 * backend treats the mic as the active speaker.
 *
 * Uses an AudioWorklet: ScriptProcessorNode is deprecated and gets throttled in
 * background tabs, which starved Deepgram of audio mid-call (net0001).
 */

const TARGET_RATE = 16000;

/**
 * Runs on the audio rendering thread. Buffers ~43 ms of the merger's stereo
 * output (plane 0 = mic, plane 1 = tab) and posts both planes to the main thread.
 */
const WORKLET_SOURCE = `
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunkFrames = 2048;
    this.mic = new Float32Array(this.chunkFrames);
    this.tab = new Float32Array(this.chunkFrames);
    this.filled = 0;
  }
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const mic = input[0];
    const tab = input[1];
    let offset = 0;
    while (offset < mic.length) {
      const n = Math.min(mic.length - offset, this.chunkFrames - this.filled);
      this.mic.set(mic.subarray(offset, offset + n), this.filled);
      if (tab) this.tab.set(tab.subarray(offset, offset + n), this.filled);
      this.filled += n;
      offset += n;
      if (this.filled === this.chunkFrames) {
        this.port.postMessage({ mic: this.mic, tab: this.tab });
        this.mic = new Float32Array(this.chunkFrames);
        this.tab = new Float32Array(this.chunkFrames);
        this.filled = 0;
      }
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCaptureProcessor);
`;

export type PcmStreamOptions = {
  /**
   * When true, prompts for a screen/tab share and sends tab audio on channel 1.
   * For Google Meet: choose the **Meet tab** (not "Entire screen") and enable
   * "Share tab audio".
   */
  captureTabAudio?: boolean;
};

export type PcmStreamHandle = {
  stop: () => void;
};

function resampleLinear(
  input: Float32Array,
  inRate: number,
  outRate: number
): Float32Array {
  if (inRate === outRate) {
    return input;
  }
  const ratio = inRate / outRate;
  const outLen = Math.max(1, Math.floor(input.length / ratio));
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const src = i * ratio;
    const i0 = Math.floor(src);
    const frac = src - i0;
    const a = input[i0] ?? 0;
    const b = input[i0 + 1] ?? a;
    out[i] = a * (1 - frac) + b * frac;
  }
  return out;
}

/** Interleave two mono channels into stereo int16 LE: [mic, tab, mic, tab, …]. */
function interleave16(mic: Float32Array, tab: Float32Array): ArrayBuffer {
  const frames = Math.min(mic.length, tab.length);
  const view = new DataView(new ArrayBuffer(frames * 4));
  for (let i = 0; i < frames; i++) {
    const m = Math.max(-1, Math.min(1, mic[i]));
    const t = Math.max(-1, Math.min(1, tab[i]));
    view.setInt16(i * 4, m < 0 ? m * 0x8000 : m * 0x7fff, true);
    view.setInt16(i * 4 + 2, t < 0 ? t * 0x8000 : t * 0x7fff, true);
  }
  return view.buffer;
}

/**
 * Resolves when the socket is OPEN. If the caller already awaited network round-trips
 * before getUserMedia, Chrome may drop user-gesture activation and the AudioContext
 * stays suspended — so we wait for WS *after* mic/tab capture, not before.
 */
function waitForWebSocketOpen(ws: WebSocket): Promise<void> {
  if (ws.readyState === WebSocket.OPEN) return Promise.resolve();
  if (
    ws.readyState === WebSocket.CLOSING ||
    ws.readyState === WebSocket.CLOSED
  ) {
    return Promise.reject(new Error("WebSocket is closed"));
  }
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      ws.removeEventListener("open", onOpen);
      ws.removeEventListener("error", onError);
      ws.removeEventListener("close", onClose);
    };
    const onOpen = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("WebSocket failed"));
    };
    const onClose = () => {
      cleanup();
      reject(new Error("WebSocket closed before open"));
    };
    ws.addEventListener("open", onOpen);
    ws.addEventListener("error", onError);
    ws.addEventListener("close", onClose);
  });
}

/**
 * Start streaming stereo PCM chunks to a WebSocket (binary). Mic/tab capture and
 * AudioContext.resume run before waiting for `open`, so the click gesture
 * is still valid in Chrome.
 */
export async function startPcmToWebSocket(
  ws: WebSocket,
  onError?: (err: Error) => void,
  options?: PcmStreamOptions
): Promise<PcmStreamHandle> {
  // Browsers require a secure context for mic + tab capture.
  // `http://localhost` is treated as secure, but `http://<IP>` is not.
  if (!window.isSecureContext) {
    throw new Error(
      "Live call requires HTTPS (secure context). Open the app over https:// with a real domain (recommended), or use a secure tunnel. HTTP on a public IP is blocked by the browser for microphone/tab audio."
    );
  }
  const audioCtx = new AudioContext();
  await audioCtx.resume();

  /**
   * Mic first so permission + capture path starts before the (slow) share dialog;
   * avoids long gaps with zero bytes to Deepgram after WS connect.
   */
  const micStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
  });

  let displayStream: MediaStream | null = null;

  const abort = (message: string): Error => {
    micStream.getTracks().forEach((t) => t.stop());
    displayStream?.getTracks().forEach((t) => t.stop());
    void audioCtx.close();
    return new Error(message);
  };

  if (options?.captureTabAudio) {
    if (!navigator.mediaDevices.getDisplayMedia) {
      throw abort(
        "This browser cannot capture tab audio. Use Chrome or Edge, or use a virtual audio cable."
      );
    }
    try {
      displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: true,
      });
    } catch (e) {
      throw abort(
        e instanceof DOMException && e.name === "NotAllowedError"
          ? "Screen/tab share was blocked or cancelled — allow sharing to capture meeting audio."
          : e instanceof Error
            ? e.message
            : "Could not capture tab."
      );
    }
    if (!displayStream.getAudioTracks().length) {
      throw abort(
        'No tab audio. Pick the **Chrome tab** that has Meet/Zoom (not "Entire screen" unless you know it carries tab audio), and enable "Share tab audio".'
      );
    }
  }

  try {
    await waitForWebSocketOpen(ws);
  } catch (e) {
    throw abort(e instanceof Error ? e.message : String(e));
  }

  try {
    const workletUrl = URL.createObjectURL(
      new Blob([WORKLET_SOURCE], { type: "application/javascript" })
    );
    await audioCtx.audioWorklet.addModule(workletUrl);
    URL.revokeObjectURL(workletUrl);
  } catch (e) {
    throw abort(e instanceof Error ? e.message : "AudioWorklet failed to load");
  }

  // Mic → merger input 0, tab → merger input 1. Each source is forced mono
  // first so a stereo tab track cannot bleed across channels. An unconnected
  // merger input outputs silence, so mic-only sessions still produce stereo.
  const merger = audioCtx.createChannelMerger(2);
  const toMono = (stream: MediaStream, mergerInput: number) => {
    const source = audioCtx.createMediaStreamSource(stream);
    const mono = new GainNode(audioCtx, {
      channelCount: 1,
      channelCountMode: "explicit",
      channelInterpretation: "speakers",
    });
    source.connect(mono);
    mono.connect(merger, 0, mergerInput);
    return () => {
      source.disconnect();
      mono.disconnect();
    };
  };

  const disconnectGraph: Array<() => void> = [];
  disconnectGraph.push(toMono(micStream, 0));
  if (displayStream) {
    disconnectGraph.push(
      toMono(new MediaStream(displayStream.getAudioTracks()), 1)
    );
  }

  const capture = new AudioWorkletNode(audioCtx, "pcm-capture", {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [1],
    channelCount: 2,
    channelCountMode: "explicit",
    channelInterpretation: "discrete",
  });
  const mute = new GainNode(audioCtx, { gain: 0 });

  // If the mic channel stays flat for ~5s of chunks, the graph is broken or the
  // mic is muted — tell the rep instead of leaving an empty transcript.
  let silentChunks = 0;
  let silenceReported = false;

  capture.port.onmessage = (ev: MessageEvent<{ mic: Float32Array; tab: Float32Array }>) => {
    if (ws.readyState !== WebSocket.OPEN) return;
    try {
      if (!silenceReported) {
        const peak = ev.data.mic.reduce((m, v) => Math.max(m, Math.abs(v)), 0);
        silentChunks = peak < 0.001 ? silentChunks + 1 : 0;
        if (silentChunks >= 120) {
          silenceReported = true;
          onError?.(
            new Error(
              "No microphone signal detected — check that the mic is not muted and the right input device is selected."
            )
          );
        }
      }
      const mic = resampleLinear(ev.data.mic, audioCtx.sampleRate, TARGET_RATE);
      const tab = resampleLinear(ev.data.tab, audioCtx.sampleRate, TARGET_RATE);
      ws.send(interleave16(mic, tab));
    } catch (e) {
      onError?.(e instanceof Error ? e : new Error(String(e)));
    }
  };

  merger.connect(capture);
  capture.connect(mute);
  mute.connect(audioCtx.destination);

  await audioCtx.resume();

  const resumeIfSuspended = () => {
    if (audioCtx.state === "suspended") {
      void audioCtx.resume().catch(() => {});
    }
  };
  const onVisibility = () => {
    if (document.visibilityState === "visible") resumeIfSuspended();
  };
  document.addEventListener("visibilitychange", onVisibility);
  audioCtx.addEventListener("statechange", resumeIfSuspended);

  const stop = () => {
    capture.port.onmessage = null;
    try {
      merger.disconnect();
      capture.disconnect();
      mute.disconnect();
      disconnectGraph.forEach((fn) => {
        try {
          fn();
        } catch {
          /* ignore */
        }
      });
    } catch {
      /* ignore */
    }
    micStream.getTracks().forEach((t) => t.stop());
    displayStream?.getTracks().forEach((t) => t.stop());
    document.removeEventListener("visibilitychange", onVisibility);
    audioCtx.removeEventListener("statechange", resumeIfSuspended);
    void audioCtx.close();
  };

  return { stop };
}
