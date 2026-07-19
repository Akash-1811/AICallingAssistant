import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  formatDuration,
  formatTimestamp,
  getAnalyticsSummary,
  type AnalyticsCallRow,
  type AnalyticsSummary,
} from "../api/conversations";
import { scoreTone } from "./callReview/metrics";
import { OUTCOME_LABELS, RANGE_OPTIONS, TALK_LABELS } from "./analytics/constants";
import { DrilldownModal } from "./analytics/DrilldownModal";
import type { Drilldown, WinBand } from "./analytics/drilldown";
import { downloadAnalyticsCsv } from "./analytics/exportCsv";
import {
  buildSignalBars,
  buildVolumeBars,
  buildWinBands,
  describeCoaching,
  describeSignalBalance,
  formatScore,
} from "./analytics/metrics";
import appStyles from "../App.module.css";
import styles from "./AnalyticsPage.module.css";

const RECENT_CALL_LIMIT = 20;

export function AnalyticsPage() {
  const [range, setRange] = useState<"7d" | "30d" | "90d">("30d");
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [drilldown, setDrilldown] = useState<Drilldown | null>(null);

  useEffect(() => {
    setLoading(true);
    setExportNote(null);
    void getAnalyticsSummary(range)
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, [range]);

  const barWeeks = useMemo(() => buildVolumeBars(summary), [summary]);
  const winBands = useMemo(() => buildWinBands(summary), [summary]);
  const signalBars = useMemo(() => buildSignalBars(summary), [summary]);

  const calls = summary?.calls.slice(0, RECENT_CALL_LIMIT) ?? [];
  const analyzed = summary?.analyzed_conversations ?? 0;
  const pipeline = summary?.pipeline_outlook;
  const coaching = summary?.coaching_snapshot;
  const repTalkPct = summary?.avg_rep_talk_pct ?? 0;
  const prospectTalkPct = Math.max(0, Math.round(100 - repTalkPct));

  function handleExport() {
    if (!summary) {
      setExportNote("Load your call data before exporting.");
      return;
    }
    downloadAnalyticsCsv(summary, range);
    setExportNote(`CSV saved · ${summary.total_conversations} calls, ${summary.calls.length} rows in detail.`);
  }

  return (
    <div className={appStyles.content}>
      <div className={appStyles.mainCol}>
        <header className={styles.anHero}>
          <div className={styles.anHeroLeft}>
            <p className={styles.anEyebrow}>Call insights</p>
            <h1 className={styles.anHeroTitle}>
              <span className={styles.anHeroTitleDark}>See what your calls </span>
              <span className={styles.anHeroTitleAccent}>tell you.</span>
            </h1>
            <p className={styles.anHeroBody}>
              Find which calls are worth following up, where customers had concerns, and how well you
              listened. Tap any chart to see those calls.
            </p>
          </div>
          <div className={styles.anHeroStatus}>
            <span className={styles.anStatusLabel}>Data source</span>
            <div className={styles.anStatusRow}>
              <span className={styles.anStatusDot} aria-hidden="true" />
              <span>{loading ? "Loading…" : "Saved calls with AI review"}</span>
            </div>
          </div>
        </header>

        <section className={styles.graphGrid} aria-label="Call insight charts">
          <article className={styles.graphCard}>
            <div className={styles.graphCardHead}>
              <h2 className={styles.graphTitle}>Call volume</h2>
              <p className={styles.graphCaption}>
                {range === "7d" ? "By day" : "By week"} · {summary?.total_conversations ?? 0} total
              </p>
            </div>
            <div className={styles.graphBody}>
              {barWeeks.length ? (
                <div className={styles.barCluster} aria-label="Call volume by period">
                  {barWeeks.map((week) => (
                    <button
                      key={week.label}
                      type="button"
                      className={`${styles.barCol} ${styles.chartHit}`}
                      onClick={() => setDrilldown({ type: "volume", period: week.label })}
                      aria-label={`${week.label}, ${week.count} calls`}
                    >
                      <div className={styles.barWrap} aria-hidden="true">
                        {week.count ? <span className={styles.barValue}>{week.count}</span> : null}
                        <div
                          className={styles.barFill}
                          style={{ height: `${Math.max(week.pct, week.count ? 8 : 2)}%` }}
                        />
                      </div>
                      <span className={styles.barTick}>{week.label}</span>
                    </button>
                  ))}
                </div>
              ) : (
                <p className={styles.graphEmpty}>No calls recorded in this range.</p>
              )}
            </div>
          </article>

          <article className={styles.graphCard}>
            <div className={styles.graphCardHead}>
              <h2 className={styles.graphTitle}>Chance to close</h2>
              <p className={styles.graphCaption}>
                {pipeline
                  ? `${pipeline.qualified_calls} of ${analyzed} reviewed calls look like good leads`
                  : "Which calls are worth following up"}
              </p>
            </div>
            <div className={styles.graphBody}>
              {analyzed > 0 ? (
                <div className={styles.insightStack}>
                  <ul className={styles.hBarList}>
                    {winBands.map((band) => (
                      <li key={band.id}>
                        <button
                          type="button"
                          className={`${styles.hBarRow} ${styles.chartHit}`}
                          onClick={() => setDrilldown({ type: "win_band", band: band.id as WinBand })}
                        >
                          <span className={styles.hBarLabel}>{band.label}</span>
                          <div className={styles.hBarTrack}>
                            <div className={styles.hBarFill} style={{ width: `${band.pct}%` }} />
                          </div>
                          <span className={styles.hBarVal}>
                            {band.count} ({band.pct}%)
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className={styles.insightGrid}>
                    {(
                      [
                        ["qualified", pipeline?.qualified_calls ?? 0, "Good lead"],
                        ["follow_up", pipeline?.follow_up_calls ?? 0, "Needs follow-up"],
                        ["at_risk", pipeline?.at_risk_calls ?? 0, "Needs attention"],
                      ] as const
                    ).map(([outcome, value, label]) => (
                      <button
                        key={outcome}
                        type="button"
                        className={`${styles.insightStat} ${styles.chartHit}`}
                        onClick={() => setDrilldown({ type: "outcome", outcome })}
                      >
                        <span className={styles.insightStatValue}>{value}</span>
                        <span className={styles.insightStatLabel}>{label}</span>
                      </button>
                    ))}
                  </div>
                  <p className={styles.insightNote}>
                    Avg close chance {summary?.avg_conversion_pct ?? "—"}% · avg interest{" "}
                    {summary?.avg_interest_score ?? "—"}
                  </p>
                </div>
              ) : (
                <p className={styles.graphEmpty}>Shows up after your calls are reviewed.</p>
              )}
            </div>
          </article>

          <article className={styles.graphCard}>
            <div className={styles.graphCardHead}>
              <h2 className={styles.graphTitle}>Customer cues</h2>
              <p className={styles.graphCaption}>Interest vs concerns picked up in conversations</p>
            </div>
            <div className={styles.graphBody}>
              {analyzed > 0 && signalBars.length ? (
                <div className={styles.insightStack}>
                  <ul className={styles.hBarList}>
                    {signalBars.map((bar) => (
                      <li key={bar.id}>
                        <button
                          type="button"
                          className={`${styles.hBarRow} ${styles.chartHit}`}
                          onClick={() => setDrilldown({ type: "signals", signal: bar.id })}
                        >
                          <span className={styles.hBarLabel}>{bar.label}</span>
                          <div className={styles.hBarTrack}>
                            <div
                              className={styles.hBarFill}
                              data-tone={bar.tone}
                              style={{ width: `${Math.max(bar.pct, bar.count ? 12 : 0)}%` }}
                            />
                          </div>
                          <span className={styles.hBarVal}>
                            {bar.count} ({bar.avg}/call)
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  <p className={styles.insightNote}>
                    {describeSignalBalance(summary?.signal_balance.net_signal_score ?? 0, analyzed)}
                  </p>
                </div>
              ) : (
                <p className={styles.graphEmpty}>Shows interest and concerns after calls are reviewed.</p>
              )}
            </div>
          </article>

          <article className={styles.graphCard}>
            <div className={styles.graphCardHead}>
              <h2 className={styles.graphTitle}>How you spoke</h2>
              <p className={styles.graphCaption}>Talk balance · avg length {formatDuration(summary?.avg_duration_sec)}</p>
            </div>
            <div className={styles.graphBody}>
              {analyzed > 0 && coaching ? (
                <div className={styles.insightStack}>
                  <button
                    type="button"
                    className={`${styles.coachHeader} ${styles.chartHit}`}
                    onClick={() => setDrilldown({ type: "coaching", focus: "overview" })}
                  >
                    <span className={styles.coachBadge} data-tone={coaching.talk_balance_label}>
                      {TALK_LABELS[coaching.talk_balance_label]}
                    </span>
                    <span className={styles.coachMeta}>
                      You {repTalkPct}% · Them {prospectTalkPct}%
                    </span>
                  </button>
                  <button
                    type="button"
                    className={`${styles.talkBalanceTrack} ${styles.chartHit}`}
                    onClick={() => setDrilldown({ type: "coaching", focus: "overview" })}
                    aria-label="View who talked more on each call"
                  >
                    <div className={styles.talkBalanceRep} style={{ width: `${repTalkPct}%` }} />
                  </button>
                  <div className={styles.insightGrid}>
                    {(
                      [
                        ["questions", coaching.avg_rep_questions, "Questions asked"],
                        ["listening", coaching.listening_index, "Listening score"],
                        ["wpm", summary?.avg_rep_wpm ?? "—", "Speaking speed"],
                      ] as const
                    ).map(([focus, value, label]) => (
                      <button
                        key={focus}
                        type="button"
                        className={`${styles.insightStat} ${styles.chartHit}`}
                        onClick={() => setDrilldown({ type: "coaching", focus })}
                      >
                        <span className={styles.insightStatValue}>{value}</span>
                        <span className={styles.insightStatLabel}>{label}</span>
                      </button>
                    ))}
                  </div>
                  <p className={styles.insightNote}>{describeCoaching(coaching, repTalkPct)}</p>
                </div>
              ) : (
                <p className={styles.graphEmpty}>Talk stats appear after calls are saved and reviewed.</p>
              )}
            </div>
          </article>
        </section>

        <section className={styles.dimPanel} aria-label="Recent calls">
          <div className={styles.dimHead}>
            <h2 className={styles.dimTitle}>Recent calls</h2>
            <p className={styles.dimCaption}>
              {calls.length ? `${calls.length} in selected range` : "No calls in selected range"}
            </p>
          </div>
          <div className={styles.dimScroll}>
            {calls.length ? (
              <table className={styles.dimTable}>
                <thead>
                  <tr>
                    <th scope="col">When</th>
                    <th scope="col">Caller</th>
                    <th scope="col">Length</th>
                    <th scope="col">Result</th>
                    <th scope="col">Interest / concerns</th>
                    <th scope="col">Close chance</th>
                    <th scope="col" />
                  </tr>
                </thead>
                <tbody>
                  {calls.map((call: AnalyticsCallRow) => (
                    <tr key={call.id}>
                      <td>{formatTimestamp(call.started_at)}</td>
                      <td>{call.rep_label?.trim() || "—"}</td>
                      <td>{formatDuration(call.duration_sec)}</td>
                      <td>
                        <span className={styles.outcomePill} data-tone={call.outcome}>
                          {OUTCOME_LABELS[call.outcome]}
                        </span>
                      </td>
                      <td>{call.outcome === "pending" ? "—" : `+${call.buying_signals} / -${call.objections}`}</td>
                      <td>
                        {call.conversion_pct != null ? (
                          <span className={styles.scorePill} data-tone={scoreTone(call.conversion_pct)}>
                            {formatScore(call.conversion_pct)}%
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        <Link className={styles.reviewBtn} to={`/conversations/${call.id}`}>
                          Review
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className={styles.tableEmpty}>Start a live call to see insights here.</p>
            )}
          </div>
        </section>
      </div>

      <aside className={appStyles.rightPanel}>
        <div className={styles.rangeCard}>
          <h3 className={styles.rangeTitle}>Date range</h3>
          <div className={styles.rangeRow}>
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                className={`${styles.rangePill} ${range === option.id ? styles.rangePillActive : ""}`}
                onClick={() => setRange(option.id)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.exportCard}>
          <p className={styles.exportTitle}>Download</p>
          <button type="button" className={styles.exportBtn} onClick={handleExport} disabled={loading || !summary}>
            Export report
          </button>
          <p className={styles.exportHint}>
            {exportNote ?? `Spreadsheet for the last ${range === "7d" ? "7 days" : range === "30d" ? "30 days" : "90 days"} — summary and call list.`}
          </p>
        </div>

        <div className={styles.snapshotCard}>
          <h3 className={styles.railCardTitle}>At a glance</h3>
          <p className={styles.snapshotSub}>Selected period</p>
          <ul className={styles.snapshotList}>
            {(
              [
                ["Saved calls", summary?.total_conversations ?? "—"],
                ["Good leads", pipeline?.qualified_calls ?? "—"],
                ["Needs attention", pipeline?.at_risk_calls ?? "—"],
                ["Avg close chance", summary?.avg_conversion_pct ? `${summary.avg_conversion_pct}%` : "—"],
                ["Interest balance", summary?.signal_balance.net_signal_score ?? "—"],
                ["Listening score", coaching?.listening_index ?? "—"],
                ["Calls reviewed", summary?.analysis_coverage_pct != null ? `${summary.analysis_coverage_pct}%` : "—"],
              ] as const
            ).map(([label, value]) => (
              <li key={label} className={styles.snapshotRow}>
                <span className={styles.snapshotLabel}>{label}</span>
                <span className={styles.snapshotValue}>{value}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className={styles.coverageCard}>
          <h3 className={styles.railCardTitle}>Calls reviewed</h3>
          <p className={styles.coverageCaption}>How many saved calls have an AI review</p>
          <div className={styles.coverageTrack}>
            <div className={styles.coverageFill} style={{ width: `${summary?.analysis_coverage_pct ?? 0}%` }} />
          </div>
          <p className={styles.coveragePct}>
            {summary?.analysis_coverage_pct != null ? `${summary.analysis_coverage_pct}% analyzed` : "—"}
          </p>
        </div>
      </aside>

      <DrilldownModal drilldown={drilldown} summary={summary} onClose={() => setDrilldown(null)} />
    </div>
  );
}
