/**
 * View model for the Call Review page.
 *
 * The server is the single source of truth: every number here is either
 * MEASURED by the backend from transcript timestamps (curves, glance stats,
 * talk ratio) or AI-ASSESSED with cited evidence (interest, conversion,
 * phase sentiment). This file only reads and clamps — it never re-derives
 * or invents values. Missing data renders as missing, not as a guess.
 */

import { formatDuration } from "../../api/conversations";
import type { ConversationSummary } from "../../api/conversations";
import { PHASE_KEYS, PHASE_LABELS, type CurveKey } from "./constants";
import { asArray, asNumber, asRecord, asString } from "./json";

function clampPct(value: number): number {
  return Math.min(100, Math.max(0, Math.round(value)));
}

export function scoreTone(score: number): "high" | "mid" | "low" {
  if (score >= 70) return "high";
  if (score >= 45) return "mid";
  return "low";
}

export function scoreBadge(score: number): string {
  if (score >= 70) return "Good";
  if (score >= 45) return "Okay";
  return "Low";
}

export type CallGlance = {
  durationLabel: string;
  repPct: number;
  prospectPct: number;
  repTalkLabel: string;
  prospectTalkLabel: string;
  questions: number;
  prospectQuestions: number;
};

export type SentimentPhase = { label: string; score: number; note: string; quote: string };

export type MeasuredCurves = Record<CurveKey, number[]>;

export type CallReviewView = ReturnType<typeof buildCallReviewView>;

export function buildCallReviewView(
  report: Record<string, unknown>,
  metrics: Record<string, unknown>,
  conversation: ConversationSummary | null,
  analysisStatus?: string
) {
  const clientIntent = asRecord(report.client_intent);
  const repComm = asRecord(report.rep_communication);
  const talkRatio = asRecord(repComm.talk_listen_ratio ?? metrics.talk_listen_ratio);
  const sentiment = asRecord(report.sentiment_trajectory);

  // AI-assessed scores — the backend validates and rescales them; we only clamp.
  const interestScore = clampPct(asNumber(clientIntent.interest_score, 0));
  const conversionPct = clampPct(asNumber(clientIntent.conversion_probability_pct, 0));

  // Measured five-point curves, computed server-side from transcript timestamps.
  const curveRows = asRecord(metrics.engagement_curves);
  const curveFrom = (key: CurveKey): number[] =>
    asArray(curveRows[key]).map((row) => clampPct(asNumber(asRecord(row).score)));
  const curves: MeasuredCurves = {
    prospect_talk: curveFrom("prospect_talk"),
    prospect_questions: curveFrom("prospect_questions"),
    objections: curveFrom("objections"),
  };

  // AI-assessed phase sentiment, each score backed by a transcript quote.
  const phaseScores = asRecord(metrics.phase_scores);
  const sentimentPhases: SentimentPhase[] = PHASE_LABELS.map((label, i) => {
    const key = PHASE_KEYS[i];
    return {
      label,
      score: clampPct(asNumber(phaseScores[key], asNumber(sentiment[`${key}_score`], 0))),
      note: asString(sentiment[key]),
      quote: asString(sentiment[`${key}_quote`]),
    };
  });

  const glanceRaw = asRecord(metrics.call_glance);
  const durationSec =
    asNumber(glanceRaw.total_duration_sec, -1) >= 0
      ? asNumber(glanceRaw.total_duration_sec)
      : conversation?.duration_sec ?? 0;
  const callGlance: CallGlance = {
    durationLabel: asString(glanceRaw.total_duration_label) || formatDuration(durationSec),
    repPct: asNumber(glanceRaw.rep_talk_pct, asNumber(talkRatio.rep_pct)),
    prospectPct: asNumber(glanceRaw.prospect_talk_pct, asNumber(talkRatio.prospect_pct)),
    repTalkLabel: asString(glanceRaw.rep_talk_label) || "—",
    prospectTalkLabel: asString(glanceRaw.prospect_talk_label) || "—",
    questions: asNumber(glanceRaw.questions_asked),
    prospectQuestions: asNumber(glanceRaw.prospect_questions),
  };

  const objections = asArray(clientIntent.objections);
  const executiveSummary = asString(report.executive_summary);
  const firstSentence = executiveSummary.split(/(?<=[.!?])\s+/)[0] ?? executiveSummary;

  return {
    clientIntent,
    repComm,
    interestScore,
    conversionPct,
    engagement: asString(clientIntent.engagement_level, scoreTone(interestScore)),
    conversionLikelihood: asString(clientIntent.conversion_likelihood).replace(/_/g, " "),
    repPct: callGlance.repPct,
    prospectPct: callGlance.prospectPct,
    paceWpm: asNumber(repComm.pace_wpm ?? metrics.rep_wpm),
    fillerPct: asNumber(repComm.filler_rate_pct ?? metrics.rep_filler_rate_pct),
    questions: asNumber(repComm.questions_asked ?? metrics.rep_questions_asked),
    topicBars: asArray(report.topics)
      .slice(0, 5)
      .map((t) => {
        const raw = asRecord(t);
        return {
          label: asString(raw.name, "Topic"),
          value: clampPct(asNumber(raw.weight) * 100),
        };
      }),
    curves,
    objectionSpikes: curves.objections
      .map((score, i) => (score > 0 ? i : -1))
      .filter((i) => i >= 0),
    callGlance,
    coachingInsight: asString(metrics.coaching_insight),
    sentimentPhases,
    buyingSignals: asArray(clientIntent.buying_signals),
    objections,
    pivotal: asArray(report.pivotal_moments),
    nextSteps: asArray(report.next_steps),
    coaching: asArray(repComm.coaching_recommendations),
    strengths: asArray<string>(repComm.strengths),
    dealHealth: Math.round((interestScore + conversionPct) / 2),
    hasReport: Boolean(executiveSummary || analysisStatus === "ready"),
    executiveSummary,
    shortSummary: firstSentence.length > 220 ? `${firstSentence.slice(0, 217)}…` : firstSentence,
  };
}

/** Top-strip KPI cards — all three are measured values, not model guesses. */
export function buildKpiStrip(vm: CallReviewView) {
  const talk = vm.callGlance.prospectPct;
  return [
    {
      key: "prospect_talk" as const,
      label: "Prospect talk share",
      value: talk,
      unit: "%",
      badge: talk >= 45 ? "Healthy" : talk > 0 ? "Rep-heavy" : "",
      badgeTone: talk >= 45 ? ("high" as const) : ("low" as const),
      curve: vm.curves.prospect_talk,
      color: "teal" as const,
      caption: "Talk share by call phase",
    },
    {
      key: "prospect_questions" as const,
      label: "Prospect questions",
      value: vm.callGlance.prospectQuestions,
      unit: "",
      badge: "",
      badgeTone: "mid" as const,
      curve: vm.curves.prospect_questions,
      color: "accent" as const,
      caption: "Questions asked by phase",
    },
    {
      key: "objections" as const,
      label: "Objections raised",
      value: vm.objections.length,
      unit: "",
      badge: "",
      badgeTone: "mid" as const,
      curve: vm.curves.objections,
      color: "amber" as const,
      caption: "Objection intensity by phase",
      spikes: vm.objectionSpikes,
    },
  ];
}
