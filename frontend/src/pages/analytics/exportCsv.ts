import type { AnalyticsSummary } from "../../api/conversations";
import { OUTCOME_LABELS } from "./constants";

function csvCell(value: string | number | null | undefined): string {
  const raw = value == null ? "" : String(value);
  return /[",\n]/.test(raw) ? `"${raw.replace(/"/g, '""')}"` : raw;
}

export function buildAnalyticsCsv(summary: AnalyticsSummary): string {
  const lines = [
    ["Call Insights Export"],
    ["Range", summary.range],
    ["Exported at", new Date().toISOString()],
    [],
    ["Summary"],
    ["Metric", "Value"],
    ["Saved calls", summary.total_conversations],
    ["Reviewed calls", summary.analyzed_conversations],
    ["Calls reviewed %", summary.analysis_coverage_pct],
    ["Good leads", summary.pipeline_outlook.qualified_calls],
    ["Needs follow-up", summary.pipeline_outlook.follow_up_calls],
    ["Needs attention", summary.pipeline_outlook.at_risk_calls],
    ["Avg interest", summary.avg_interest_score],
    ["Avg close chance %", summary.avg_conversion_pct],
    ["Interest signs total", summary.signal_balance.buying_signals_total],
    ["Concerns total", summary.signal_balance.objections_total],
    ["Interest balance", summary.signal_balance.net_signal_score],
    ["Avg you talked %", summary.avg_rep_talk_pct],
    ["Avg questions asked", summary.coaching_snapshot.avg_rep_questions],
    ["Listening score", summary.coaching_snapshot.listening_index],
    ["Avg speaking speed", summary.avg_rep_wpm],
    ["Avg length (sec)", summary.avg_duration_sec],
    ["Tip suggestions used %", summary.suggestion_cache_hit_pct],
    [],
    ["Chance to close"],
    ["Group", "Count"],
    ["Strong chance (65%+)", summary.conversion_bands.likely],
    ["Some chance (45-64%)", summary.conversion_bands.possible],
    ["Low chance (under 45%)", summary.conversion_bands.unlikely],
    [],
    ["Call volume"],
    ["Period", "Calls"],
    ...summary.weekly_volume.map((row) => [row.label, row.count]),
    [],
    ["Calls"],
    ["ID", "Started at", "Caller", "Length (sec)", "Result", "Interest", "Close chance %", "Interest signs", "Concerns"],
    ...summary.calls.map((call) => [
      call.id,
      call.started_at,
      call.rep_label,
      call.duration_sec,
      OUTCOME_LABELS[call.outcome],
      call.interest_score,
      call.conversion_pct,
      call.buying_signals,
      call.objections,
    ]),
  ];
  return `${lines.map((row) => row.map(csvCell).join(",")).join("\n")}\n`;
}

export function downloadAnalyticsCsv(summary: AnalyticsSummary, range: string): void {
  const stamp = new Date().toISOString().slice(0, 10);
  const blob = new Blob([buildAnalyticsCsv(summary)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `call-insights-${range}-${stamp}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}
