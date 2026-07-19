/** All shared types for the AI Sales Assistant UI. */

export type SessionStatus = "idle" | "connecting" | "live" | "error";

export interface SourceItem {
  id?: string | null;
  excerpt?: string;
  metadata?: Record<string, unknown>;
  vector_score?: number;
  rerank_score?: number;
}

export interface TranscriptPartialMessage {
  type: "transcript_partial";
  text: string;
  session_id?: string;
  speaker?: number | null;
}

export interface TranscriptFinalMessage {
  type: "transcript_final";
  text: string;
  session_id?: string;
  speaker?: number | null;
}

export interface AnswerStartedMessage {
  type: "answer_started";
  session_id?: string;
  generation_id: number;
  query: string;
}

export interface AnswerDeltaMessage {
  type: "answer_delta";
  session_id?: string;
  generation_id: number;
  query?: string;
  delta: string;
  text: string;
  from_cache?: boolean;
  cache_hit?: string | boolean;
}

export interface AnswerDoneMessage {
  type: "answer_done";
  text: string;
  session_id?: string;
  generation_id: number;
  query?: string;
  sources?: SourceItem[];
  error?: string;
  from_cache?: boolean;
  cache_hit?: string | boolean;
  duplicate_skip?: boolean;
}

export interface AnswerCancelledMessage {
  type: "answer_cancelled";
  session_id?: string;
  generation_id: number;
}

export interface ErrorMessage {
  type: "error";
  message: string;
  session_id?: string;
}

/**
 * Server push: speaker channels heard so far and the lead (customer) channel.
 * Channel 0 = the rep's mic, channel 1 = shared meeting-tab audio.
 */
export interface SessionStatusMessage {
  type: "session_status";
  session_id?: string;
  speakers: number[];
  lead_speaker_id: number | null;
}

export type WsMessage =
  | TranscriptPartialMessage
  | TranscriptFinalMessage
  | AnswerStartedMessage
  | AnswerDeltaMessage
  | AnswerDoneMessage
  | AnswerCancelledMessage
  | ErrorMessage
  | SessionStatusMessage;

export interface SessionState {
  status: SessionStatus;
  error: string | null;
  messages: WsMessage[];
  sessionId: string | null;
  lastEndedSessionId: string | null;
  startedAt: number | null;
  speakers: number[];
  leadSpeakerId: number | null;
}

export type SessionAction =
  | { type: "CONNECTING" }
  | { type: "LIVE"; sessionId?: string }
  | { type: "MESSAGE"; payload: WsMessage }
  | {
      type: "SESSION_STATUS";
      payload: Pick<SessionStatusMessage, "speakers" | "lead_speaker_id">;
    }
  | { type: "ERROR"; error: string }
  | { type: "DISCONNECT" };
