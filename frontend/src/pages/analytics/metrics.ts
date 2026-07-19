import type { AnalyticsSummary } from "../../api/conversations";
import { WIN_BANDS } from "./constants";

export function formatScore(value: number | null | undefined): string {
  if (value == null || value < 0) return "—";
  return `${value}`;
}

export function withPercent<T extends { label: string; count: number }>(counts: T[]) {
  const total = counts.reduce((sum, row) => sum + row.count, 0);
  return counts.map((row) => ({
    ...row,
    pct: total ? Math.round((row.count / total) * 100) : 0,
  }));
}

export function buildVolumeBars(summary: AnalyticsSummary | null) {
  const weeks = summary?.weekly_volume ?? [];
  const max = Math.max(...weeks.map((week) => week.count), 1);
  return weeks.map((week) => ({
    label: week.label,
    count: week.count,
    pct: weeks.length ? Math.round((week.count / max) * 100) : 0,
  }));
}

export function buildWinBands(summary: AnalyticsSummary | null) {
  const bands = summary?.conversion_bands;
  return withPercent(
    WIN_BANDS.map((band) => ({
      ...band,
      count: bands?.[band.id] ?? 0,
    })),
  );
}

export function buildSignalBars(summary: AnalyticsSummary | null) {
  const balance = summary?.signal_balance;
  if (!balance) return [];
  const max = Math.max(balance.buying_signals_total, balance.objections_total, 1);
  return [
    {
      id: "buying" as const,
      label: "Showed interest",
      count: balance.buying_signals_total,
      avg: balance.avg_buying_signals_per_call,
      pct: Math.round((balance.buying_signals_total / max) * 100),
      tone: "positive" as const,
    },
    {
      id: "objections" as const,
      label: "Had concerns",
      count: balance.objections_total,
      avg: balance.avg_objections_per_call,
      pct: Math.round((balance.objections_total / max) * 100),
      tone: "risk" as const,
    },
  ];
}

export function describeSignalBalance(net: number, analyzed: number): string {
  if (!analyzed) return "Review a few calls first to see interest and concerns.";
  if (net > 0) return `${net} more sign${net === 1 ? "" : "s"} of interest than concern. Momentum looks good.`;
  if (net < 0) {
    return `${Math.abs(net)} more concern${net === -1 ? "" : "s"} than interest. Worth a careful follow-up.`;
  }
  return "Interest and concerns are balanced. Follow up on open questions.";
}

export function describeCoaching(
  snapshot: AnalyticsSummary["coaching_snapshot"],
  repTalkPct: number,
): string {
  if (snapshot.talk_balance_label === "rep_heavy") {
    return `You spoke ${repTalkPct}% of the time. Try asking more questions and leave room for the customer to talk.`;
  }
  if (snapshot.talk_balance_label === "prospect_heavy") {
    return "The customer did most of the talking. Guide the call a bit more and suggest clear next steps.";
  }
  if (snapshot.avg_rep_questions < 5) {
    return "Talk time looks balanced, but you could ask more questions. Aim for at least 5 per call.";
  }
  return "Good balance. You are listening well and asking enough questions.";
}
