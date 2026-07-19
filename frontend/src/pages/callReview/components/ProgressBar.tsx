import styles from "../../CallReviewPage.module.css";

export function MetricBar({
  label,
  value,
  max,
  unit,
  fill = "teal",
}: {
  label: string;
  value: number;
  max: number;
  unit: string;
  fill?: "teal" | "accent";
}) {
  const pct = Math.min(100, (value / max) * 100);
  const fillClass = fill === "accent" ? styles.metricBarFillAccent : styles.metricBarFill;

  return (
    <div className={styles.metricBar}>
      <div className={styles.metricBarHead}>
        <span>{label}</span>
        <strong>
          {value}
          {unit}
        </strong>
      </div>
      <div className={styles.metricBarTrack}>
        <div className={fillClass} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function BarList({
  items,
  scale = "relative",
}: {
  items: { label: string; value: number }[];
  scale?: "relative" | "absolute";
}) {
  const max = Math.max(...items.map((i) => i.value), 1);

  return (
    <div className={styles.barChart}>
      {items.map((item) => {
        const width = scale === "absolute" ? item.value : (item.value / max) * 100;
        return (
          <div key={item.label} className={styles.barRow}>
            <div className={styles.barRowTop}>
              <span className={styles.barLabel}>{item.label}</span>
              <span className={styles.barValue}>{item.value}%</span>
            </div>
            <div className={styles.barTrack}>
              <div className={styles.barFill} style={{ width: `${Math.min(100, width)}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
