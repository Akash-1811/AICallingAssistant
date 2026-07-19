import styles from "../../CallReviewPage.module.css";
import { BarList } from "../components/ProgressBar";
import { CallPhaseList, MiniTrendChart } from "../charts";
import { CURVE_OPTIONS, GLANCE_ROWS, type CurveKey } from "../constants";
import { asString } from "../json";
import type { CallReviewView } from "../metrics";
import { scoreTone } from "../metrics";
import { EvidenceList } from "../components/EvidenceList";

type Props = {
  vm: CallReviewView;
  engagementCurve: CurveKey;
  onEngagementCurveChange: (key: CurveKey) => void;
};

export function IntentTab({ vm, engagementCurve, onEngagementCurveChange }: Props) {
  const activeCurve = vm.curves[engagementCurve];

  return (
    <div className={styles.intentTab}>
      <section className={styles.intentSummary}>
        <div className={styles.intentSummaryMain}>
          <h2>Client intent</h2>
          {vm.clientIntent.summary ? (
            <p className={styles.intentSummaryText}>{asString(vm.clientIntent.summary)}</p>
          ) : null}
        </div>
        <div className={styles.intentSummaryMeta}>
          {vm.clientIntent.primary_intent ? (
            <span className={styles.intentPill}>
              {asString(vm.clientIntent.primary_intent).replace(/_/g, " ")}
            </span>
          ) : null}
          <span className={`${styles.badge} ${styles[`badge_${scoreTone(vm.interestScore)}`]}`}>
            {vm.interestScore}% interested
          </span>
        </div>
      </section>

      <div className={styles.intentDashboard}>
        <div className={styles.intentColumnLeft}>
          <section className={styles.intentCard}>
            <header className={styles.intentCardHeader}>
              <h3>Conversation topics</h3>
              <p className={styles.intentCardHint}>AI-assessed share of discussion</p>
            </header>
            {vm.topicBars.length > 0 ? (
              <BarList items={vm.topicBars} scale="absolute" />
            ) : (
              <p className={styles.emptyChart}>No topics in this report.</p>
            )}
          </section>

          <section className={styles.intentCard}>
            <header className={styles.intentCardHeader}>
              <h3>At a glance</h3>
            </header>
            <div className={styles.glanceGrid}>
              {GLANCE_ROWS.map((row) => {
                const value = vm.callGlance[row.key];
                const display =
                  row.suffix && typeof value === "number" ? `${value}${row.suffix}` : String(value);
                const sub = row.subKey ? vm.callGlance[row.subKey] : undefined;
                return (
                  <div key={row.label} className={styles.glanceCard}>
                    <p className={styles.glanceLabel}>{row.label}</p>
                    <p className={styles.glanceValue}>{display}</p>
                    {sub ? <p className={styles.glanceSub}>{sub}</p> : null}
                  </div>
                );
              })}
            </div>
          </section>

          {vm.coachingInsight ? (
            <aside className={styles.proTipBanner}>
              <p>{vm.coachingInsight}</p>
            </aside>
          ) : null}
        </div>

        <section className={`${styles.intentCard} ${styles.intentEngagementCard}`}>
          <header className={styles.intentEngagementHeader}>
            <div className={styles.intentEngagementTitle}>
              <div className={styles.chartCardTitleRow}>
                <h3>Prospect activity</h3>
                <span className={styles.dataBadgeLive}>Measured from transcript</span>
              </div>
              <p className={styles.intentCardHint}>
                How much the prospect spoke, asked, and pushed back across the call.
              </p>
            </div>
            <select
              className={styles.curveSelect}
              value={engagementCurve}
              onChange={(e) => onEngagementCurveChange(e.target.value as CurveKey)}
              aria-label="Chart metric"
            >
              {CURVE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </header>

          <div className={styles.engagementChartZone}>
            {activeCurve.length > 0 ? (
              <MiniTrendChart values={activeCurve} color="accent" spikeIndices={vm.objectionSpikes} />
            ) : (
              <p className={styles.emptyChart}>No timeline data for this call.</p>
            )}
          </div>

          <div className={styles.callPhasesBlock}>
            <div className={styles.chartCardTitleRow}>
              <h4 className={styles.callPhasesTitle}>Call phases</h4>
              <span className={styles.dataBadgeEst}>AI assessed · quote-backed</span>
            </div>
            <CallPhaseList phases={vm.sentimentPhases} />
          </div>
        </section>
      </div>

      {vm.buyingSignals.length > 0 || vm.objections.length > 0 ? (
        <div className={styles.intentInsights}>
          <EvidenceList title="Buying signals" field="signal" items={vm.buyingSignals} />
          <EvidenceList title="Objections" field="objection" items={vm.objections} />
        </div>
      ) : null}
    </div>
  );
}
