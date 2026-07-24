import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { getStoredToken } from "../auth/AuthContext";
import {
  startPcmToWebSocket,
  type PcmStreamOptions,
} from "../audio/pcmStream";
import type {
  SessionAction,
  SessionState,
  WarningKind,
  WsMessage,
} from "../types";

// ─── State machine ───────────────────────────────────────────────────────────

const MAX_MESSAGES = 250;

// Mirrors the order documented on WarningKind: higher wins. A lower-priority
// source can never bump a still-active higher one off the banner, and can
// only clear the banner if it's the one that put its own message there.
const WARNING_PRIORITY: Record<WarningKind, number> = {
  mic: 1,
  deepgram: 2,
  tab_share: 3,
};

const initialState: SessionState = {
  status: "idle",
  error: null,
  warning: null,
  warningKind: null,
  messages: [],
  sessionId: null,
  lastEndedSessionId: null,
  startedAt: null,
  speakers: [],
  leadSpeakerId: null,
};

function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case "CONNECTING":
      return { ...initialState, status: "connecting" };
    case "LIVE":
      return {
        ...state,
        status: "live",
        sessionId: action.sessionId ?? state.sessionId,
        startedAt: Date.now(),
        error: null,
      };
    case "MESSAGE": {
      const messages = appendMessage(state.messages, action.payload).slice(-MAX_MESSAGES);
      const sessionId =
        action.payload.session_id ?? state.sessionId;
      return { ...state, messages, sessionId };
    }
    case "SESSION_STATUS":
      return {
        ...state,
        speakers: action.payload.speakers,
        leadSpeakerId: action.payload.lead_speaker_id,
      };
    case "ERROR":
      return { ...state, status: "error", error: action.error };
    case "WARNING": {
      const { warning, kind } = action;
      if (warning === null) {
        // Only the source that's currently showing may clear it — otherwise
        // a resolved mic-silence check could wipe out an unrelated, still-
        // active "tab share stopped" or "Deepgram reconnecting" warning.
        if (state.warningKind !== kind) return state;
        return { ...state, warning: null, warningKind: null };
      }
      if (state.warningKind && WARNING_PRIORITY[state.warningKind] > WARNING_PRIORITY[kind]) {
        return state;
      }
      return { ...state, warning, warningKind: kind };
    }
    case "DISCONNECT":
      return {
        ...initialState,
        lastEndedSessionId: state.sessionId ?? state.lastEndedSessionId,
      };
    default:
      return state;
  }
}

function appendMessage(messages: WsMessage[], payload: WsMessage): WsMessage[] {
  const next = [...messages];
  const last = next.at(-1);

  if (
    payload.type === "transcript_partial" &&
    last?.type === "transcript_partial"
  ) {
    next[next.length - 1] = payload;
    return next;
  }

  if (
    payload.type === "answer_delta" &&
    last?.type === "answer_delta" &&
    last.generation_id === payload.generation_id
  ) {
    next[next.length - 1] = payload;
    return next;
  }

  next.push(payload);
  return next;
}

// ─── WS URL builder ──────────────────────────────────────────────────────────

// Credentials are NEVER put in the URL (URLs land in server access logs).
// Auth is sent as the first WebSocket message instead — see connect().
function buildWsUrl(): string {
  const path = import.meta.env.VITE_WS_PATH || "/ws/realtime";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export type ConnectOptions = PcmStreamOptions & {
  /** Deepgram call-language mode ("multi" | "mr" | "gu" | "ta" | "te" | "kn" | "bn"). Defaults to "multi" server-side. */
  language?: string;
};

export interface AssistantWsApi {
  status: SessionState["status"];
  error: string | null;
  warning: string | null;
  messages: WsMessage[];
  sessionId: string | null;
  lastEndedSessionId: string | null;
  elapsedSeconds: number;
  speakers: number[];
  leadSpeakerId: number | null;
  connect: (apiKey: string, options?: ConnectOptions) => Promise<void>;
  disconnect: () => void;
}

export function useAssistantWs(): AssistantWsApi {
  const [state, dispatch] = useReducer(sessionReducer, initialState);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const stopPcmRef = useRef<(() => void) | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Session timer
  useEffect(() => {
    if (state.status === "live" && state.startedAt !== null) {
      timerRef.current = setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - state.startedAt!) / 1000));
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      setElapsedSeconds(0);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [state.status, state.startedAt]);

  const teardown = useCallback(() => {
    stopPcmRef.current?.();
    stopPcmRef.current = null;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    teardown();
    dispatch({ type: "DISCONNECT" });
  }, [teardown]);

  const connect = useCallback(
    async (apiKey: string, options?: ConnectOptions) => {
      teardown();
      dispatch({ type: "CONNECTING" });

      const ws = new WebSocket(buildWsUrl());
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      // Auth must be the FIRST message on the socket — the server waits for it
      // before starting the session (and ignores everything else until then).
      ws.onopen = () => {
        const token = getStoredToken();
        const auth = token ? { token } : { api_key: apiKey.trim() };
        ws.send(JSON.stringify({ type: "auth", ...auth, language: options?.language }));
      };

      ws.onmessage = (ev) => {
        try {
          const raw =
            typeof ev.data === "string"
              ? ev.data
              : new TextDecoder().decode(ev.data as ArrayBuffer);
          const data = JSON.parse(raw) as Record<string, unknown>;
          const t = data.type;
          if (t === "session_started" && typeof data.session_id === "string") {
            dispatch({ type: "LIVE", sessionId: data.session_id });
            return;
          }
          if (t === "session_status") {
            dispatch({
              type: "SESSION_STATUS",
              payload: {
                speakers: (data.speakers as number[]) ?? [],
                lead_speaker_id:
                  (data.lead_speaker_id as number | null | undefined) ?? null,
              },
            });
            return;
          }
          if (t === "warning") {
            const kind: WarningKind =
              data.kind === "mic" || data.kind === "tab_share" ? data.kind : "deepgram";
            dispatch({
              type: "WARNING",
              warning: typeof data.message === "string" ? data.message : null,
              kind,
            });
            return;
          }
          if (
            t === "transcript_partial" ||
            t === "transcript_final" ||
            t === "answer_started" ||
            t === "answer_delta" ||
            t === "answer_done" ||
            t === "answer_cancelled" ||
            t === "error"
          ) {
            dispatch({
              type: "MESSAGE",
              payload: data as unknown as WsMessage,
            });
          }
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.onclose = () => {
        stopPcmRef.current?.();
        stopPcmRef.current = null;
        dispatch({ type: "DISCONNECT" });
      };

      // PCM must start getUserMedia + AudioContext.resume before waiting for WS open;
      // otherwise Chrome can expire the user gesture and the graph stays silent (Deepgram net0001).
      try {
        const { stop } = await startPcmToWebSocket(
          ws,
          (err) => dispatch({ type: "ERROR", error: err.message }),
          (message, kind) => dispatch({ type: "WARNING", warning: message, kind }),
          { captureTabAudio: options?.captureTabAudio === true }
        );
        stopPcmRef.current = stop;
        dispatch({ type: "LIVE" });
      } catch (e) {
        dispatch({
          type: "ERROR",
          error: e instanceof Error ? e.message : "Microphone access failed",
        });
        ws.close();
      }
    },
    [teardown]
  );

  return {
    status: state.status,
    error: state.error,
    warning: state.warning,
    messages: state.messages,
    sessionId: state.sessionId,
    lastEndedSessionId: state.lastEndedSessionId,
    elapsedSeconds,
    speakers: state.speakers,
    leadSpeakerId: state.leadSpeakerId,
    connect,
    disconnect,
  };
}
