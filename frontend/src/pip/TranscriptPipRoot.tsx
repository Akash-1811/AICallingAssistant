import { useEffect, useRef } from "react";
import type { WsMessage } from "../types";
import { buildRealtimeView, speakerLabel } from "../realtime";
import { HighlightedText } from "../components/HighlightedText";

interface Props {
  messages: WsMessage[];
  elapsedLabel: string;
}

export function TranscriptPipRoot({ messages, elapsedLabel }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const { transcriptTimeline, livePartial, liveAnswer } = buildRealtimeView(messages);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, transcriptTimeline.length, livePartial?.text, liveAnswer?.text]);

  return (
    <div className="pip-wrap">
      <header className="pip-header">
        <h1 className="pip-title">Transcript</h1>
        <span className="pip-live" aria-live="polite">
          Live · {elapsedLabel}
        </span>
      </header>

      <div className="pip-panel">
        <div className="pip-feed" role="log" aria-live="polite" aria-label="Floating transcript">
          {transcriptTimeline.length === 0 && !livePartial && !liveAnswer ? (
            <div className="pip-empty">
              <span aria-hidden="true">{"\u{1F3A4}"}</span>
              <span>Transcript and suggested replies will appear as the call progresses.</span>
            </div>
          ) : (
            <>
              {transcriptTimeline.map((item, i) => {
                if (item.kind === "speaker") {
                  return (
                    <div key={item.id} className="pip-turn">
                      <div className="pip-prospect-row">
                        <div className="pip-prospect-bubble">
                          <p className="pip-role">{speakerLabel(item.speaker)}</p>
                          <p className="pip-bubble-text">{item.text}</p>
                          <p className="pip-bubble-time">Turn {i + 1}</p>
                        </div>
                      </div>
                    </div>
                  );
                }
                if (item.kind === "assistant") {
                  return (
                    <div key={item.id} className="pip-turn">
                      <div className="pip-agent-row">
                        <div className="pip-agent-bubble">
                          <p className="pip-role-light">Suggested response</p>
                          <p className="pip-bubble-text-light">
                            <HighlightedText text={item.text} variant="onAccent" markClassName="pip-value-mark" />
                          </p>
                          <p className="pip-bubble-time-light">
                            AI · {item.fromCache ? "cached" : "generated"}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={item.id} className="pip-error">
                    <WarningIcon />
                    {item.text}
                  </div>
                );
              })}

              {livePartial && (
                <div className="pip-turn">
                  <div className="pip-prospect-row">
                    <div className="pip-prospect-bubble">
                      <p className="pip-role">
                        {typeof livePartial.speaker === "number"
                          ? speakerLabel(livePartial.speaker)
                          : "Listening"}
                      </p>
                      <p className="pip-bubble-text">{livePartial.text}</p>
                      <p className="pip-bubble-time">Live transcript…</p>
                    </div>
                  </div>
                </div>
              )}

              {liveAnswer && (
                <div className="pip-turn">
                  <div className="pip-agent-row">
                    <div className="pip-agent-bubble">
                      <p className="pip-role-light">Suggested response</p>
                      <p className="pip-bubble-text-light">
                        <HighlightedText
                          text={liveAnswer.text || "Thinking…"}
                          variant="onAccent"
                          markClassName="pip-value-mark"
                        />
                      </p>
                      <p className="pip-bubble-time-light">AI · streaming</p>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <p className="pip-footer">
        AI Calling Assistant · drag to reposition · close window to return here
      </p>
    </div>
  );
}

function WarningIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}
