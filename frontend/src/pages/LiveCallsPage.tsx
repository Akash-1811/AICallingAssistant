import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { authHeaders, updateCallerDetails } from "../api/conversations";
import type { AssistantWsApi } from "../hooks/useAssistantWs";
import { useTranscriptPictureInPicture } from "../hooks/useTranscriptPictureInPicture";
import { buildRealtimeView } from "../realtime";
import { SuggestionPanel } from "../components/SuggestionPanel";
import { TranscriptFeed } from "../components/TranscriptFeed";
import type { AnswerDoneMessage } from "../types";
import styles from "../App.module.css";

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60).toString().padStart(2, "0");
  const s = (seconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

// Deepgram locks the call to one language mode once it connects — it can't
// switch mid-call — so this is picked before Start Session, not during.
// "multi" code-switches English + Hindi live; the rest are single-language
// models, so mixing in English mid-call will transcribe poorly for those.
const CALL_LANGUAGE_OPTIONS: { value: string; label: string }[] = [
  { value: "multi", label: "English + Hindi (mixed)" },
  { value: "mr", label: "Marathi" },
  { value: "gu", label: "Gujarati" },
  { value: "ta", label: "Tamil" },
  { value: "te", label: "Telugu" },
  { value: "kn", label: "Kannada" },
  { value: "bn", label: "Bengali" },
];

function CallLanguageSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className={styles.callLanguagePicker}>
      <span className={styles.callLanguageLabel}>Call language</span>
      <select
        className={styles.callLanguageSelect}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {CALL_LANGUAGE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function LiveCallsPage() {
  const {
    status,
    error,
    messages,
    elapsedSeconds,
    connect,
    disconnect,
    sessionId,
    lastEndedSessionId,
    speakers,
    leadSpeakerId,
  } = useOutletContext<AssistantWsApi>();

  const [callLanguage, setCallLanguage] = useState("multi");
  const [manualQuestion, setManualQuestion] = useState("");
  const [manualAnswer, setManualAnswer] = useState("");
  const [manualLoading, setManualLoading] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualAnswerModalOpen, setManualAnswerModalOpen] = useState(false);
  const answerModalCloseRef = useRef<HTMLButtonElement>(null);

  const [endCallModalOpen, setEndCallModalOpen] = useState(false);
  const [endingSessionId, setEndingSessionId] = useState<string | null>(null);
  const [callerName, setCallerName] = useState("");
  const [callerPhone, setCallerPhone] = useState("");
  const [callerAddress, setCallerAddress] = useState("");
  const [callNotes, setCallNotes] = useState("");
  const [callerSaving, setCallerSaving] = useState(false);
  const [callerSaveError, setCallerSaveError] = useState<string | null>(null);

  const isLive = status === "live";
  const isBusy = status === "connecting";
  const elapsed = formatElapsed(elapsedSeconds);

  const { pipSupported, pipOpen, openPip } = useTranscriptPictureInPicture({
    active: isLive,
    messages,
    elapsedLabel: elapsed,
  });

  const realtimeView = useMemo(() => buildRealtimeView(messages), [messages]);
  const allSuggestions = realtimeView.completedAnswers;
  const latestSuggestion = (allSuggestions.at(-1) ?? null) as AnswerDoneMessage | null;

  // Real live stats measured from the transcript — no synthetic scores.
  const liveStats = useMemo(() => {
    if (!isLive) return null;
    let repWords = 0;
    let customerWords = 0;
    let customerQuestions = 0;
    for (const m of messages) {
      if (m.type !== "transcript_final") continue;
      const text = m.text.trim();
      const words = text.split(/\s+/).filter(Boolean).length;
      if (leadSpeakerId != null && m.speaker === leadSpeakerId) {
        customerWords += words;
        // English + Hindi (romanized and Devanagari) question openers — calls are multilingual.
        if (
          /\?$/.test(text) ||
          /^(what|which|where|when|why|how|who|can|could|would|should|is|are|do|does|did|will|kya|kaise|kahan|kab|kyun|kyu|kaun|kitna|kitni|kitne|क्या|कैसे|कहाँ|कहां|कब|क्यों|कौन|कितना|कितनी|कितने)\b/i.test(text)
        ) {
          customerQuestions += 1;
        }
      } else {
        repWords += words;
      }
    }
    const total = repWords + customerWords;
    if (total === 0) return null;
    const repPct = Math.round((100 * repWords) / total);
    return { repPct, customerPct: 100 - repPct, customerQuestions };
  }, [isLive, messages, leadSpeakerId]);

  const strategyTip = useMemo(() => {
    if (!isLive) {
      return {
        lead: "Start a session",
        rest: " to unlock live coaching cues aligned with your knowledge base.",
      };
    }
    if (allSuggestions.length === 0) {
      return {
        lead: "Let the prospect finish",
        rest: ". Suggestions sharpen after a full thought.",
      };
    }
    return {
      lead: "Stay concise",
      rest: ". Pair the live transcript with the primary card and cite sources when challenged.",
    };
  }, [isLive, allSuggestions.length]);

  const talkInsight = useMemo(() => {
    if (!liveStats) return null;
    return (
      <p className={styles.sentimentInsight}>
        {liveStats.repPct > 65 ? (
          <>
            You're doing most of the talking. Pause and ask an{" "}
            <strong className={styles.sentimentKeyword}>open question</strong> so the customer can share priorities.
          </>
        ) : (
          <>
            Healthy balance. The customer is talking. Keep{" "}
            <strong className={styles.sentimentKeyword}>listening</strong> and answer what they actually ask.
          </>
        )}
      </p>
    );
  }, [liveStats]);

  useEffect(() => {
    if (!manualAnswerModalOpen) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, [manualAnswerModalOpen]);

  useEffect(() => {
    if (!manualAnswerModalOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setManualAnswerModalOpen(false);
    };
    window.addEventListener("keydown", onKey);
    const raf = requestAnimationFrame(() => answerModalCloseRef.current?.focus());
    return () => {
      window.removeEventListener("keydown", onKey);
      cancelAnimationFrame(raf);
    };
  }, [manualAnswerModalOpen]);

  function handleStart() {
    void connect("", { captureTabAudio: true, language: callLanguage });
  }

  function handleEndCall() {
    // Capture the id being ended now — disconnect() clears sessionId on its
    // next render, so waiting for lastEndedSessionId here would be stale.
    setEndingSessionId(sessionId);
    disconnect();
    setCallerName("");
    setCallerPhone("");
    setCallerAddress("");
    setCallNotes("");
    setCallerSaveError(null);
    setEndCallModalOpen(true);
  }

  async function handleSaveCallerDetails() {
    const name = callerName.trim();
    if (!endingSessionId || !name || callerSaving) return;
    setCallerSaving(true);
    setCallerSaveError(null);
    try {
      await updateCallerDetails(endingSessionId, {
        caller_name: name,
        caller_phone: callerPhone.trim() || undefined,
        caller_address: callerAddress.trim() || undefined,
        call_notes: callNotes.trim() || undefined,
      });
      setEndCallModalOpen(false);
    } catch (e) {
      setCallerSaveError(e instanceof Error ? e.message : "Couldn't save — try again.");
    } finally {
      setCallerSaving(false);
    }
  }

  async function handleManualAsk() {
    const q = manualQuestion.trim();
    if (!q || manualLoading) return;
    setManualLoading(true);
    setManualAnswerModalOpen(false);
    setManualError(null);
    setManualAnswer("");
    try {
      const res = await fetch("/api/v1/ask", {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const data = (await res.json()) as {
        answer?: string;
        detail?: unknown;
      };
      if (!res.ok) {
        const d = data.detail;
        let msg = res.statusText;
        if (typeof d === "string") msg = d;
        else if (Array.isArray(d) && d[0] && typeof d[0] === "object" && d[0] !== null && "msg" in d[0]) {
          msg = String((d[0] as { msg: string }).msg);
        }
        throw new Error(msg || "Request failed");
      }
      setManualAnswer(data.answer ?? "");
      setManualAnswerModalOpen(true);
    } catch (e) {
      setManualError(e instanceof Error ? e.message : "Something went wrong.");
      setManualAnswerModalOpen(true);
    } finally {
      setManualLoading(false);
    }
  }

  return (
    <>
      <div className={`${styles.content} ${styles.contentLive}`}>
        <div className={`${styles.mainCol} ${styles.mainColLive}`}>
          <div className={styles.liveStrip}>
            <div className={styles.liveStripLeft}>
              <span className={`${styles.statusOrb} ${isLive ? styles.statusOrbLive : ""}`} aria-hidden="true" />
              <div className={styles.liveStripTitles}>
                <p className={styles.liveStripKicker}>Live call interface</p>
                <p className={styles.liveStripSession}>
                  <span className={styles.metaLabel}>Session ID</span>
                  <span className={styles.metaValue}>
                    {sessionId ? `${sessionId.slice(0, 10)}…` : isBusy ? "Connecting…" : "—"}
                  </span>
                </p>
              </div>
            </div>
            <div className={styles.liveStripRight}>
              {isLive && pipSupported && (
                <button
                  type="button"
                  className={styles.pipPopoutBtn}
                  onClick={() => void openPip()}
                  aria-pressed={pipOpen}
                  title="Open a small always-on-top window with transcript and AI suggestions (Chrome or Edge)"
                >
                  <PipGlyph aria-hidden="true" />
                  {pipOpen ? "Pip open" : "Pop out"}
                </button>
              )}
              {isLive ? (
                <span className={styles.livePill}>Live · {elapsed}</span>
              ) : isBusy ? (
                <span className={styles.idlePill}>Connecting</span>
              ) : (
                <span className={styles.idlePill}>Ready</span>
              )}
            </div>
          </div>

          {!isLive && lastEndedSessionId ? (
            <div className={styles.postCallBanner}>
              <p>
                Call saved. Post-call analysis runs automatically — open the review when ready.
              </p>
              <Link to={`/conversations/${lastEndedSessionId}`} className={styles.postCallLink}>
                View call analysis
              </Link>
            </div>
          ) : null}

          {/* The Start/End call control normally lives in the right rail below,
              but that rail hides below 1060px to make room for the transcript —
              taking the only way to start a call with it. This copy fills that
              gap; it's hidden again once the rail has room to show its own. */}
          <div className={styles.mobileCallControl}>
            {isLive ? (
              <div className={styles.liveCallPill}>
                <div className={styles.livePillLeft}>
                  <span className={styles.livePillDot} aria-hidden="true" />
                  <span className={styles.livePillText} aria-live="polite">
                    Live call <span className={styles.livePillSep}>|</span> {elapsed}
                  </span>
                </div>
                <button
                  type="button"
                  className={styles.liveEndCallBtn}
                  onClick={handleEndCall}
                  aria-label="End call"
                >
                  <HangupPhoneIcon />
                </button>
              </div>
            ) : (
              <>
                <CallLanguageSelect value={callLanguage} onChange={setCallLanguage} />
                <button
                  className={styles.startBtn}
                  type="button"
                  onClick={handleStart}
                  disabled={isBusy}
                  aria-busy={isBusy}
                >
                  <MicIcon />
                  {isBusy ? "Connecting…" : "Start Session"}
                </button>
              </>
            )}
            {error && <p className={styles.errorMsg}>{error}</p>}
          </div>

          <div className={styles.transcriptBlock}>
            <TranscriptFeed messages={messages} />
          </div>

          <div className={styles.suggestionBlock}>
            <SuggestionPanel
              suggestion={latestSuggestion}
              liveAnswer={realtimeView.liveAnswer}
              isLive={isLive}
              manualQuestion={manualQuestion}
              onManualQuestionChange={setManualQuestion}
              manualLoading={manualLoading}
              manualAnswer={manualAnswer}
              manualError={manualError}
              onManualAsk={() => void handleManualAsk()}
              onOpenManualAnswerModal={() => setManualAnswerModalOpen(true)}
            />
          </div>
        </div>

        <aside className={styles.rightPanel}>
          <div className={styles.callHeader}>
            {isLive ? (
              <div className={styles.liveCallPill}>
                <div className={styles.livePillLeft}>
                  <span className={styles.livePillDot} aria-hidden="true" />
                  <span className={styles.livePillText} aria-live="polite">
                    Live call <span className={styles.livePillSep}>|</span> {elapsed}
                  </span>
                </div>
                <LiveWaveform />
                <button
                  type="button"
                  className={styles.liveEndCallBtn}
                  onClick={handleEndCall}
                  aria-label="End call"
                >
                  <HangupPhoneIcon />
                </button>
              </div>
            ) : (
              <>
                <CallLanguageSelect value={callLanguage} onChange={setCallLanguage} />
                <button
                  className={styles.startBtn}
                  type="button"
                  onClick={handleStart}
                  disabled={isBusy}
                  aria-busy={isBusy}
                >
                  <MicIcon />
                  {isBusy ? "Connecting…" : "Start Session"}
                </button>
              </>
            )}
            {error && <p className={styles.errorMsg}>{error}</p>}
          </div>

          <div className={styles.profileCard}>
            <div className={styles.profileAvatarSquare} aria-hidden="true">
              {isLive ? (leadSpeakerId === 1 ? "C" : "L") : "·"}
            </div>
            <div className={styles.profileText}>
              <p className={styles.profileName}>
                {isLive
                  ? leadSpeakerId != null
                    ? "Customer"
                    : "Waiting for customer audio"
                  : "No active call"}
              </p>
              <p className={styles.profileRole}>
                {isLive
                  ? sessionId
                    ? `${sessionId.slice(0, 8).toUpperCase()} · ON CALL`
                    : "LIVE SESSION"
                  : "POWERED BY HUBCODE"}
              </p>
            </div>
          </div>

          <div className={styles.sentimentCard}>
            <p className={styles.sentimentTitle}>Talk balance</p>
            {liveStats ? (
              <>
                <p className={styles.sentimentValue}>
                  <span className={styles.sentimentNumber}>{liveStats.customerPct}%</span>
                  <span className={styles.sentimentPositiveLabel}>Customer</span>
                </p>
                <div className={styles.sentimentTrack}>
                  <div className={styles.sentimentFill} style={{ width: `${liveStats.customerPct}%` }} />
                </div>
                <p className={styles.sentimentInsight}>
                  {liveStats.customerQuestions} customer question{liveStats.customerQuestions === 1 ? "" : "s"} ·{" "}
                  {allSuggestions.length} suggestion{allSuggestions.length === 1 ? "" : "s"} delivered
                </p>
                {talkInsight}
              </>
            ) : (
              <p className={styles.sentimentPlaceholder}>Stats appear once the conversation starts.</p>
            )}
          </div>

          <div className={styles.accountCard}>
            <p className={styles.accountTitle}>Account history</p>
            <ul className={styles.accountHistoryList}>
              <li className={styles.accountHistoryItem}>
                <span className={styles.accountHistoryIcon}>
                  <HistoryGlyph />
                </span>
                <div className={styles.accountHistoryCopy}>
                  <p className={styles.accountHistoryItemTitle}>Session momentum</p>
                  <p className={styles.accountHistoryItemSub}>
                    {allSuggestions.length} coaching cue{allSuggestions.length === 1 ? "" : "s"} this call
                  </p>
                </div>
              </li>
              <li className={styles.accountHistoryItem}>
                <span className={styles.accountHistoryIcon}>
                  <StakeholdersGlyph />
                </span>
                <div className={styles.accountHistoryCopy}>
                  <p className={styles.accountHistoryItemTitle}>Key stakeholders</p>
                  <p className={styles.accountHistoryItemSub}>
                    {speakers.length > 0
                      ? `${speakers.length} voice channel${speakers.length === 1 ? "" : "s"} detected`
                      : "Voices appear as the call progresses"}
                  </p>
                </div>
              </li>
              <li className={styles.accountHistoryItem}>
                <span className={styles.accountHistoryIcon}>
                  <EngagementGlyph />
                </span>
                <div className={styles.accountHistoryCopy}>
                  <p className={styles.accountHistoryItemTitle}>Engagement footprint</p>
                  <p className={styles.accountHistoryItemSub}>
                    {isLive ? `${elapsed} on the line · ${messages.length} events` : "Start a session to populate"}
                  </p>
                </div>
              </li>
            </ul>
          </div>

          <div className={styles.strategyCard}>
            <div className={styles.strategyHead}>
              <StrategyPinIcon />
              <span>AI strategy note</span>
            </div>
            <p className={styles.strategyBody}>
              <em className={styles.strategyPull}>{strategyTip.lead}</em>
              {strategyTip.rest}
            </p>
          </div>
        </aside>
      </div>

      {manualAnswerModalOpen && (manualAnswer || manualError) && (
        <div
          className={styles.answerModalBackdrop}
          role="presentation"
          onClick={() => setManualAnswerModalOpen(false)}
        >
          <div
            className={styles.answerModal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="manual-answer-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.answerModalTop}>
              <h2 id="manual-answer-modal-title" className={styles.answerModalTitle}>
                Answer
              </h2>
              <button
                ref={answerModalCloseRef}
                type="button"
                className={styles.answerModalClose}
                onClick={() => setManualAnswerModalOpen(false)}
                aria-label="Close"
              >
                <ModalCloseIcon />
              </button>
            </div>
            <div
              className={`${styles.answerModalBody} ${manualError ? styles.manualOutputError : ""}`}
            >
              {manualError ?? manualAnswer}
            </div>
            <p className={styles.answerModalFooterHint}>Press Esc to close</p>
          </div>
        </div>
      )}

      {endCallModalOpen && (
        <div
          className={styles.answerModalBackdrop}
          role="presentation"
          onClick={() => setEndCallModalOpen(false)}
        >
          <div
            className={styles.answerModal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="end-call-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.callEndedHead}>
              <div className={styles.callEndedIcon} aria-hidden="true">
                <CheckCircleIcon />
              </div>
              <div className={styles.callEndedHeadText}>
                <h2 id="end-call-modal-title" className={styles.callEndedTitle}>
                  Call ended
                </h2>
                <p className={styles.callEndedSub}>
                  Add the customer's details so this call is easy to find later.
                </p>
              </div>
              <button
                type="button"
                className={styles.answerModalClose}
                onClick={() => setEndCallModalOpen(false)}
                aria-label="Close"
              >
                <ModalCloseIcon />
              </button>
            </div>
            <div className={styles.callerModalBody}>
              <label className={styles.apiField}>
                <span className={styles.apiLabel}>
                  Name <span className={styles.requiredMark}>Required</span>
                </span>
                <input
                  className={styles.apiInput}
                  type="text"
                  value={callerName}
                  onChange={(e) => setCallerName(e.target.value)}
                  placeholder="Customer's name"
                  autoFocus
                />
              </label>
              <label className={styles.apiField}>
                <span className={styles.apiLabel}>Contact number</span>
                <input
                  className={styles.apiInput}
                  type="tel"
                  value={callerPhone}
                  onChange={(e) => setCallerPhone(e.target.value)}
                  placeholder="Optional"
                />
              </label>
              <label className={styles.apiField}>
                <span className={styles.apiLabel}>Address</span>
                <input
                  className={styles.apiInput}
                  type="text"
                  value={callerAddress}
                  onChange={(e) => setCallerAddress(e.target.value)}
                  placeholder="Optional"
                />
              </label>
              <label className={styles.apiField}>
                <span className={styles.apiLabel}>Notes</span>
                <textarea
                  className={styles.callerNotesInput}
                  value={callNotes}
                  onChange={(e) => setCallNotes(e.target.value)}
                  placeholder="Anything worth remembering about this call — optional"
                  rows={3}
                />
              </label>
              {callerSaveError && <p className={styles.errorMsg}>{callerSaveError}</p>}
            </div>
            <div className={styles.callerModalActions}>
              <button
                type="button"
                className={styles.callerSkipBtn}
                onClick={() => setEndCallModalOpen(false)}
              >
                Skip
              </button>
              <button
                type="button"
                className={styles.callerSaveBtn}
                onClick={() => void handleSaveCallerDetails()}
                disabled={!callerName.trim() || callerSaving}
              >
                {callerSaving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function PipGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="4" width="12" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.8" />
      <rect x="11" y="9" width="10" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

function ModalCloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function StrategyPinIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 22s8-4.5 8-11a8 8 0 1 0-16 0c0 6.5 8 11 8 11z"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="11" r="2.5" fill="var(--accent)" />
    </svg>
  );
}

function HistoryGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
      <path d="M12 7v5l4 2" />
    </svg>
  );
}

function StakeholdersGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="7" r="3" />
      <path d="M5 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2" />
      <circle cx="19" cy="11" r="2" />
      <path d="M21 21v-1a3 3 0 0 0-2-2.83" />
      <circle cx="5" cy="11" r="2" />
      <path d="M3 21v-1a3 3 0 0 1 2-2.83" />
    </svg>
  );
}

function EngagementGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  );
}

function MicIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 2a3 3 0 0 1 3 3v7a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="22" />
    </svg>
  );
}

function HangupPhoneIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const LIVE_WAVE_HEIGHTS = [5, 12, 7, 16, 9, 14, 6, 11, 8, 15, 7, 10];

function LiveWaveform() {
  return (
    <div className={styles.liveWaveform} aria-hidden="true">
      {LIVE_WAVE_HEIGHTS.map((h, i) => (
        <span
          key={i}
          className={styles.liveWaveBar}
          style={{ height: h, animationDelay: `${i * 0.06}s` }}
        />
      ))}
    </div>
  );
}
