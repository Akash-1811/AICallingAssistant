import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  formatDuration,
  formatTimestamp,
  listConversations,
  type ConversationSummary,
} from "../api/conversations";
import appStyles from "../App.module.css";
import styles from "./DashboardPage.module.css";

const VELOCITY_DAYS = [
  { label: "Mon", pct: 38, highlight: false },
  { label: "Tue", pct: 52, highlight: false },
  { label: "Wed", pct: 45, highlight: false },
  { label: "Thu", pct: 61, highlight: false },
  { label: "Fri", pct: 72, highlight: true, tag: "29%" },
  { label: "Sat", pct: 28, highlight: false },
  { label: "Sun", pct: 34, highlight: false },
];

const SESSIONS_PLACEHOLDER = [
  {
    id: "#ACC-9022",
    name: "Jonathan K.",
    vertical: "Real Estate Vertical",
    initials: "JK",
    outcome: "converted" as const,
    duration: "09:42",
  },
  {
    id: "#ACC-9018",
    name: "Maria Santos",
    vertical: "FinTech",
    initials: "MS",
    outcome: "nurturing" as const,
    duration: "06:15",
  },
  {
    id: "#ACC-9014",
    name: "David Chen",
    vertical: "Healthcare",
    initials: "DC",
    outcome: "unresponsive" as const,
    duration: "02:03",
  },
];

export function DashboardPage() {
  const [chartScale, setChartScale] = useState<"D" | "W" | "M">("M");
  const [recentCalls, setRecentCalls] = useState<ConversationSummary[]>([]);
  const [totalCalls, setTotalCalls] = useState<number | null>(null);

  useEffect(() => {
    void listConversations(5)
      .then((data) => {
        setRecentCalls(data.items);
        setTotalCalls(data.items.length > 0 ? data.items.length : 0);
      })
      .catch(() => {
        setRecentCalls([]);
      });
  }, []);

  return (
    <div className={appStyles.content}>
      <div className={`${appStyles.mainCol} ${styles.dashMain}`}>
        <header className={styles.pageHeader}>
          <p className={styles.pageEyebrow}>System performance hub</p>
          <h1 className={styles.pageTitle}>
            <span className={styles.pageTitleDark}>Intelligence </span>
            <span className={styles.pageTitleAccent}>Dashboard.</span>
          </h1>
        </header>

        <section className={styles.kpiGrid} aria-label="Key metrics">
          <article className={styles.capacityCard}>
            <span className={styles.capacityBadge}>Active capacity</span>
            <p className={styles.capacityValue}>98.4%</p>
            <p className={styles.capacityBody}>
              AI processing efficiency across inference clusters—latency within SLO for the current load envelope.
            </p>
            <div className={styles.capacityFooter}>
              <span className={styles.capacityFooterLabel}>Cluster nodes · 128 online</span>
              <span className={styles.nodeDots} aria-hidden="true">
                <span />
                <span />
                <span />
                <span />
              </span>
            </div>
          </article>

          <article className={`${styles.miniCard} ${styles.sentimentCard}`}>
            <p className={styles.miniLabel}>Avg. sentiment</p>
            <p className={styles.miniEmphasis}>Positive</p>
            <div className={styles.sentimentBar}>
              <div className={styles.sentimentFill} style={{ width: "82.4%" }} />
            </div>
            <p className={styles.miniFoot}>82.4% neural confidence</p>
          </article>

          <article className={`${styles.miniCard} ${styles.orangeCard}`}>
            <p className={styles.miniLabelOrange}>Total sessions</p>
            <p className={styles.sessionsValue}>{totalCalls ?? "—"}</p>
            <Link to="/analytics" className={styles.reportBtn}>
              Generate report
            </Link>
          </article>

          <article className={`${styles.miniCard} ${styles.leadCard}`}>
            <p className={styles.miniLabel}>Lead conv.</p>
            <p className={styles.convValue}>24.2%</p>
            <p className={styles.convTrend}>+4.1% vs PW</p>
            <div className={styles.leadSpark} aria-hidden="true">
              {[40, 55, 48, 62, 58].map((h, i) => (
                <span key={i} className={styles.leadSparkBar} style={{ height: `${h}%` }} />
              ))}
            </div>
            <p className={styles.leadFoot}>SQL → won, blended across inbound and partner dialer.</p>
          </article>
        </section>

        <div className={styles.chartRow}>
          <section className={styles.chartSection} aria-label="Conversion velocity">
            <div className={styles.chartHeader}>
              <div>
                <h2 className={styles.chartTitle}>Conversion velocity</h2>
                <p className={styles.chartSub}>7-day rolling optimization metric</p>
              </div>
              <div className={styles.chartToggles} role="group" aria-label="Chart scale">
                {(["D", "W", "M"] as const).map((id) => (
                  <button
                    key={id}
                    type="button"
                    className={`${styles.chartToggle} ${chartScale === id ? styles.chartToggleOn : ""}`}
                    onClick={() => setChartScale(id)}
                  >
                    {id}
                  </button>
                ))}
              </div>
            </div>
            <div className={styles.chartPlot}>
              {VELOCITY_DAYS.map((d) => (
                <div key={d.label} className={styles.chartCol}>
                  <div className={styles.chartBarWrap}>
                    {d.tag ? <span className={styles.chartTag}>{d.tag}</span> : null}
                    <div
                      className={`${styles.chartBar} ${d.highlight ? styles.chartBarHi : ""}`}
                      style={{ height: `${d.pct}%` }}
                    />
                  </div>
                  <span className={styles.chartDay}>{d.label}</span>
                </div>
              ))}
            </div>
          </section>

          <section className={styles.insightCard} aria-label="Model throughput">
            <div className={styles.insightHead}>
              <div>
                <h2 className={styles.insightTitle}>Inference throughput</h2>
                <p className={styles.insightSub}>Tokens per minute · live cluster</p>
              </div>
              <span className={styles.insightBadge}>Live</span>
            </div>
            <p className={styles.insightHero}>
              12.4k <span className={styles.insightHeroUnit}>tok/min</span>
            </p>
            <p className={styles.insightCaption}>P95 latency 118 ms · within SLO</p>
            <ul className={styles.insightList}>
              <li>
                <div className={styles.insightRowTop}>
                  <span className={styles.insightLabel}>Streaming ASR</span>
                  <span className={styles.insightPct}>88%</span>
                </div>
                <span className={styles.insightTrack}>
                  <span className={styles.insightFill} style={{ width: "88%" }} />
                </span>
              </li>
              <li>
                <div className={styles.insightRowTop}>
                  <span className={styles.insightLabel}>RAG retrieval</span>
                  <span className={styles.insightPct}>76%</span>
                </div>
                <span className={styles.insightTrack}>
                  <span className={styles.insightFill} style={{ width: "76%" }} />
                </span>
              </li>
              <li>
                <div className={styles.insightRowTop}>
                  <span className={styles.insightLabel}>Suggestion ranker</span>
                  <span className={styles.insightPct}>92%</span>
                </div>
                <span className={styles.insightTrack}>
                  <span className={styles.insightFill} style={{ width: "92%" }} />
                </span>
              </li>
            </ul>
          </section>
        </div>

        <section className={styles.tableSection} aria-label="Recent sessions">
          <div className={styles.tableHead}>
            <h2 className={styles.tableTitle}>Recent intelligent sessions</h2>
            <Link to="/analytics" className={styles.tableLink}>
              View historical archive
            </Link>
          </div>
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Session ID</th>
                  <th scope="col">Lead identity</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Duration</th>
                </tr>
              </thead>
              <tbody>
                {recentCalls.length > 0
                  ? recentCalls.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <Link to={`/conversations/${row.id}`} className={styles.sessionId}>
                            {row.id.slice(0, 8)}
                          </Link>
                        </td>
                        <td>
                          <div className={styles.leadCell}>
                            <span className={styles.leadAvatar}>LC</span>
                            <div>
                              <p className={styles.leadName}>Live call</p>
                              <p className={styles.leadSub}>{formatTimestamp(row.started_at)}</p>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span
                            className={
                              row.status === "ready"
                                ? styles.badgeOk
                                : row.status === "analyzing"
                                  ? styles.badgeNeutral
                                  : styles.badgeWarn
                            }
                          >
                            {row.status === "ready"
                              ? "Analyzed"
                              : row.status === "analyzing"
                                ? "Analyzing"
                                : row.status}
                          </span>
                        </td>
                        <td className={styles.duration}>{formatDuration(row.duration_sec)}</td>
                      </tr>
                    ))
                  : SESSIONS_PLACEHOLDER.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <span className={styles.sessionId}>{row.id}</span>
                        </td>
                        <td>
                          <div className={styles.leadCell}>
                            <span className={styles.leadAvatar}>{row.initials}</span>
                            <div>
                              <p className={styles.leadName}>{row.name}</p>
                              <p className={styles.leadSub}>{row.vertical}</p>
                            </div>
                          </div>
                        </td>
                        <td>
                          <span
                            className={
                              row.outcome === "converted"
                                ? styles.badgeOk
                                : row.outcome === "nurturing"
                                  ? styles.badgeNeutral
                                  : styles.badgeWarn
                            }
                          >
                            {row.outcome === "converted"
                              ? "Converted"
                              : row.outcome === "nurturing"
                                ? "Nurturing"
                                : "Unresponsive"}
                          </span>
                        </td>
                        <td className={styles.duration}>{row.duration}</td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
