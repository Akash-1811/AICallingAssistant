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

const OUTCOME_LABELS: Record<
  AnalyticsCallRow["outcome"],
  { text: string; tone: "good" | "warn" | "risk" | "neutral" }
> = {
  qualified: { text: "Strong lead", tone: "good" },
  follow_up: { text: "Needs follow-up", tone: "warn" },
  at_risk: { text: "May slip away", tone: "risk" },
  nurture: { text: "Still deciding", tone: "neutral" },
  pending: { text: "Being reviewed", tone: "neutral" },
};

const TALK_VERDICTS: Record<
  AnalyticsSummary["coaching_snapshot"]["talk_balance_label"],
  { text: string; note: string }
> = {
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

function toneClass(tone: "good" | "warn" | "risk" | "neutral"): string {
  if (tone === "good") return styles.pillGood;
  if (tone === "warn") return styles.pillWarn;
  if (tone === "risk") return styles.pillRisk;
  return styles.pillNeutral;
}

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

  const recentCalls = useMemo(() => (summary?.calls ?? []).slice(0, 6), [summary]);
  const actionCalls = useMemo(
    () =>
      (summary?.calls ?? [])
        .filter((c) => c.outcome === "follow_up" || c.outcome === "at_risk")
        .slice(0, 5),
    [summary]
  );
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
  const signals = summary?.signal_balance;
  const signalMax = Math.max(signals?.buying_signals_total ?? 0, signals?.objections_total ?? 0, 1);

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
          <div className={styles.grid}>
            {/* ── Row 1: dark hero + calls made ─────────────────────── */}
            <section className={`${styles.darkCard} ${styles.spanHero}`} aria-label="Where your leads stand">
              <div className={styles.heroTop}>
                <div>
                  <p className={styles.darkLabel}>Where your leads stand</p>
                  <p className={styles.heroValue}>
                    {pipeline?.qualified_calls ?? "—"}
                    <span className={styles.heroUnit}> strong leads</span>
                  </p>
                  <p className={styles.heroBody}>
                    Counted from what each customer actually said on the call.
                  </p>
                </div>
                <div className={styles.heroSideStats}>
                  <div className={styles.heroStat}>
                    <span className={styles.heroStatValue}>
                      {summary ? `${summary.avg_interest_score}%` : "—"}
                    </span>
                    <span className={styles.heroStatLabel}>Customer interest</span>
                    <span className={styles.heroMeter}>
                      <span style={{ width: `${summary?.avg_interest_score ?? 0}%` }} />
                    </span>
                  </div>
                  <div className={styles.heroStat}>
                    <span className={styles.heroStatValue}>
                      {summary ? `${summary.avg_conversion_pct}%` : "—"}
                    </span>
                    <span className={styles.heroStatLabel}>Chance of closing</span>
                    <span className={styles.heroMeter}>
                      <span style={{ width: `${summary?.avg_conversion_pct ?? 0}%` }} />
                    </span>
                  </div>
                </div>
              </div>
              <div className={styles.heroBottom}>
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
                  <span className={`${styles.pill} ${styles.pillOnDark}`}>
                    <i className={styles.dotGood} /> <strong>{pipeline?.qualified_calls ?? 0}</strong>{" "}
                    strong
                  </span>
                  <span className={`${styles.pill} ${styles.pillOnDark}`}>
                    <i className={styles.dotWarn} /> <strong>{pipeline?.follow_up_calls ?? 0}</strong>{" "}
                    need a follow-up
                  </span>
                  <span className={`${styles.pill} ${styles.pillOnDark}`}>
                    <i className={styles.dotRisk} /> <strong>{pipeline?.at_risk_calls ?? 0}</strong>{" "}
                    may slip away
                  </span>
                  <span className={`${styles.pill} ${styles.pillOnDark}`}>
                    <i className={styles.dotNeutral} /> <strong>{stillDeciding}</strong> still
                    deciding
                  </span>
                </div>
              </div>
            </section>

            <section className={`${styles.orangeCard} ${styles.spanSide}`} aria-label="Calls made">
              <div>
                <p className={styles.orangeLabel}>Calls made</p>
                <p className={styles.orangeValue}>{summary?.total_conversations ?? "—"}</p>
                <p className={styles.orangeFoot}>
                  {summary?.analyzed_conversations ?? 0} of {summary?.total_conversations ?? 0}{" "}
                  reviewed by AI
                </p>
              </div>
              <div className={styles.orangeStats}>
                <div>
                  <span className={styles.orangeStatValue}>
                    {formatDuration(summary?.avg_duration_sec ?? null)}
                  </span>
                  <span className={styles.orangeStatLabel}>Average length</span>
                </div>
                <div>
                  <span className={styles.orangeStatValue}>{summary?.avg_rep_wpm || "—"}</span>
                  <span className={styles.orangeStatLabel}>Words / minute</span>
                </div>
              </div>
              <Link to="/analytics" className={styles.reportBtn}>
                See full report
              </Link>
            </section>

            {/* ── Row 2: what customers said + volume chart ─────────── */}
            <section className={`${styles.card} ${styles.spanSide}`} aria-label="What customers told you">
              <p className={styles.cardLabel}>What customers told you</p>
              <ul className={styles.signalList}>
                <li>
                  <div className={styles.signalTop}>
                    <span>
                      <i className={styles.dotGood} /> Positive signs
                    </span>
                    <span className={styles.signalValue}>{signals?.buying_signals_total ?? 0}</span>
                  </div>
                  <div className={styles.signalTrack}>
                    <div
                      className={`${styles.signalFill} ${styles.signalFillGood}`}
                      style={{
                        width: `${((signals?.buying_signals_total ?? 0) / signalMax) * 100}%`,
                      }}
                    />
                  </div>
                </li>
                <li>
                  <div className={styles.signalTop}>
                    <span>
                      <i className={styles.dotRisk} /> Concerns raised
                    </span>
                    <span className={styles.signalValue}>{signals?.objections_total ?? 0}</span>
                  </div>
                  <div className={styles.signalTrack}>
                    <div
                      className={`${styles.signalFill} ${styles.signalFillRisk}`}
                      style={{ width: `${((signals?.objections_total ?? 0) / signalMax) * 100}%` }}
                    />
                  </div>
                </li>
              </ul>
              <p className={styles.cardFoot}>
                Things customers said that show interest — like asking about price or a site visit —
                versus doubts they raised.
              </p>
            </section>

            <section className={`${styles.card} ${styles.spanHero}`} aria-label="Calls over time">
              <div className={styles.chartHead}>
                <div>
                  <h2 className={styles.chartTitle}>Calls over time</h2>
                  <p className={styles.chartSub}>Each bar is one {range === "7d" ? "day" : "week"}</p>
                </div>
              </div>
              <div className={styles.plotArea}>
                <div className={styles.gridLines} aria-hidden="true">
                  <span data-label={maxVolume} />
                  <span data-label={Math.round(maxVolume / 2)} />
                  <span data-label="0" />
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
                            style={{ height: `${Math.max((bucket.count / maxVolume) * 100, 2)}%` }}
                            title={`${bucket.label}: ${bucket.count} ${bucket.count === 1 ? "call" : "calls"}`}
                          />
                        </div>
                        <span className={styles.plotDay}>{bucket.label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </section>

            {/* ── Row 3: attention list + coaching ──────────────────── */}
            <section className={`${styles.card} ${styles.spanHalf}`} aria-label="Needs your attention">
              <div className={styles.chartHead}>
                <div>
                  <h2 className={styles.chartTitle}>Needs your attention</h2>
                  <p className={styles.chartSub}>Calls where the deal could be won or lost</p>
                </div>
                {actionCalls.length > 0 ? (
                  <span className={styles.countBubble}>{actionCalls.length}</span>
                ) : null}
              </div>
              {actionCalls.length > 0 ? (
                <ul className={styles.actionList}>
                  {actionCalls.map((row) => {
                    const outcome = OUTCOME_LABELS[row.outcome];
                    return (
                      <li key={row.id}>
                        <Link to={`/conversations/${row.id}`} className={styles.actionRow}>
                          <div>
                            <span className={styles.actionId}>{row.id.slice(0, 8)}</span>
                            <span className={styles.actionWhen}>
                              {formatTimestamp(row.started_at)}
                            </span>
                          </div>
                          <span className={`${styles.pill} ${toneClass(outcome.tone)}`}>
                            {outcome.text}
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className={styles.allClear}>
                  <span className={styles.allClearMark}>✓</span>
                  <p>All clear — no calls are waiting on you right now.</p>
                </div>
              )}
            </section>

            <section className={`${styles.card} ${styles.spanHalf}`} aria-label="How your team talks">
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
                  <p className={styles.coachNote}>
                    Aim for 6 or more — questions uncover what the customer wants.
                  </p>
                </li>
              </ul>
            </section>

            {/* ── Row 4: recent calls ───────────────────────────────── */}
            <section className={`${styles.card} ${styles.spanFull}`} aria-label="Recent calls">
              <div className={styles.chartHead}>
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
                      <th scope="col">What they said</th>
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
                            <span className={`${styles.pill} ${toneClass(outcome.tone)}`}>
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
                          <td>
                            {row.outcome === "pending" ? (
                              <span className={styles.faint}>—</span>
                            ) : (
                              <span className={styles.saidCell}>
                                <i className={styles.dotGood} /> {row.buying_signals} positive
                                <i className={`${styles.dotRisk} ${styles.saidGap}`} />{" "}
                                {row.objections} {row.objections === 1 ? "concern" : "concerns"}
                              </span>
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
          </div>
        )}
      </div>
    </div>
  );
}
