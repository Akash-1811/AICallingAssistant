import type { AnalyticsCallRow, AnalyticsSummary } from "../../api/conversations";
import { OUTCOME_LABELS } from "./constants";

export type WinBand = "likely" | "possible" | "unlikely";
export type SignalFocus = "buying" | "objections";
export type CoachingFocus = "overview" | "questions" | "listening" | "wpm";

export type Drilldown =
  | { type: "volume"; period: string }
  | { type: "win_band"; band: WinBand }
  | { type: "outcome"; outcome: AnalyticsCallRow["outcome"] }
  | { type: "signals"; signal: SignalFocus }
  | { type: "coaching"; focus: CoachingFocus };

export type DrilldownMeta = {
  title: string;
  subtitle: string;
  stats: { label: string; value: string }[];
};

const WIN_BAND_LABELS: Record<WinBand, string> = {
  likely: "Strong chance (65%+)",
  possible: "Some chance (45–64%)",
  unlikely: "Low chance (under 45%)",
};

const COACHING_LABELS: Record<CoachingFocus, string> = {
  overview: "How you spoke",
  questions: "Questions asked",
  listening: "Listening score",
  wpm: "Speaking speed",
};

function getConversionBand(call: AnalyticsCallRow): WinBand | null {
  if (call.conversion_pct == null) return null;
  if (call.conversion_pct >= 65) return "likely";
  if (call.conversion_pct >= 45) return "possible";
  return "unlikely";
}

function mean(
  calls: AnalyticsCallRow[],
  pick: (call: AnalyticsCallRow) => number | null | undefined,
): number | null {
  const values = calls.map(pick).filter((value): value is number => value != null);
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function formatDurationAverage(calls: AnalyticsCallRow[]): string {
  const avg = mean(calls, (call) => call.duration_sec);
  if (avg == null) return "—";
  const minutes = Math.floor(avg / 60);
  const seconds = Math.round(avg % 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function formatAverage(
  calls: AnalyticsCallRow[],
  pick: (call: AnalyticsCallRow) => number | null | undefined,
  suffix = "",
): string {
  const avg = mean(calls, pick);
  return avg == null ? "—" : `${Math.round(avg * 10) / 10}${suffix}`;
}

export function getDrilldownCalls(summary: AnalyticsSummary, drilldown: Drilldown): AnalyticsCallRow[] {
  const calls = summary.calls;

  switch (drilldown.type) {
    case "volume": {
      const bucket = summary.weekly_volume.find((row) => row.label === drilldown.period);
      if (!bucket?.call_ids.length) return [];
      const ids = new Set(bucket.call_ids);
      return calls.filter((call) => ids.has(call.id));
    }
    case "win_band":
      return calls.filter((call) => getConversionBand(call) === drilldown.band);
    case "outcome":
      return calls.filter((call) => call.outcome === drilldown.outcome);
    case "signals":
      return [...calls]
        .filter((call) => call.outcome !== "pending")
        .sort((left, right) =>
          drilldown.signal === "buying"
            ? right.buying_signals - left.buying_signals
            : right.objections - left.objections,
        );
    case "coaching":
      return calls.filter((call) => call.outcome !== "pending");
    default:
      return [];
  }
}

export function getDrilldownMeta(
  summary: AnalyticsSummary,
  drilldown: Drilldown,
  calls: AnalyticsCallRow[],
): DrilldownMeta {
  const subtitle = `${calls.length} call${calls.length === 1 ? "" : "s"}`;

  switch (drilldown.type) {
    case "volume": {
      const bucket = summary.weekly_volume.find((row) => row.label === drilldown.period);
      return {
        title: `${drilldown.period}: call count`,
        subtitle: `${subtitle} in this period`,
        stats: [
          { label: "Calls in period", value: String(bucket?.count ?? calls.length) },
          { label: "Avg length", value: formatDurationAverage(calls) },
          { label: "Reviewed", value: String(calls.filter((call) => call.outcome !== "pending").length) },
        ],
      };
    }
    case "win_band":
      return {
        title: WIN_BAND_LABELS[drilldown.band],
        subtitle: `${subtitle} in this group`,
        stats: [
          { label: "Avg close chance", value: formatAverage(calls, (call) => call.conversion_pct, "%") },
          { label: "Avg interest", value: formatAverage(calls, (call) => call.interest_score) },
          {
            label: "Good leads",
            value: String(calls.filter((call) => call.outcome === "qualified").length),
          },
        ],
      };
    case "outcome":
      return {
        title: OUTCOME_LABELS[drilldown.outcome],
        subtitle: `${subtitle} in selected range`,
        stats: [
          { label: "Avg close chance", value: formatAverage(calls, (call) => call.conversion_pct, "%") },
          {
            label: "Interest balance",
            value: String(
              calls.reduce((sum, call) => sum + call.buying_signals - call.objections, 0),
            ),
          },
          { label: "Avg length", value: formatDurationAverage(calls) },
        ],
      };
    case "signals": {
      const buying = calls.reduce((sum, call) => sum + call.buying_signals, 0);
      const objections = calls.reduce((sum, call) => sum + call.objections, 0);
      return {
        title: drilldown.signal === "buying" ? "Showed interest" : "Had concerns",
        subtitle:
          drilldown.signal === "buying"
            ? `${subtitle} (most interest first)`
            : `${subtitle} (most concerns first)`,
        stats: [
          { label: "Interest signs", value: String(buying) },
          { label: "Concerns", value: String(objections) },
          { label: "Balance", value: String(buying - objections) },
        ],
      };
    }
    case "coaching":
      return {
        title: COACHING_LABELS[drilldown.focus],
        subtitle: `${subtitle} with talk stats`,
        stats: [
          { label: "Avg you talked", value: formatAverage(calls, (call) => call.rep_talk_pct, "%") },
          { label: "Avg questions", value: formatAverage(calls, (call) => call.rep_questions) },
          { label: "Avg speaking speed", value: formatAverage(calls, (call) => call.rep_wpm) },
        ],
      };
    default:
      return { title: "Details", subtitle, stats: [] };
  }
}
