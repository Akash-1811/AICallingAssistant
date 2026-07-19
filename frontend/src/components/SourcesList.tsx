import type { SourceItem as SourceItemType } from "../types";
import styles from "./SourcesList.module.css";

interface Props {
  sources: SourceItemType[];
}

export function SourcesList({ sources }: Props) {
  if (sources.length === 0) return null;

  return (
    <details className={styles.details}>
      <summary className={styles.summary}>
        <span className={styles.icon} aria-hidden="true">⬡</span>
        {sources.length} source{sources.length !== 1 ? "s" : ""} retrieved
      </summary>
      <ul className={styles.list}>
        {sources.map((s, i) => (
          <li key={s.id ?? i} className={styles.item}>
            {s.id && (
              <span className={styles.id}>#{s.id}</span>
            )}
            {s.excerpt && (
              <p className={styles.excerpt}>{s.excerpt}</p>
            )}
            {(s.vector_score !== undefined || s.rerank_score !== undefined) && (
              <div className={styles.scores}>
                {s.vector_score !== undefined && (
                  <ScorePill label="vec" value={s.vector_score} />
                )}
                {s.rerank_score !== undefined && (
                  <ScorePill label="rank" value={s.rerank_score} />
                )}
              </div>
            )}
            {s.metadata && Object.keys(s.metadata).length > 0 && (
              <div className={styles.meta}>
                {Object.entries(s.metadata).map(([k, v]) => (
                  <span key={k} className={styles.tag}>
                    {k}: {String(v)}
                  </span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

function ScorePill({ label, value }: { label: string; value: number }) {
  const pct = Math.min(100, Math.round(value * 100));
  return (
    <span className={styles.scorePill}>
      {label} {pct}%
    </span>
  );
}
