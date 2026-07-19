import styles from "../../CallReviewPage.module.css";
import { asString } from "../json";

type EvidenceItem = Record<string, unknown>;

export function EvidenceList({
  title,
  field,
  items,
}: {
  title: string;
  field: "signal" | "objection";
  items: EvidenceItem[];
}) {
  if (items.length === 0) return null;

  return (
    <section className={styles.intentInsightCard}>
      <h3>{title}</h3>
      <ul className={styles.intentInsightList}>
        {items.map((item, i) => (
          <li key={i}>
            <strong>{asString(item[field])}</strong>
            {item.evidence_quote ? <span>{asString(item.evidence_quote)}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
