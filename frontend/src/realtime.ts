import type {
  AnswerCancelledMessage,
  AnswerDeltaMessage,
  AnswerDoneMessage,
  AnswerStartedMessage,
  ErrorMessage,
  TranscriptFinalMessage,
  TranscriptPartialMessage,
  WsMessage,
} from "./types";

export interface LiveAnswerState {
  generationId: number;
  query: string;
  text: string;
  fromCache?: boolean;
  cacheHit?: string | boolean;
}

export interface TranscriptTimelineItem {
  kind: "speaker" | "assistant" | "error";
  id: string;
  text: string;
  speaker: number | null;
  query?: string;
  fromCache?: boolean;
  error?: string;
}

export interface RealtimeView {
  transcriptTimeline: TranscriptTimelineItem[];
  livePartial: TranscriptPartialMessage | null;
  liveAnswer: LiveAnswerState | null;
  completedAnswers: AnswerDoneMessage[];
}

function asSpeakerId(value: number | null | undefined): number | null {
  return typeof value === "number" ? value : null;
}

/** Speaker ids are audio channels: 0 = the rep's mic, 1 = meeting-tab audio. */
export function speakerLabel(speaker: number | null | undefined): string {
  if (speaker === 1) return "Customer";
  if (speaker === 0) return "You";
  return "Caller";
}

export function buildRealtimeView(messages: WsMessage[]): RealtimeView {
  const transcriptTimeline: TranscriptTimelineItem[] = [];
  const completedAnswers: AnswerDoneMessage[] = [];
  let livePartial: TranscriptPartialMessage | null = null;
  let currentAnswer: LiveAnswerState | null = null;
  let activeAnswerMeta: AnswerStartedMessage | null = null;

  for (const message of messages) {
    switch (message.type) {
      case "transcript_partial":
        livePartial = message;
        break;
      case "transcript_final":
        transcriptTimeline.push(speakerTimelineItem(message));
        livePartial = null;
        break;
      case "answer_started":
        activeAnswerMeta = message;
        currentAnswer = {
          generationId: message.generation_id,
          query: message.query,
          text: "",
        };
        break;
      case "answer_delta":
        currentAnswer = mergeAnswerDelta(currentAnswer, activeAnswerMeta, message);
        break;
      case "answer_done":
        completedAnswers.push(message);
        transcriptTimeline.push(assistantTimelineItem(message));
        if (
          currentAnswer &&
          currentAnswer.generationId === message.generation_id
        ) {
          currentAnswer = null;
        }
        if (
          activeAnswerMeta &&
          activeAnswerMeta.generation_id === message.generation_id
        ) {
          activeAnswerMeta = null;
        }
        break;
      case "answer_cancelled":
        currentAnswer = clearCancelledAnswer(currentAnswer, message);
        if (
          activeAnswerMeta &&
          activeAnswerMeta.generation_id === message.generation_id
        ) {
          activeAnswerMeta = null;
        }
        break;
      case "error":
        transcriptTimeline.push(errorTimelineItem(message));
        break;
      default:
        break;
    }
  }

  return {
    transcriptTimeline,
    livePartial,
    liveAnswer: currentAnswer,
    completedAnswers,
  };
}

function speakerTimelineItem(
  message: TranscriptFinalMessage
): TranscriptTimelineItem {
  return {
    kind: "speaker",
    id: `speaker-${message.session_id ?? "session"}-${message.speaker ?? "unknown"}-${message.text}`,
    text: message.text,
    speaker: asSpeakerId(message.speaker),
  };
}

function assistantTimelineItem(
  message: AnswerDoneMessage
): TranscriptTimelineItem {
  return {
    kind: "assistant",
    id: `assistant-${message.generation_id}`,
    text: message.text,
    speaker: null,
    query: message.query,
    fromCache: message.from_cache,
    error: message.error,
  };
}

function errorTimelineItem(message: ErrorMessage): TranscriptTimelineItem {
  return {
    kind: "error",
    id: `error-${message.session_id ?? "session"}-${message.message}`,
    text: message.message,
    speaker: null,
    error: message.message,
  };
}

function mergeAnswerDelta(
  current: LiveAnswerState | null,
  meta: AnswerStartedMessage | null,
  message: AnswerDeltaMessage
): LiveAnswerState {
  const baseQuery = current?.query || meta?.query || message.query || "";
  return {
    generationId: message.generation_id,
    query: baseQuery,
    text: message.text,
    fromCache: message.from_cache,
    cacheHit: message.cache_hit,
  };
}

function clearCancelledAnswer(
  current: LiveAnswerState | null,
  message: AnswerCancelledMessage
): LiveAnswerState | null {
  if (!current) return null;
  if (current.generationId !== message.generation_id) return current;
  return null;
}
