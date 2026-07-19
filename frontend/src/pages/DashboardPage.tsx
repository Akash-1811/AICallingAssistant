/**
 * Landing page: the owner's 10-second answer to "how are my sales calls going,
 * and what needs my attention?". Every number comes from the analytics summary
 * endpoint — measured from real calls or AI-assessed with evidence. Nothing is
 * invented, and the copy is written for non-technical users.
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  formatDuration,
  formatTimestamp,
  getAnalyticsSummary,
  type AnalyticsCallRow,
  type AnalyticsSummary,
} from "../api/conversations";
import appStyles from "../App.module.css";
import styles from "./DashboardPage.module.css";

type Range = "7d" | "30d" | "90d";

const RANGE_OPTIONS: { id: Range; label: string }[] = [
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
  { id: "90d", label: "90 days" },
];

const OUTCOME_LABELS: Record<AnalyticsCallRow["outcome"], { text: string; tone: "good" | "warn" | "risk" | "neutral" }> = {
  qualified: { text: "Strong lead", tone: "good" },
  follow_up: { text: "Needs follow-up", tone: "warn" },
  at_risk: { text: "May slip away", tone: "risk" },
  nurture: { text: "Still deciding", tone: "neutral" },
  pending: { text: "Being reviewed", tone: "neutral" },
};

const TALK_VERDICTS: Record<AnalyticsSummary["coaching_snapshot"]["talk_balance_label"], { text: string; note: string }> = {
  balanced: {
    text: "Good balance",
    note: "Right in the healthy range — customers get room to talk.",
  },
  rep_heavy: {
    text: "Talking too much",
    note: "Best range is 35–55% — try letting the customer talk more.",
  },
  prospect_heavy: {
    text: "Customer leads the talking",
    note: "Great listening — make sure key questions still get asked.",
  },
};

export function DashboardPage() {
  const [range, setRange] = useState<Range>("30d");
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAnalyticsSummary(range)
      .then((data) => {
        if (!cancelled) {
          setSummary(data);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load your numbers");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [range]);

  const recentCalls = useMemo(() => (summary?.calls ?? []).slice(0, 5), [summary]);
  const maxVolume = useMemo(
    () => Math.max(...(summary?.weekly_volume ?? []).map((b) => b.count), 1),
    [summary]
  );

  const hasCalls = (summary?.total_conversations ?? 0) > 0;
  const pipeline = summary?.pipeline_outlook;
  const stillDeciding = summary
    ? Math.max(
        0,
        summary.analyzed_conversations -
          (pipeline?.qualified_calls ?? 0) -
          (pipeline?.follow_up_calls ?? 0) -
          (pipeline?.at_risk_calls ?? 0)
      )
    : 0;
  const coach = summary?.coaching_snapshot;
  const verdict = coach ? TALK_VERDICTS[coach.talk_balance_label] : null;

  return (
    <div className={appStyles.content}>
      <div className={`${appStyles.mainCol} ${styles.dashMain}`}>
        <header className={styles.pageHeader}>
          <div>
            <p className={styles.pageEyebrow}>Your sales at a glance</p>
            <h1 className={styles.pageTitle}>
              <span className={styles.pageTitleDark}>Intelligence </span>
              <span className={styles.pageTitleAccent}>Dashboard.</span>
            </h1>
          </div>
          <div className={styles.rangeToggle} role="group" aria-label="Time period">
            {RANGE_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                className={`${styles.rangeBtn} ${range === opt.id ? styles.rangeBtnOn : ""}`}
                aria-pressed={range === opt.id}
                onClick={() => setRange(opt.id)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </header>

        {error ? <p className={styles.error}>{error}</p> : null}

        {!loading && !hasCalls && !error ? (
          <section className={styles.emptyCard}>
            <h2 className={styles.emptyTitle}>No calls yet</h2>
            <p className={styles.emptyBody}>
              Start your first live session and your numbers will appear here automatically.
            </p>
            <Link to="/live" className={styles.emptyBtn}>
              Start a session
            </Link>
          </section>
        ) : (
          <>
            <section className={styles.kpiGrid} aria-label="Key numbers">
              <article className={styles.heroCard}>
                <div>
                  <p className={styles.cardLabel}>Where your leads stand</p>
                  <p className={styles.heroValue}>
                    {pipeline?.qualified_calls ?? "—"}
                    <span className={styles.heroUnit}> strong leads</span>
                  </p>
                  <p className={styles.heroBody}>
                    Counted from what each customer actually said on the call.
                  </p>
                </div>
                <div>
                  {summary && summary.analyzed_conversations > 0 ? (
                    <div className={styles.splitBar} aria-hidden="true">
                      {(
                        [
                          [pipeline?.qualified_calls ?? 0, styles.splitGood],
                          [pipeline?.follow_up_calls ?? 0, styles.splitWarn],
                          [pipeline?.at_risk_calls ?? 0, styles.splitRisk],
                          [stillDeciding, styles.splitNeutral],
                        ] as const
                      )
                        .filter(([count]) => count > 0)
                        .map(([count, cls]) => (
                          <span key={cls} className={cls} style={{ flexGrow: count }} />
                        ))}
                    </div>
                  ) : null}
                  <div className={styles.pillRow}>
                    <span className={`${styles.pill} ${styles.pillWarn}`}>
                      <strong>{pipeline?.follow_up_calls ?? 0}</strong> need a follow-up call
                    </span>
                    <span className={`${styles.pill} ${styles.pillRisk}`}>
                      <strong>{pipeline?.at_risk_calls ?? 0}</strong> may slip away
                    </span>
                    <span className={`${styles.pill} ${styles.pillNeutral}`}>
                      <strong>{stillDeciding}</strong> still deciding
                    </span>
                  </div>
                </div>
              </article>

              <article className={styles.miniCard}>
                <div>
                  <p className={styles.cardLabel}>Customer interest</p>
                  <p className={styles.miniValue}>
                    {summary ? `${summary.avg_interest_score}%` : "—"}
                  </p>
                </div>
                <div>
                  <div className={styles.meterTrack}>
                    <div
                      className={styles.meterFill}
                      style={{ width: `${summary?.avg_interest_score ?? 0}%` }}
                    />
                  </div>
                  <p className={styles.miniFoot}>
                    How keen customers sounded, from {summary?.analyzed_conversations ?? 0}{" "}
                    reviewed {summary?.analyzed_conversations === 1 ? "call" : "calls"}
                  </p>
                </div>
              </article>

              <article className={`${styles.miniCard} ${styles.orangeCard}`}>
                <div>
                  <p className={styles.cardLabel}>Calls made</p>
                  <p className={styles.miniValue}>{summary?.total_conversations ?? "—"}</p>
                  <p className={styles.miniFoot}>
                    {summary?.analyzed_conversations ?? 0} of {summary?.total_conversations ?? 0}{" "}
                    reviewed by AI
                  </p>
                </div>
                <div>
                  <p className={styles.miniFoot}>
                    Average length {formatDuration(summary?.avg_duration_sec ?? null)}
                  </p>
                  <Link to="/analytics" className={styles.reportBtn}>
                    See full report
                  </Link>
                </div>
              </article>

              <article className={styles.miniCard}>
                <div>
                  <p className={styles.cardLabel}>Chance of closing</p>
                  <p className={styles.miniValue}>
                    {summary ? `${summary.avg_conversion_pct}%` : "—"}
                  </p>
                </div>
                <div>
                  <div className={styles.bandRow} aria-label="Calls grouped by closing chance">
                    {(
                      [
                        ["High", summary?.conversion_bands.likely ?? 0, styles.bandHigh],
                        ["Medium", summary?.conversion_bands.possible ?? 0, styles.bandMid],
                        ["Low", summary?.conversion_bands.unlikely ?? 0, styles.bandLow],
                      ] as const
                    ).map(([label, count, cls]) => (
                      <div key={label} className={styles.band}>
                        <div
                          className={`${styles.bandBar} ${cls}`}
                          style={{ height: `${14 + Math.min(count, 8) * 5}px` }}
                        />
                        <span className={styles.bandCount}>{count}</span>
                        <span className={styles.bandLabel}>{label}</span>
                      </div>
                    ))}
                  </div>
                  <p className={styles.miniFoot}>How many deals look likely to close</p>
                </div>
              </article>
            </section>

            <div className={styles.chartRow}>
              <section className={styles.chartCard} aria-label="Calls over time">
                <div className={styles.chartHead}>
                  <div>
                    <h2 className={styles.chartTitle}>Calls over time</h2>
                    <p className={styles.chartSub}>
                      Each bar is one {range === "7d" ? "day" : "week"}
                    </p>
                  </div>
                </div>
                <div className={styles.plot}>
                  {(summary?.weekly_volume ?? []).map((bucket) => {
                    const isPeak = bucket.count === maxVolume && bucket.count > 0;
                    return (
                      <div key={bucket.label} className={styles.plotCol}>
                        <div className={styles.plotBarWrap}>
                          {isPeak ? (
                            <span className={styles.plotTag}>
                              {bucket.count} {bucket.count === 1 ? "call" : "calls"}
                            </span>
                          ) : null}
                          <div
                            className={`${styles.plotBar} ${isPeak ? styles.plotBarHi : ""}`}
                            style={{ height: `${Math.max((bucket.count / maxVolume) * 100, 3)}%` }}
                            title={`${bucket.label}: ${bucket.count} ${bucket.count === 1 ? "call" : "calls"}`}
                          />
                        </div>
                        <span className={styles.plotDay}>{bucket.label}</span>
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className={styles.chartCard} aria-label="How your team talks">
                <div className={styles.chartHead}>
                  <div>
                    <h2 className={styles.chartTitle}>How your team talks on calls</h2>
                    <p className={styles.chartSub}>Measured from real call recordings</p>
                  </div>
                </div>
                <p className={styles.verdict}>{verdict?.text ?? "—"}</p>
                <ul className={styles.coachList}>
                  <li>
                    <div className={styles.coachTop}>
                      <span>Rep talking time</span>
                      <span className={styles.coachValue}>
                        {summary ? `${summary.avg_rep_talk_pct}%` : "—"}
                      </span>
                    </div>
                    <div className={styles.coachTrack}>
                      <div className={styles.coachZone} title="Healthy range: 35–55%" />
                      <div
                        className={styles.coachFill}
                        style={{ width: `${summary?.avg_rep_talk_pct ?? 0}%` }}
                      />
                    </div>
                    <p className={styles.coachNote}>{verdict?.note ?? ""}</p>
                  </li>
                  <li>
                    <div className={styles.coachTop}>
                      <span>Listening score</span>
                      <span className={styles.coachValue}>
                        {coach ? coach.listening_index : "—"}
                        <span className={styles.coachOf}>/100</span>
                      </span>
                    </div>
                    <div className={styles.coachTrack}>
                      <div
                        className={styles.coachFill}
                        style={{ width: `${coach?.listening_index ?? 0}%` }}
                      />
                    </div>
                  </li>
                  <li>
                    <div className={styles.coachTop}>
                      <span>Questions asked per call</span>
                      <span className={styles.coachValue}>{coach?.avg_rep_questions ?? "—"}</span>
                    </div>
                    <div className={styles.coachTrack}>
                      <div
                        className={styles.coachFill}
                        style={{
                          width: `${Math.min(((coach?.avg_rep_questions ?? 0) / 8) * 100, 100)}%`,
                        }}
                      />
                    </div>
                    <p className={styles.coachNote}>Aim for 6 or more — questions uncover what the customer wants.</p>
                  </li>
                </ul>
              </section>
            </div>

            <section className={styles.tableCard} aria-label="Recent calls">
              <div className={styles.tableHead}>
                <h2 className={styles.chartTitle}>Recent calls</h2>
                <Link to="/analytics" className={styles.tableLink}>
                  See all calls
                </Link>
              </div>
              <div className={styles.tableScroll}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th scope="col">Call</th>
                      <th scope="col">Result</th>
                      <th scope="col">Customer interest</th>
                      <th scope="col">Length</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentCalls.map((row) => {
                      const outcome = OUTCOME_LABELS[row.outcome];
                      return (
                        <tr key={row.id}>
                          <td>
                            <Link to={`/conversations/${row.id}`} className={styles.callId}>
                              {row.id.slice(0, 8)}
                            </Link>
                            <p className={styles.callWhen}>{formatTimestamp(row.started_at)}</p>
                          </td>
                          <td>
                            <span
                              className={`${styles.pill} ${
                                outcome.tone === "good"
                                  ? styles.pillGood
                                  : outcome.tone === "warn"
                                    ? styles.pillWarn
                                    : outcome.tone === "risk"
                                      ? styles.pillRisk
                                      : styles.pillNeutral
                              }`}
                            >
                              {outcome.text}
                            </span>
                          </td>
                          <td>
                            {row.interest_score != null ? (
                              <div className={styles.interestCell}>
                                <div className={styles.interestTrack}>
                                  <div
                                    className={styles.interestFill}
                                    style={{ width: `${row.interest_score}%` }}
                                  />
                                </div>
                                <span>{row.interest_score}%</span>
                              </div>
                            ) : (
                              <span className={styles.faint}>—</span>
                            )}
                          </td>
                          <td className={styles.duration}>{formatDuration(row.duration_sec)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
