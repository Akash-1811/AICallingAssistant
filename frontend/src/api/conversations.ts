/**
 * REST client for saved conversations and analytics.
 */

import { clearStoredToken, getStoredToken } from "../auth/AuthContext";

export type ConversationSummary = {
  id: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  duration_sec: number | null;
  lead_speaker_id: number | null;
  audio_channels: number;
  rep_label?: string | null;
};

export type TranscriptSegment = {
  speaker_id: number;
  role: string;
  text: string;
  start_ms: number | null;
  end_ms: number | null;
  word_count: number;
};

export type SavedSuggestion = {
  generation_id: number | null;
  trigger_query: string;
  suggestion_text: string;
  from_cache: boolean;
  sources: unknown[];
  latency_ms: number | null;
  created_at: string | null;
};

export type CallAnalysis = {
  conversation_id: string;
  status: string;
  version?: number;
  model?: string | null;
  metrics: Record<string, unknown>;
  analysis: Record<string, unknown>;
  error?: string | null;
  created_at?: string | null;
};

export type AnalyticsSummary = {
  range: string;
  total_conversations: number;
  analyzed_conversations: number;
  analysis_coverage_pct: number;
  avg_rep_talk_pct: number;
  avg_rep_wpm: number;
  avg_duration_sec: number;
  avg_interest_score: number;
  avg_conversion_pct: number;
  suggestion_cache_hit_pct: number;
  pipeline_outlook: {
    qualified_calls: number;
    follow_up_calls: number;
    at_risk_calls: number;
  };
  conversion_bands: { likely: number; possible: number; unlikely: number };
  signal_balance: {
    buying_signals_total: number;
    objections_total: number;
    avg_buying_signals_per_call: number;
    avg_objections_per_call: number;
    net_signal_score: number;
  };
  coaching_snapshot: {
    avg_rep_questions: number;
    talk_balance_label: "balanced" | "rep_heavy" | "prospect_heavy";
    listening_index: number;
  };
  weekly_volume: { label: string; count: number; call_ids: string[] }[];
  calls: AnalyticsCallRow[];
};

export type AnalyticsCallRow = {
  id: string;
  started_at: string | null;
  duration_sec: number | null;
  status: string;
  rep_label: string | null;
  has_audio: boolean;
  interest_examples: string[];
  concern_examples: string[];
  interest_score: number | null;
  conversion_pct: number | null;
  buying_signals: number;
  objections: number;
  outcome: "qualified" | "follow_up" | "at_risk" | "nurture" | "pending";
  conversion_band: "likely" | "possible" | "unlikely" | null;
  rep_talk_pct: number | null;
  rep_questions: number;
  rep_wpm: number | null;
  listening_index: number | null;
};

function apiHeaders(): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getStoredToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const key = import.meta.env.VITE_INTERNAL_API_KEY as string | undefined;
  if (key?.trim()) headers["X-API-Key"] = key.trim();
  return headers;
}

function handleUnauthorized(): void {
  clearStoredToken();
  if (window.location.pathname !== "/login") {
    window.location.assign("/login");
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: apiHeaders() });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail || res.statusText || "Request failed");
  }
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { ...apiHeaders(), "Content-Type": "application/json" },
  });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail || res.statusText || "Request failed");
  }
  return res.json() as Promise<T>;
}

export async function apiDelete(path: string): Promise<void> {
  const res = await fetch(path, { method: "DELETE", headers: apiHeaders() });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail || res.statusText || "Request failed");
  }
}

export async function apiFormPost<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(path, { method: "POST", headers: apiHeaders(), body: form });
  if (res.status === 401) {
    handleUnauthorized();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = (body as { detail?: string }).detail;
    throw new Error(detail || res.statusText || "Request failed");
  }
  return res.json() as Promise<T>;
}

export function authHeaders(): HeadersInit {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getStoredToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export function listConversations(limit = 20) {
  return apiGet<{ items: ConversationSummary[] }>(
    `/api/v1/conversations?limit=${limit}`
  );
}

export function getConversation(id: string) {
  return apiGet<ConversationSummary>(`/api/v1/conversations/${id}`);
}

export function getTranscript(id: string) {
  return apiGet<{
    conversation_id: string;
    segments: TranscriptSegment[];
    suggestions: SavedSuggestion[];
  }>(`/api/v1/conversations/${id}/transcript`);
}

export function getAnalysis(id: string) {
  return apiGet<CallAnalysis>(`/api/v1/conversations/${id}/analysis`);
}

export function reanalyzeConversation(id: string) {
  return apiPost<{ conversation_id: string; status: string }>(
    `/api/v1/conversations/${id}/reanalyze`
  );
}

export function refreshCallMetrics(id: string) {
  return apiPost<{ conversation_id: string; status: string }>(
    `/api/v1/conversations/${id}/refresh-metrics`
  );
}

export function getAnalyticsSummary(range: "7d" | "30d" | "90d" = "30d") {
  return apiGet<AnalyticsSummary>(`/api/v1/analytics/summary?range=${range}`);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatMs(ms: number | null | undefined): string {
  if (ms == null || ms < 0) return "";
  const sec = Math.floor(ms / 1000);
  return `${Math.floor(sec / 60)
    .toString()
    .padStart(2, "0")}:${(sec % 60).toString().padStart(2, "0")}`;
}
