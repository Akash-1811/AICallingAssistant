import { useEffect, useRef } from "react";
import type { WsMessage } from "../types";
import { buildRealtimeView, speakerLabel } from "../realtime";
import { CopyButton } from "./CopyButton";
import { HighlightedText } from "./HighlightedText";
import styles from "./TranscriptFeed.module.css";

interface Props {
  messages: WsMessage[];
}

export function TranscriptFeed({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const { transcriptTimeline, livePartial, liveAnswer } = buildRealtimeView(messages);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, transcriptTimeline.length, livePartial?.text, liveAnswer?.text]);

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.titleRow}>
          <h2 className={styles.title}>Transcript</h2>
        </div>
        {(transcriptTimeline.length > 0 || livePartial || liveAnswer) && (
          <button
            type="button"
            className={styles.autoScroll}
            onClick={() => bottomRef.current?.scrollIntoView({ behavior: "smooth" })}
          >
            <span className={styles.autoScrollDot} aria-hidden="true" />
            Live scroll
          </button>
        )}
      </div>

      <div className={styles.feed} role="log" aria-live="polite" aria-label="Live call transcript">
        {transcriptTimeline.length === 0 && !livePartial && !liveAnswer ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon} aria-hidden="true">
              {"\u{1F3A4}"}
            </span>
            <span>Transcript and suggested lines will appear as the conversation progresses.</span>
          </div>
        ) : (
          <>
            {transcriptTimeline.map((item, i) => {
              if (item.kind === "speaker") {
                const label = speakerLabel(item.speaker);
                return (
                  <div key={item.id} className={styles.turn}>
                    <div className={styles.prospectRow}>
                      <div className={styles.prospectBubble}>
                        <p className={styles.roleTag}>{label}</p>
                        <p className={styles.bubbleText}>{item.text}</p>
                        <p className={styles.bubbleTime}>Turn {i + 1}</p>
                        <span className={styles.copyWrap}>
                          <CopyButton text={item.text} label={`Copy ${label} line`} />
                        </span>
                      </div>
                    </div>
                  </div>
                );
              }

              if (item.kind === "assistant") {
                return (
                  <div key={item.id} className={styles.turn}>
                    <div className={styles.agentRow}>
                      <div className={styles.agentBubble}>
                        <p className={styles.roleTagLight}>Suggested response</p>
                        {item.error && (
                          <div className={styles.errorRow}>
                            <WarningIcon />
                            {item.error}
                          </div>
                        )}
                        <p className={styles.bubbleTextLight}>
                          <HighlightedText text={item.text} variant="onAccent" />
                        </p>
                        <p className={styles.bubbleTimeLight}>
                          AI · {item.fromCache ? "cached" : "generated"}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              }

              return (
                <div key={item.id} className={styles.errorRow}>
                  <WarningIcon />
                  {item.text}
                </div>
              );
            })}

            {livePartial && (
              <div className={styles.turn}>
                <div className={styles.prospectRow}>
                  <div className={styles.prospectBubble}>
                    <p className={styles.roleTag}>
                      {typeof livePartial.speaker === "number"
                        ? speakerLabel(livePartial.speaker)
                        : "Listening"}
                    </p>
                    <p className={styles.bubbleText}>{livePartial.text}</p>
                    <p className={styles.bubbleTime}>Live transcript…</p>
                  </div>
                </div>
              </div>
            )}

            {liveAnswer && (
              <div className={styles.turn}>
                <div className={styles.agentRow}>
                  <div className={styles.agentBubble}>
                    <p className={styles.roleTagLight}>Suggested response</p>
                    <p className={styles.bubbleTextLight}>
                      <HighlightedText text={liveAnswer.text || "Thinking…"} variant="onAccent" />
                    </p>
                    <p className={styles.bubbleTimeLight}>AI · streaming</p>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function WarningIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}
