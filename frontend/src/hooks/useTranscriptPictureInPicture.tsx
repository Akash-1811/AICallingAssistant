import { useCallback, useEffect, useRef, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import pipCssUrl from "../pip/transcriptPip.css?url";
import { TranscriptPipRoot } from "../pip/TranscriptPipRoot";
import type { WsMessage } from "../types";

function isDocumentPipSupported(): boolean {
  return typeof window !== "undefined" && "documentPictureInPicture" in window && !!window.documentPictureInPicture;
}

export function useTranscriptPictureInPicture(options: {
  /** Call is live — PiP closes automatically when false. */
  active: boolean;
  messages: WsMessage[];
  elapsedLabel: string;
}) {
  const { active, messages, elapsedLabel } = options;

  const optsRef = useRef(options);
  optsRef.current = options;

  const rootRef = useRef<Root | null>(null);
  const pipWindowRef = useRef<Window | null>(null);
  const [pipOpen, setPipOpen] = useState(false);

  const syncFromPipClose = useCallback(() => {
    try {
      rootRef.current?.unmount();
    } catch {
      /* ignore */
    }
    rootRef.current = null;
    pipWindowRef.current = null;
    setPipOpen(false);
  }, []);

  const closePip = useCallback(() => {
    const w = pipWindowRef.current;
    try {
      rootRef.current?.unmount();
    } catch {
      /* ignore */
    }
    rootRef.current = null;
    pipWindowRef.current = null;
    if (w && !w.closed) {
      try {
        w.close();
      } catch {
        /* ignore */
      }
    }
    setPipOpen(false);
  }, []);

  const openPip = useCallback(async () => {
    if (!isDocumentPipSupported()) return;

    if (pipWindowRef.current && !pipWindowRef.current.closed) {
      pipWindowRef.current.focus();
      return;
    }

    const pipApi = window.documentPictureInPicture!;
    const pipWin = await pipApi.requestWindow({ width: 400, height: 560 });
    pipWindowRef.current = pipWin;

    const doc = pipWin.document;
    const link = doc.createElement("link");
    link.rel = "stylesheet";
    link.href = pipCssUrl;
    doc.head.appendChild(link);

    doc.documentElement.lang = "en";
    doc.body.style.margin = "0";
    doc.body.style.minHeight = "100vh";

    const mount = doc.createElement("div");
    mount.id = "pip-react-root";
    doc.body.appendChild(mount);

    const { messages: m0, elapsedLabel: e0 } = optsRef.current;
    const root = createRoot(mount);
    rootRef.current = root;
    root.render(<TranscriptPipRoot messages={m0} elapsedLabel={e0} />);
    setPipOpen(true);

    pipWin.addEventListener(
      "pagehide",
      () => {
        syncFromPipClose();
      },
      { once: true }
    );
  }, [syncFromPipClose]);

  useEffect(() => {
    if (!pipOpen || !rootRef.current) return;
    const w = pipWindowRef.current;
    if (!w || w.closed) return;
    rootRef.current.render(<TranscriptPipRoot messages={messages} elapsedLabel={elapsedLabel} />);
  }, [messages, elapsedLabel, pipOpen]);

  useEffect(() => {
    if (!active && pipOpen) {
      closePip();
    }
  }, [active, pipOpen, closePip]);

  useEffect(() => {
    return () => {
      closePip();
    };
  }, [closePip]);

  return {
    pipSupported: isDocumentPipSupported(),
    pipOpen,
    openPip,
    closePip,
  };
}
