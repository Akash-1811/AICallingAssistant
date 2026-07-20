import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getAnalysis,
  getConversation,
  getTranscript,
  refreshCallMetrics,
  reanalyzeConversation,
  type CallAnalysis,
  type ConversationSummary,
  type SavedSuggestion,
  type TranscriptSegment,
} from "../../api/conversations";
import { asArray, asRecord } from "./json";
import { buildCallReviewView } from "./metrics";

export function useCallReview(conversationId: string | undefined) {
  const [conversation, setConversation] = useState<ConversationSummary | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [suggestions, setSuggestions] = useState<SavedSuggestion[]>([]);
  const [analysis, setAnalysis] = useState<CallAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reanalyzing, setReanalyzing] = useState(false);
  const metricsRefreshed = useRef(false);

  const load = useCallback(async () => {
    if (!conversationId) return;
    setError(null);
    try {
      const [conv, transcript, report] = await Promise.all([
        getConversation(conversationId),
        getTranscript(conversationId),
        getAnalysis(conversationId),
      ]);
      setConversation(conv);
      setSegments(transcript.segments ?? []);
      setSuggestions(transcript.suggestions ?? []);
      setAnalysis(report);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load call");
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!conversationId || loading || metricsRefreshed.current) return;
    const m = asRecord(analysis?.metrics);
    const buckets = asArray(asRecord(m.call_timeline).buckets);
    const hasGlance = Boolean(m.call_glance);
    if (buckets.length > 0 && hasGlance) return;
    if (!analysis?.analysis || Object.keys(asRecord(analysis.analysis)).length === 0) return;
    metricsRefreshed.current = true;
    void refreshCallMetrics(conversationId)
      .then(() => load())
      .catch(() => {
        metricsRefreshed.current = false;
      });
  }, [conversationId, loading, analysis, load]);

  useEffect(() => {
    if (!conversationId || !analysis) return;
    const busy =
      analysis.status === "analyzing" ||
      analysis.status === "running" ||
      conversation?.status === "analyzing";
    if (!busy) return;
    const timer = setInterval(() => void load(), 4000);
    return () => clearInterval(timer);
  }, [conversationId, analysis, conversation?.status, load]);

  const handleReanalyze = useCallback(async () => {
    if (!conversationId || reanalyzing) return;
    setReanalyzing(true);
    try {
      await reanalyzeConversation(conversationId);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Re-analyze failed");
    } finally {
      setReanalyzing(false);
    }
  }, [conversationId, reanalyzing, load]);

  const vm = useMemo(
    () =>
      buildCallReviewView(
        asRecord(analysis?.analysis),
        asRecord(analysis?.metrics),
        conversation
      ),
    [analysis?.analysis, analysis?.metrics, conversation]
  );

  return {
    conversation,
    segments,
    suggestions,
    analysis,
    error,
    loading,
    reanalyzing,
    vm,
    load,
    handleReanalyze,
  };
}
