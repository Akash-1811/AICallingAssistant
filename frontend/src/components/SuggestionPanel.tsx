import type { AnswerDoneMessage } from "../types";
import type { LiveAnswerState } from "../realtime";
import { CopyButton } from "./CopyButton";
import { HighlightedText } from "./HighlightedText";
import styles from "./SuggestionPanel.module.css";

interface Props {
  suggestion: AnswerDoneMessage | null;
  liveAnswer: LiveAnswerState | null;
  isLive: boolean;
  manualQuestion: string;
  onManualQuestionChange: (value: string) => void;
  manualLoading: boolean;
  manualAnswer: string;
  manualError: string | null;
  onManualAsk: () => void;
  onOpenManualAnswerModal: () => void;
}

export function SuggestionPanel({
  suggestion,
  liveAnswer,
  isLive,
  manualQuestion,
  onManualQuestionChange,
  manualLoading,
  manualAnswer,
  manualError,
  onManualAsk,
  onOpenManualAnswerModal,
}: Props) {
  const visibleText = liveAnswer?.text || suggestion?.text || "";
  const hasVisibleAnswer = visibleText.trim().length > 0;
  const visibleError = suggestion?.error ?? null;
  const isStreaming = liveAnswer !== null;

  return (
    <div className={styles.section}>
      <div className={styles.header}>
        <h2 className={styles.title}>AI Response Suggestions</h2>
        {(suggestion || liveAnswer) && !visibleError && (
          <span className={styles.confidenceBadge}>
            {isStreaming ? "Streaming" : "High confidence"}
          </span>
        )}
      </div>

      <div className={styles.cards}>
        <div className={`${styles.suggestionCard} ${styles.cardPrimary} ${isLive ? styles.cardLive : ""}`}>
          {isLive && <span className={styles.accentLine} aria-hidden="true" />}
          <div className={styles.cardTop}>
            <span className={styles.cardLabel}>Primary response</span>
            {hasVisibleAnswer && (
              <CopyButton text={visibleText} label="Copy suggestion" />
            )}
          </div>

          {suggestion || liveAnswer ? (
            <>
              {visibleError && (
                <p className={styles.warn} role="alert">
                  <WarnIcon />
                  {visibleError}
                </p>
              )}
              <p className={styles.cardBody}>
                <HighlightedText text={visibleText || "Thinking…"} />
              </p>
              <button
                type="button"
                className={styles.sendCta}
                onClick={() => {
                  void navigator.clipboard.writeText(visibleText).catch(() => undefined);
                }}
                disabled={!hasVisibleAnswer}
              >
                {isStreaming ? "Copy partial reply" : "Use response"} <span aria-hidden="true">→</span>
              </button>
            </>
          ) : (
            <p className={styles.emptyText}>
              {isLive
                ? "Listening — a suggested line will appear after the prospect speaks."
                : "Start a session to receive real-time suggestions."}
            </p>
          )}
        </div>

        <div className={`${styles.suggestionCard} ${styles.cardSecondary}`}>
          <span className={styles.tealLine} aria-hidden="true" />
          <div className={styles.askBlock}>
            <div className={styles.askHeaderRow}>
              <p className={styles.sideSectionTitle}>Ask AI</p>
              <button
                type="button"
                className={styles.expandModalBtn}
                disabled={!manualAnswer && !manualError}
                onClick={onOpenManualAnswerModal}
                aria-label="Open answer in enlarged view"
                title="Open enlarged view"
              >
                <ExpandModalIcon />
              </button>
            </div>
            <textarea
              className={styles.manualInput}
              placeholder="e.g. What is the price range for 3 BHK?"
              value={manualQuestion}
              onChange={(e) => onManualQuestionChange(e.target.value)}
              rows={3}
              aria-label="Question for AI"
            />
            <button
              type="button"
              className={styles.getAnswerBtn}
              disabled={manualLoading || !manualQuestion.trim()}
              onClick={onManualAsk}
            >
              {manualLoading ? "Thinking…" : "Get answer"}
            </button>
            {(manualAnswer || manualError) && (
              <button
                type="button"
                className={styles.openEnlargedLink}
                onClick={onOpenManualAnswerModal}
              >
                Open enlarged view
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function ExpandModalIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
    </svg>
  );
}

function WarnIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}
