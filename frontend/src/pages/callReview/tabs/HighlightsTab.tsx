import { formatMs } from "../../../api/conversations";
import styles from "../../CallReviewPage.module.css";
import { asNumber, asString } from "../json";
import type { CallReviewView } from "../metrics";

export function HighlightsTab({
  vm,
  onJumpToMoment,
}: {
  vm: CallReviewView;
  onJumpToMoment: (startMs: number) => void;
}) {
  return (
    <section className={styles.card}>
      <h2>Pivotal moments</h2>
      <p className={styles.chartHint}>Click a moment to jump to that point in the transcript.</p>
      {vm.pivotal.length > 0 ? (
        <ol className={styles.timeline}>
          {vm.pivotal.map((m, i) => (
            <li key={i}>
              <button type="button" className={styles.timelineBtn} onClick={() => onJumpToMoment(asNumber(m.start_ms))}>
                <span className={styles.timelineDot} />
                <div>
                  <span className={styles.timelineLabel}>{asString(m.label)}</span>
                  <span className={styles.timelineTime}>{formatMs(asNumber(m.start_ms))}</span>
                  <p>{asString(m.quote)}</p>
                </div>
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <p className={styles.emptyChart}>No pivotal moments identified for this call.</p>
      )}
    </section>
  );
}
