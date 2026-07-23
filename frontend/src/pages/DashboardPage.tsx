/**
 * Landing page: the owner's 10-second answer to "how are my sales calls going,
 * and what needs my attention?". Every number comes from the analytics summary
 * endpoint — measured from real calls or AI-assessed with evidence.
 *
 * Every count is a drill-down: clicking a bar, pill, or band opens a modal
 * listing exactly those calls, and each call links to its full review page.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  audioStreamUrl,
  formatDuration,
  formatTimestamp,
  getAnalyticsSummary,
  getAudioToken,
  type AnalyticsCallRow,
  type AnalyticsSummary,
} from "../api/conversations";
import { downloadTranscriptTxt } from "../utils/downloadTranscript";
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
    note: "Right in the healthy range. Customers get room to talk.",
  },
  rep_heavy: {
    text: "Talking too much",
    note: "Best range is 35–55%. Try letting the customer talk more.",
  },
  prospect_heavy: {
    text: "Customer leads the talking",
    note: "Great listening. Make sure key questions still get asked.",
  },
};

function toneClass(tone: "good" | "warn" | "risk" | "neutral"): string {
  if (tone === "good") return styles.pillGood;
  if (tone === "warn") return styles.pillWarn;
  if (tone === "risk") return styles.pillRisk;
  return styles.pillNeutral;
}

type ModalState = {
  title: string;
  subtitle: string;
  rows: AnalyticsCallRow[];
  /** When set, rows show that signal's count + the customer's quoted words. */
  kind?: "positive" | "concerns";
} | null;

/** Modal listing a set of calls; every row links to that call's full review. */
function CallListModal({
  modal,
  onClose,
}: {
  modal: NonNullable<ModalState>;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className={styles.modalBackdrop} role="presentation" onClick={onClose}>
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-label={modal.title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.modalHead}>
          <div>
            <h2 className={styles.modalTitle}>{modal.title}</h2>
            <p className={styles.modalSub}>{modal.subtitle}</p>
          </div>
          <button ref={closeRef} type="button" className={styles.modalClose} onClick={onClose}>
            ✕
          </button>
        </div>
        {modal.rows.length > 0 ? (
          <ul className={styles.modalList}>
            {modal.rows.map((row) => {
              const outcome = OUTCOME_LABELS[row.outcome];
              const quotes =
                modal.kind === "positive"
                  ? row.interest_examples
                  : modal.kind === "concerns"
                    ? row.concern_examples
                    : [];
              return (
                <li key={row.id}>
                  <Link to={`/conversations/${row.id}`} className={styles.modalRow}>
                    <div className={styles.modalRowTop}>
                      <div className={styles.modalRowMain}>
                        <span className={styles.callId}>{row.id.slice(0, 8)}</span>
                        <span className={styles.modalWhen}>{formatTimestamp(row.started_at)}</span>
                      </div>
                      {modal.kind === "positive" ? (
                        <span className={`${styles.pill} ${styles.pillGood}`}>
                          {row.buying_signals} positive{" "}
                          {row.buying_signals === 1 ? "sign" : "signs"}
                        </span>
                      ) : modal.kind === "concerns" ? (
                        <span className={`${styles.pill} ${styles.pillRisk}`}>
                          {row.objections} {row.objections === 1 ? "concern" : "concerns"}
                        </span>
                      ) : (
                        <span className={`${styles.pill} ${toneClass(outcome.tone)}`}>
                          {outcome.text}
                        </span>
                      )}
                      <span className={styles.modalMeta}>
                        {row.interest_score != null ? `${row.interest_score}% interest` : "—"}
                      </span>
                      <span className={styles.modalMeta}>{formatDuration(row.duration_sec)}</span>
                      <span className={styles.modalChevron} aria-hidden="true">
                        ›
                      </span>
                    </div>
                    {quotes.length > 0 ? (
                      <ul className={styles.quoteList}>
                        {quotes.map((quote) => (
                          <li key={quote}>{quote}</li>
                        ))}
                      </ul>
                    ) : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className={styles.modalEmpty}>No calls in this group yet.</p>
        )}
      </div>
    </div>
  );
}

function clockFormat(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function AudioPlayerModal({
  conversationId,
  when,
  client,
  onClose,
}: {
  conversationId: string;
  when: string;
  client: string | null;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [muted, setMuted] = useState(false);

  useEffect(() => {
    closeRef.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    getAudioToken(conversationId)
      .then(({ token }) => {
        if (!cancelled) setSrc(audioStreamUrl(conversationId, token));
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Audio unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  function togglePlay() {
    const el = audioElRef.current;
    if (!el) return;
    if (el.paused) void el.play().catch(() => {});
    else el.pause();
  }

  function seek(value: number) {
    const el = audioElRef.current;
    if (!el) return;
    el.currentTime = value;
    setCurrentTime(value);
  }

  function toggleMute() {
    const el = audioElRef.current;
    if (!el) return;
    el.muted = !el.muted;
    setMuted(el.muted);
  }

  const progressPct = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className={styles.modalBackdrop} role="presentation" onClick={onClose}>
      <div
        className={styles.playerModal}
        role="dialog"
        aria-modal="true"
        aria-label={`Call recording — ${when}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.playerHead}>
          <div className={styles.playerHeadIcon} aria-hidden="true">
            <HeadphonesIcon />
          </div>
          <div className={styles.playerHeadText}>
            <h2 className={styles.playerTitle}>Call recording</h2>
            <p className={styles.playerSub}>
              {client ? `${client} · ${when}` : when}
            </p>
          </div>
          <button ref={closeRef} type="button" className={styles.modalClose} onClick={onClose}>
            ✕
          </button>
        </div>
        <div className={styles.playerBody}>
          {error ? (
            <p className={styles.modalEmpty}>{error}</p>
          ) : src ? (
            <>
              {/* eslint-disable-next-line jsx-a11y/media-has-caption -- a raw call recording has no captions to attach */}
              <audio
                ref={audioElRef}
                src={src}
                autoPlay
                onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
                onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => setIsPlaying(false)}
                className={styles.hiddenAudioEl}
              />
              <div className={styles.playerRow}>
                <button
                  type="button"
                  className={styles.playerPlayBtn}
                  onClick={togglePlay}
                  aria-label={isPlaying ? "Pause" : "Play"}
                >
                  {isPlaying ? <PauseIcon /> : <PlayIcon />}
                </button>
                <div className={styles.playerTrackCol}>
                  <input
                    type="range"
                    className={styles.playerRange}
                    style={{ "--played": `${progressPct}%` } as React.CSSProperties}
                    min={0}
                    max={duration || 0}
                    step={0.1}
                    value={currentTime}
                    onChange={(e) => seek(Number(e.target.value))}
                    aria-label="Seek"
                  />
                  <div className={styles.playerTimes}>
                    <span>{clockFormat(currentTime)}</span>
                    <span>{clockFormat(duration)}</span>
                  </div>
                </div>
                <button
                  type="button"
                  className={styles.playerMuteBtn}
                  onClick={toggleMute}
                  aria-label={muted ? "Unmute" : "Mute"}
                >
                  {muted ? <MutedIcon /> : <VolumeIcon />}
                </button>
              </div>
            </>
          ) : (
            <div className={styles.playerRow}>
              <div className={styles.playerLoadingBtn} aria-hidden="true" />
              <div className={styles.playerTrackCol}>
                <div className={styles.playerLoadingTrack} />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function HeadphonesIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
      <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
    </svg>
  );
}

function VolumeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 5 6 9H2v6h4l5 4z" />
      <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" />
    </svg>
  );
}

function MutedIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 5 6 9H2v6h4l5 4z" />
      <line x1="23" y1="9" x2="17" y2="15" />
      <line x1="17" y1="9" x2="23" y2="15" />
    </svg>
  );
}

export function DashboardPage() {
  const [range, setRange] = useState<Range>("30d");
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<ModalState>(null);

  const [player, setPlayer] = useState<{ id: string; when: string; client: string | null } | null>(
    null
  );

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

  const calls = useMemo(() => summary?.calls ?? [], [summary]);
  const callsById = useMemo(() => new Map(calls.map((c) => [c.id, c])), [calls]);
  const recentCalls = useMemo(() => calls.slice(0, 6), [calls]);
  const actionCalls = useMemo(
    () => calls.filter((c) => c.outcome === "follow_up" || c.outcome === "at_risk").slice(0, 5),
    [calls]
  );
  const maxVolume = useMemo(
    () => Math.max(...(summary?.weekly_volume ?? []).map((b) => b.count), 1),
    [summary]
  );

  const closeModal = useCallback(() => setModal(null), []);

  const openOutcomeModal = useCallback(
    (outcome: AnalyticsCallRow["outcome"], title: string) => {
      setModal({
        title,
        subtitle: "Click a call to open its full review",
        rows: calls.filter((c) => c.outcome === outcome),
      });
    },
    [calls]
  );

  const openBandModal = useCallback(
    (band: "likely" | "possible" | "unlikely", title: string) => {
      setModal({
        title,
        subtitle: "Click a call to open its full review",
        rows: calls.filter((c) => c.conversion_band === band),
      });
    },
    [calls]
  );

  const openBucketModal = useCallback(
    (label: string, callIds: string[]) => {
      setModal({
        title: `Calls in ${label}`,
        subtitle: "Click a call to open its full review",
        rows: callIds
          .map((id) => callsById.get(id))
          .filter((c): c is AnalyticsCallRow => Boolean(c)),
      });
    },
    [callsById]
  );

  const openSignalModal = useCallback(
    (kind: "positive" | "concerns") => {
      // Only calls that actually contain this signal, strongest first —
      // clicking "12 positive signs" must show exactly where those 12 live.
      const relevant = calls
        .filter((c) =>
          kind === "positive" ? c.buying_signals > 0 : c.objections > 0
        )
        .sort((a, b) =>
          kind === "positive" ? b.buying_signals - a.buying_signals : b.objections - a.objections
        );
      setModal({
        kind,
        title: kind === "positive" ? "Positive signs from customers" : "Concerns customers raised",
        subtitle:
          kind === "positive"
            ? `${relevant.length} ${relevant.length === 1 ? "call" : "calls"} where the customer showed real interest — with their own words`
            : `${relevant.length} ${relevant.length === 1 ? "call" : "calls"} where the customer pushed back — with their own words`,
        rows: relevant,
      });
    },
    [calls]
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
                  <button
                    type="button"
                    className={styles.heroValueBtn}
                    onClick={() => openOutcomeModal("qualified", "Strong leads")}
                  >
                    <span className={styles.heroValue}>
                      {pipeline?.qualified_calls ?? "—"}
                      <span className={styles.heroUnit}> strong leads</span>
                    </span>
                  </button>
                  <p className={styles.heroBody}>
                    Counted from what each customer actually said on the call. Click any number to
                    see the calls behind it.
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
                    <span className={styles.bandChips}>
                      <button
                        type="button"
                        className={styles.bandChip}
                        onClick={() => openBandModal("likely", "Calls likely to close")}
                      >
                        {summary?.conversion_bands.likely ?? 0} high
                      </button>
                      <button
                        type="button"
                        className={styles.bandChip}
                        onClick={() => openBandModal("possible", "Calls that might close")}
                      >
                        {summary?.conversion_bands.possible ?? 0} medium
                      </button>
                      <button
                        type="button"
                        className={styles.bandChip}
                        onClick={() => openBandModal("unlikely", "Calls unlikely to close")}
                      >
                        {summary?.conversion_bands.unlikely ?? 0} low
                      </button>
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
                  <button
                    type="button"
                    className={`${styles.pill} ${styles.pillOnDark} ${styles.pillBtn}`}
                    onClick={() => openOutcomeModal("qualified", "Strong leads")}
                  >
                    <i className={styles.dotGood} /> <strong>{pipeline?.qualified_calls ?? 0}</strong>{" "}
                    strong
                  </button>
                  <button
                    type="button"
                    className={`${styles.pill} ${styles.pillOnDark} ${styles.pillBtn}`}
                    onClick={() => openOutcomeModal("follow_up", "Calls that need a follow-up")}
                  >
                    <i className={styles.dotWarn} /> <strong>{pipeline?.follow_up_calls ?? 0}</strong>{" "}
                    need a follow-up
                  </button>
                  <button
                    type="button"
                    className={`${styles.pill} ${styles.pillOnDark} ${styles.pillBtn}`}
                    onClick={() => openOutcomeModal("at_risk", "Calls that may slip away")}
                  >
                    <i className={styles.dotRisk} /> <strong>{pipeline?.at_risk_calls ?? 0}</strong>{" "}
                    may slip away
                  </button>
                  <button
                    type="button"
                    className={`${styles.pill} ${styles.pillOnDark} ${styles.pillBtn}`}
                    onClick={() => openOutcomeModal("nurture", "Customers still deciding")}
                  >
                    <i className={styles.dotNeutral} /> <strong>{stillDeciding}</strong> still
                    deciding
                  </button>
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
                  <button
                    type="button"
                    className={styles.signalBtn}
                    onClick={() => openSignalModal("positive")}
                  >
                    <div className={styles.signalTop}>
                      <span>
                        <i className={styles.dotGood} /> Positive signs
                      </span>
                      <span className={styles.signalValue}>
                        {signals?.buying_signals_total ?? 0}
                      </span>
                    </div>
                    <div className={styles.signalTrack}>
                      <div
                        className={`${styles.signalFill} ${styles.signalFillGood}`}
                        style={{
                          width: `${((signals?.buying_signals_total ?? 0) / signalMax) * 100}%`,
                        }}
                      />
                    </div>
                  </button>
                </li>
                <li>
                  <button
                    type="button"
                    className={styles.signalBtn}
                    onClick={() => openSignalModal("concerns")}
                  >
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
                  </button>
                </li>
              </ul>
              <p className={styles.cardFoot}>
                Things customers said that show interest, like asking about price or a site visit,
                versus doubts they raised. Click either to see which calls.
              </p>
            </section>

            <section className={`${styles.card} ${styles.spanHero}`} aria-label="Calls over time">
              <div className={styles.chartHead}>
                <div>
                  <h2 className={styles.chartTitle}>Calls over time</h2>
                  <p className={styles.chartSub}>
                    Each bar is one {range === "7d" ? "day" : "week"}. Click a bar to see its calls.
                  </p>
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
                    const isOn = bucket.count > 0;
                    return (
                      <div key={bucket.label} className={styles.plotCol}>
                        <div className={styles.plotBarWrap}>
                          {isPeak ? (
                            <span className={styles.plotTag}>
                              {bucket.count} {bucket.count === 1 ? "call" : "calls"}
                            </span>
                          ) : null}
                          <button
                            type="button"
                            className={`${styles.plotBar} ${isOn ? styles.plotBarOn : ""} ${isPeak ? styles.plotBarHi : ""}`}
                            style={{ height: `${Math.max((bucket.count / maxVolume) * 100, 2)}%` }}
                            title={`${bucket.label}: ${bucket.count} ${bucket.count === 1 ? "call" : "calls"}. Click to view.`}
                            disabled={bucket.count === 0}
                            aria-label={`${bucket.label}: ${bucket.count} calls — view details`}
                            onClick={() => openBucketModal(bucket.label, bucket.call_ids)}
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
            <section className={`${styles.card} ${styles.spanHalf} ${styles.cardTight}`} aria-label="Needs your attention">
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
                    Aim for 6 or more. Questions uncover what the customer wants.
                  </p>
                </li>
              </ul>
            </section>

            {/* ── Row 4: recent calls ───────────────────────────────── */}
            <section className={`${styles.card} ${styles.spanFull} ${styles.cardTight} ${styles.recentCallsTight}`} aria-label="Recent calls">
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
                      <th scope="col">Rep</th>
                      <th scope="col">Client</th>
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
                            <div className={styles.callCell}>
                              <button
                                type="button"
                                className={styles.playBtn}
                                aria-label="Play call recording"
                                title={row.has_audio ? "Play" : "No audio for this call"}
                                disabled={!row.has_audio}
                                onClick={() =>
                                  setPlayer({
                                    id: row.id,
                                    when: formatTimestamp(row.started_at),
                                    client: row.caller_name?.trim() || null,
                                  })
                                }
                              >
                                <span className={styles.playIcon} aria-hidden="true">
                                  ▶
                                </span>
                              </button>
                              <div>
                                <Link to={`/conversations/${row.id}`} className={styles.callId}>
                                  {row.id.slice(0, 8)}
                                </Link>
                                <p className={styles.callWhen}>{formatTimestamp(row.started_at)}</p>
                              </div>
                            </div>
                          </td>
                          <td>{row.rep_label?.trim() || "—"}</td>
                          <td>{row.caller_name?.trim() || "—"}</td>
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
                          <td className={styles.duration}>
                            <div className={styles.durationCell}>
                              <span>{formatDuration(row.duration_sec)}</span>
                              <button
                                type="button"
                                className={styles.transcriptBtn}
                                onClick={() =>
                                  void downloadTranscriptTxt(row.id).catch((e) =>
                                    setError(e instanceof Error ? e.message : "Could not download transcript")
                                  )
                                }
                                title="Download transcript"
                              >
                                Transcript
                              </button>
                            </div>
                          </td>
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

      {modal ? <CallListModal modal={modal} onClose={closeModal} /> : null}
      {player ? (
        <AudioPlayerModal
          conversationId={player.id}
          when={player.when}
          client={player.client}
          onClose={() => setPlayer(null)}
        />
      ) : null}
    </div>
  );
}
