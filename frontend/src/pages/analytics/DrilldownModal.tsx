import { useEffect, useMemo, useRef } from "react";
import { Link } from "react-router-dom";
import { formatDuration, formatTimestamp, type AnalyticsSummary } from "../../api/conversations";
import { scoreTone } from "../callReview/metrics";
import styles from "../AnalyticsPage.module.css";
import { OUTCOME_LABELS } from "./constants";
import { getDrilldownCalls, getDrilldownMeta, type Drilldown } from "./drilldown";

type Props = {
  drilldown: Drilldown | null;
  summary: AnalyticsSummary | null;
  onClose: () => void;
};

export function DrilldownModal({ drilldown, summary, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const calls = useMemo(
    () => (drilldown && summary ? getDrilldownCalls(summary, drilldown) : []),
    [drilldown, summary],
  );
  const meta = useMemo(
    () => (drilldown && summary ? getDrilldownMeta(summary, drilldown, calls) : null),
    [drilldown, summary, calls],
  );

  useEffect(() => {
    if (!drilldown) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const frame = requestAnimationFrame(() => closeRef.current?.focus());
    return () => {
      document.removeEventListener("keydown", onKey);
      cancelAnimationFrame(frame);
    };
  }, [drilldown, onClose]);

  if (!drilldown || !summary || !meta) return null;

  const showCoaching = drilldown.type === "coaching";
  const showSignals = drilldown.type === "signals" || drilldown.type === "outcome";
  const showConversion =
    drilldown.type === "win_band" || drilldown.type === "outcome" || drilldown.type === "volume";

  return (
    <div className={styles.drillBackdrop} role="presentation" onClick={onClose}>
      <div
        className={styles.drillModal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="analytics-drilldown-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className={styles.drillHead}>
          <div>
            <p className={styles.drillEyebrow}>Details</p>
            <h2 id="analytics-drilldown-title" className={styles.drillTitle}>
              {meta.title}
            </h2>
            <p className={styles.drillSubtitle}>{meta.subtitle}</p>
          </div>
          <button ref={closeRef} type="button" className={styles.drillClose} onClick={onClose} aria-label="Close details">
            ×
          </button>
        </header>

        <div className={styles.drillStats}>
          {meta.stats.map((stat) => (
            <div key={stat.label} className={styles.drillStat}>
              <span className={styles.drillStatValue}>{stat.value}</span>
              <span className={styles.drillStatLabel}>{stat.label}</span>
            </div>
          ))}
        </div>

        <div className={styles.drillBody}>
          {calls.length ? (
            <table className={styles.drillTable}>
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Caller</th>
                  <th scope="col">Length</th>
                  {showConversion ? <th scope="col">Close chance</th> : null}
                  {showSignals ? <th scope="col">Interest</th> : null}
                  {showCoaching ? <th scope="col">You talked</th> : null}
                  {showCoaching ? <th scope="col">Questions</th> : null}
                  {showCoaching && drilldown.focus === "wpm" ? <th scope="col">Speed</th> : null}
                  {showCoaching && drilldown.focus === "listening" ? <th scope="col">Listening</th> : null}
                  <th scope="col">Result</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id}>
                    <td>{formatTimestamp(call.started_at)}</td>
                    <td>{call.rep_label?.trim() || "—"}</td>
                    <td>{formatDuration(call.duration_sec)}</td>
                    {showConversion ? (
                      <td>
                        {call.conversion_pct != null ? (
                          <span className={styles.scorePill} data-tone={scoreTone(call.conversion_pct)}>
                            {call.conversion_pct}%
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                    ) : null}
                    {showSignals ? (
                      <td>
                        {call.outcome === "pending" ? "—" : `+${call.buying_signals} / -${call.objections}`}
                      </td>
                    ) : null}
                    {showCoaching ? <td>{call.rep_talk_pct != null ? `${call.rep_talk_pct}%` : "—"}</td> : null}
                    {showCoaching ? <td>{call.rep_questions || "—"}</td> : null}
                    {showCoaching && drilldown.focus === "wpm" ? <td>{call.rep_wpm ?? "—"}</td> : null}
                    {showCoaching && drilldown.focus === "listening" ? <td>{call.listening_index ?? "—"}</td> : null}
                    <td>
                      <span className={styles.outcomePill} data-tone={call.outcome}>
                        {OUTCOME_LABELS[call.outcome]}
                      </span>
                    </td>
                    <td>
                      <Link className={styles.drillReviewLink} to={`/conversations/${call.id}`} onClick={onClose}>
                        Review
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className={styles.drillEmpty}>No calls match this selection in the current range.</p>
          )}
        </div>

        <footer className={styles.drillFoot}>Press Esc to close</footer>
      </div>
    </div>
  );
}
