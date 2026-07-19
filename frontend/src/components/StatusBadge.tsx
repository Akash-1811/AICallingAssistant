import type { SessionStatus } from "../types";
import styles from "./StatusBadge.module.css";

const LABELS: Record<SessionStatus, string> = {
  idle:       "Idle",
  connecting: "Connecting…",
  live:       "Live",
  error:      "Error",
};

interface Props {
  status: SessionStatus;
  /** Optional session duration string, e.g. "02:45" */
  elapsed?: string;
}

export function StatusBadge({ status, elapsed }: Props) {
  return (
    <span className={`${styles.badge} ${styles[status]}`} aria-live="polite">
      {status === "live" && <span className={styles.dot} aria-hidden="true" />}
      {LABELS[status]}
      {status === "live" && elapsed && (
        <span className={styles.elapsed}>{elapsed}</span>
      )}
    </span>
  );
}
