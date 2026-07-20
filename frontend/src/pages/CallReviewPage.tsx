import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { formatDuration, formatTimestamp } from "../api/conversations";
import appStyles from "../App.module.css";
import styles from "./CallReviewPage.module.css";
import { KpiCard, NextStepsPanel, ScoreRing } from "./callReview/charts";
import { REVIEW_TABS, type CurveKey, type ReviewTab } from "./callReview/constants";
import { asString } from "./callReview/json";
import { buildKpiStrip } from "./callReview/metrics";
import { CoachingTab } from "./callReview/tabs/CoachingTab";
import { HighlightsTab } from "./callReview/tabs/HighlightsTab";
import { IntentTab } from "./callReview/tabs/IntentTab";
import { TranscriptTab } from "./callReview/tabs/TranscriptTab";
import { useCallReview } from "./callReview/useCallReview";
import { statusLabel } from "./callReview/utils";

export function CallReviewPage() {
  const { id } = useParams<{ id: string }>();
  const { conversation, segments, suggestions, analysis, error, loading, reanalyzing, vm, handleReanalyze } =
    useCallReview(id);

  const [activeTab, setActiveTab] = useState<ReviewTab>("intent");
  const [summaryMode, setSummaryMode] = useState<"standard" | "short">("standard");
  const [engagementCurve, setEngagementCurve] = useState<CurveKey>("prospect_talk");
  const [transcriptQuery, setTranscriptQuery] = useState("");
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  function jumpToMoment(startMs: number) {
    setActiveTab("transcript");
    requestAnimationFrame(() => {
      document.getElementById(`seg-${startMs}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  if (!id) {
    return (
      <div className={appStyles.content}>
        <p>Missing conversation id.</p>
      </div>
    );
  }

  const status = analysis?.status ?? conversation?.status ?? "";
  const isAnalyzing =
    !loading &&
    !vm.hasReport &&
    (status === "analyzing" || status === "running" || conversation?.status === "analyzing");
  const isFailed = !loading && !vm.hasReport && status === "failed";
  const isWaiting = !loading && !vm.hasReport && !isAnalyzing && !isFailed && !error;
  const isDemo = analysis?.model === "seed-demo-api";

  return (
    <div className={appStyles.content}>
      <div className={`${appStyles.mainCol} ${styles.page}`}>
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>Post-call review</p>
            <h1 className={styles.title}>Call analysis</h1>
            <p className={styles.meta}>
              {formatTimestamp(conversation?.started_at)} · {formatDuration(conversation?.duration_sec)} ·{" "}
              <span className={`${styles.status} ${styles[`status_${analysis?.status ?? conversation?.status}`] ?? ""}`}>
                {statusLabel(analysis?.status ?? conversation?.status ?? "")}
              </span>
              {(analysis?.version ?? 0) > 1 ? (
                <span className={styles.metaChip} title="This call has been re-analyzed">
                  Analysis v{analysis?.version}
                </span>
              ) : null}
              {isDemo ? (
                <span className={styles.demoChip} title="Sample call created for demonstration — not a real customer">
                  Demo call
                </span>
              ) : null}
            </p>
          </div>
          <div className={styles.headerActions}>
            <Link to="/analytics" className={styles.linkBtn}>
              All calls
            </Link>
            <button type="button" className={styles.primaryBtn} onClick={() => void handleReanalyze()} disabled={reanalyzing}>
              {reanalyzing ? "Re-analyzing…" : "Re-analyze"}
            </button>
          </div>
        </header>

        {loading ? <p className={styles.loading}>Loading call…</p> : null}
        {error ? <p className={styles.error}>{error}</p> : null}

        {isAnalyzing ? (
          <section className={styles.statePanel} aria-live="polite">
            <span className={styles.stateSpinner} aria-hidden="true" />
            <h2 className={styles.stateTitle}>Reviewing this call…</h2>
            <p className={styles.stateBody}>
              The AI is reading the transcript. This usually takes under a minute — the page
              updates by itself when it's done.
            </p>
          </section>
        ) : null}

        {isFailed ? (
          <section className={`${styles.statePanel} ${styles.statePanelFailed}`}>
            <h2 className={styles.stateTitle}>The review didn't finish</h2>
            <p className={styles.stateBody}>
              {analysis?.error
                ? `Reason: ${analysis.error}`
                : "Something went wrong while reviewing this call."}{" "}
              The transcript is safe — trying again usually works.
            </p>
            <button
              type="button"
              className={styles.primaryBtn}
              onClick={() => void handleReanalyze()}
              disabled={reanalyzing}
            >
              {reanalyzing ? "Trying again…" : "Try again"}
            </button>
          </section>
        ) : null}

        {isWaiting ? (
          <section className={styles.statePanel}>
            <h2 className={styles.stateTitle}>
              {segments.length === 0 && conversation?.status !== "live"
                ? "Nothing to review"
                : "No review yet"}
            </h2>
            <p className={styles.stateBody}>
              {conversation?.status === "live"
                ? "This call is still in progress — the review starts automatically when it ends."
                : segments.length === 0
                  ? "This call ended before any conversation was captured, so there is nothing to analyze."
                  : "This call hasn't been reviewed. Use Re-analyze to run the review now."}
            </p>
          </section>
        ) : null}

        {!loading && vm.hasReport ? (
          <>
            <section className={styles.kpiStrip} aria-label="Measured call stats">
              {buildKpiStrip(vm).map((kpi) => (
                <KpiCard
                  key={kpi.key}
                  label={kpi.label}
                  value={kpi.value}
                  unit={kpi.unit}
                  badge={kpi.badge}
                  badgeTone={kpi.badgeTone}
                  timeline={kpi.curve}
                  chartColor={kpi.color}
                  chartCaption={kpi.caption}
                  spikeIndices={"spikes" in kpi ? kpi.spikes : undefined}
                />
              ))}
            </section>

            <section className={styles.overviewPanel}>
              <div className={styles.overviewMain}>
                <div className={styles.card}>
                  <div className={styles.summaryHead}>
                    <h2>Summary</h2>
                    <div className={styles.summaryToggle} role="group" aria-label="Summary length">
                      <button
                        type="button"
                        className={summaryMode === "standard" ? styles.toggleActive : ""}
                        onClick={() => setSummaryMode("standard")}
                      >
                        Standard
                      </button>
                      <button
                        type="button"
                        className={summaryMode === "short" ? styles.toggleActive : ""}
                        onClick={() => setSummaryMode("short")}
                      >
                        Short
                      </button>
                    </div>
                  </div>
                  <p className={styles.summaryText}>
                    {summaryMode === "short" ? vm.shortSummary : vm.executiveSummary}
                  </p>
                  {vm.clientIntent.primary_intent ? (
                    <span className={styles.intentPill}>
                      {asString(vm.clientIntent.primary_intent).replace(/_/g, " ")}
                    </span>
                  ) : null}
                  {vm.clientIntent.conversion_rationale ? (
                    <p className={styles.heroRationale}>
                      <strong>Conversion outlook:</strong> {asString(vm.clientIntent.conversion_rationale)}
                    </p>
                  ) : null}
                </div>

                <div className={styles.overviewRings}>
                  <ScoreRing
                    value={vm.interestScore}
                    label="Client interest"
                    sublabel={`AI assessed · ${vm.engagement.replace(/_/g, " ")}`}
                    tone="teal"
                    size={108}
                  />
                  <ScoreRing
                    value={vm.conversionPct}
                    label="Conversion likelihood"
                    sublabel={`AI assessed${vm.conversionLikelihood ? ` · ${vm.conversionLikelihood}` : ""}`}
                    tone="accent"
                    size={108}
                  />
                  <ScoreRing
                    value={vm.dealHealth}
                    label="Deal health"
                    sublabel="Avg of interest + conversion"
                    tone="amber"
                    size={108}
                  />
                </div>
              </div>

              {vm.nextSteps.length > 0 ? <NextStepsPanel steps={vm.nextSteps} /> : null}
            </section>

            <nav className={styles.tabBar} aria-label="Call review sections">
              {REVIEW_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  className={`${styles.tabBtn} ${activeTab === tab.id ? styles.tabBtnActive : ""}`}
                  onClick={() => setActiveTab(tab.id)}
                  aria-selected={activeTab === tab.id}
                >
                  {tab.label}
                </button>
              ))}
            </nav>

            <div className={styles.tabPanel}>
              {activeTab === "intent" ? (
                <IntentTab vm={vm} engagementCurve={engagementCurve} onEngagementCurveChange={setEngagementCurve} />
              ) : null}
              {activeTab === "coaching" ? <CoachingTab vm={vm} /> : null}
              {activeTab === "highlights" ? <HighlightsTab vm={vm} onJumpToMoment={jumpToMoment} /> : null}
              {activeTab === "transcript" ? (
                <TranscriptTab
                  segments={segments}
                  suggestions={suggestions}
                  conversation={conversation}
                  query={transcriptQuery}
                  onQueryChange={setTranscriptQuery}
                  panelRef={transcriptRef}
                />
              ) : null}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
