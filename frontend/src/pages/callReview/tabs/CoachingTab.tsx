import styles from "../../CallReviewPage.module.css";
import { TalkListenDonut } from "../charts";
import { MetricBar } from "../components/ProgressBar";
import { asString } from "../json";
import type { CallReviewView } from "../metrics";

export function CoachingTab({ vm }: { vm: CallReviewView }) {
  return (
    <>
      <section className={`${styles.card} ${styles.coachingPanel}`}>
        <header className={styles.coachingHeader}>
          <h2>How you spoke</h2>
          {vm.repComm.overall_assessment ? (
            <p className={styles.coachingLead}>{asString(vm.repComm.overall_assessment)}</p>
          ) : null}
        </header>

        <div className={styles.coachingLayout}>
          <div className={styles.metricBars}>
            <MetricBar label="Pace" value={vm.paceWpm} max={220} unit=" WPM" />
            <MetricBar label="Filler words" value={vm.fillerPct} max={8} unit="%" />
            <MetricBar label="Questions asked" value={vm.questions} max={12} unit="" />
            <MetricBar
              label="Rep talk time"
              value={vm.repPct}
              max={100}
              unit="%"
              fill={vm.repPct >= 40 && vm.repPct <= 60 ? "teal" : "accent"}
            />
          </div>
          <aside className={styles.coachingDonutCard}>
            <h3>Talk / listen balance</h3>
            <p className={styles.coachingDonutHint}>Ideal: 40–60% rep talk</p>
            <TalkListenDonut repPct={vm.repPct} prospectPct={vm.prospectPct} />
          </aside>
        </div>

        {vm.strengths.length > 0 ? (
          <div className={styles.coachingStrengths}>
            <h3 className={styles.coachingSectionLabel}>Strengths</h3>
            <ul className={styles.chipList}>
              {vm.strengths.map((s) => (
                <li key={s} className={styles.chipGood}>
                  {s}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      {vm.coaching.length > 0 ? (
        <section className={`${styles.card} ${styles.coachingRecsPanel}`}>
          <h2>Coaching recommendations</h2>
          <p className={styles.coachingRecsHint}>Actionable improvements from this call.</p>
          <div className={styles.coachGrid}>
            {vm.coaching.map((tip, i) => (
              <article key={i} className={styles.coachCard}>
                <span>{asString(tip.area)}</span>
                <p>{asString(tip.recommendation)}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
