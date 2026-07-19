import type { AnalyticsCallRow, AnalyticsSummary } from "../../api/conversations";

export const OUTCOME_LABELS: Record<AnalyticsCallRow["outcome"], string> = {
  qualified: "Good lead",
  follow_up: "Needs follow-up",
  at_risk: "Needs attention",
  nurture: "Stay in touch",
  pending: "Not reviewed",
};

export const TALK_LABELS: Record<AnalyticsSummary["coaching_snapshot"]["talk_balance_label"], string> = {
  balanced: "Good balance",
  rep_heavy: "You talked more",
  prospect_heavy: "They talked more",
};

export const RANGE_OPTIONS = [
  { id: "7d" as const, label: "7 days" },
  { id: "30d" as const, label: "30 days" },
  { id: "90d" as const, label: "90 days" },
];

export const WIN_BANDS = [
  { id: "likely" as const, label: "Strong chance (65%+)" },
  { id: "possible" as const, label: "Some chance (45–64%)" },
  { id: "unlikely" as const, label: "Low chance (under 45%)" },
];
