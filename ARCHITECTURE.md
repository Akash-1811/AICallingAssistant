# Architecture — Developer Guide

A 10-minute tour of the codebase: what this system is, the tech stack, the end-to-end
call flow, and the main functions involved. Written straight from the current code —
if something here looks wrong, the code is the source of truth.

---

## 1. What this system actually is

A **live sales-call coaching copilot**, not a calling/telephony system. There is no
Twilio/SIP anywhere. A rep runs a call (phone-on-speaker, or Zoom/Meet in the browser),
the browser streams the audio to this backend, and the backend:

1. Transcribes it live (speech-to-text)
2. Figures out who's the rep vs. the customer, and what the customer just asked
3. Retrieves relevant facts from a knowledge base (RAG)
4. Asks an LLM to classify the moment and write a short spoken suggestion
5. Streams that suggestion to the rep's screen in real time
6. After the call, generates a structured coaching report

Everything is text shown to a human rep. Nothing here talks to the customer.

---

## 2. Tech stack

| Layer | Technology | Why |
|---|---|---|
| Backend framework | **FastAPI** (Python, async) | WebSocket + REST in one app |
| Speech-to-text | **Deepgram** (`nova-3`, multichannel streaming) | Low-latency streaming STT, Hindi/English |
| LLM | **Google Gemini** (via `google-genai` SDK) or **OpenAI** (pluggable) | Answer generation + intent classification, in one call |
| Vector search | **Qdrant** | Semantic search over the knowledge base |
| Embeddings | `sentence-transformers`, multilingual model | Turns text into vectors; Hindi and English share one space |
| Reranker | `sentence-transformers` `CrossEncoder`, multilingual | Re-scores top candidates for precision |
| Session/cache | **Redis** (optional, falls back to in-process memory) | Per-call conversation memory, answer caching |
| Database | **PostgreSQL** (Docker) or **SQLite** (local dev), via SQLAlchemy async | Durable call/transcript/analysis storage |
| Frontend | **React + TypeScript + Vite** | Dashboard, live call UI, call review |
| Auth | JWT (`PyJWT`) + `bcrypt` | User accounts, per-request auth |
| Observability | OpenTelemetry (optional, off by default) | Tracing across RAG/LLM calls |

Backend entry point: [app/main.py](app/main.py) — a FastAPI app assembled from routers,
with a `lifespan` that validates config, warms up the RAG stack (loads embedding +
reranker models once at boot so the first real call isn't slow), and initializes the
database.

---

## 3. The end-to-end call flow

This is the main thing to understand. Read this section slowly — everything else in
the codebase supports one of these steps.

```
Browser mic + tab audio
        │  (stereo PCM, 16kHz)
        ▼
WebSocket /ws/realtime  ──────────────────────────────────────────────
        │                                                              │
        ▼                                                              │
DeepgramService.stream_transcription()                                 │
   → connects to Deepgram, channel 0 = rep, channel 1 = customer        │  all of this
   → emits transcript_partial (typing indicator) and                    │  runs per
     transcript_final events (one per finished sentence)                 │  WebSocket
        │                                                              │  session,
        ▼                                                              │  concurrently,
TranscriptProcessor.process_stream()                                    │  as asyncio
   → conversation_manager.add_segments_and_get_focused_query()          │  tasks
     - appends to per-session history (Redis or in-memory)              │
     - decides who the "lead" (customer) is: channel 1 if it has        │
       spoken, else the only channel that exists                        │
     - builds a clean "question" string from the customer's turn        │
   → gates out noise: too short, filler-only, or a pure "thank you"     │
   → cancels any in-flight suggestion if the topic has moved on          │
        │                                                              │
        ▼                                                              │
RAGPipeline.stream_live()                                                │
   → checks the answer cache (skipped once there's session memory)      │
   → RAGRetriever.retrieve(): embed → Qdrant search → hybrid             │
     score → rerank → top ~4 passages                                   │
   → realtime_llm.stream_live(): sends the question + passages +         │
     session memory to Gemini/OpenAI in ONE streamed call. The model     │
     itself decides: is this a question / opener / objection / closing? │
     and writes the reply in the matching tone.                         │
   → extract_intent() strips the model's "INTENT: …" tag line before     │
     anything is shown to the rep                                       │
        │                                                              │
        ▼                                                              │
RecordingQueue.put()                                                     │
   → forwards each event to the browser immediately                     │
   → persists it in the background (never blocks the live stream)       │
        │                                                              │
        ▼                                                              │
Browser: suggestion types itself out live, word by word ────────────────
        │
        ▼  (rep clicks "End Session")
finalize_conversation() + flush_and_close()
        │
        ▼
schedule_post_call_analysis()
   → compute_speech_metrics(): real math from transcript timestamps
   → one LLM call: structured JSON report, every judgment backed by
     a verbatim quote from the transcript
   → saved to the database, shown on the Call Review page
```

### Step by step, with the actual functions

**1. Audio capture (browser)** — [pcmStream.ts](frontend/src/audio/pcmStream.ts)
`startPcmToWebSocket()` uses an `AudioWorklet` to capture the mic and (optionally) a
shared browser tab's audio, and sends them as **interleaved stereo PCM** over the
WebSocket — mic on channel 0, tab audio on channel 1. This is deliberate: channel
identity is *physical*, not guessed, so the system always knows who's who without any
manual "who is the customer" step.

**2. WebSocket entry point** — [app/api/websocket/realtime.py](app/api/websocket/realtime.py)
`realtime_assistant()` authenticates the connection (JWT or API key), creates a session
(`conversation_manager.create_session()`), and starts four concurrent tasks: receive
audio from the browser, stream it to Deepgram, process transcripts into suggestions,
and send events back to the browser. The session lives as long as `receive_audio()` is
running; when the browser disconnects, everything else is cancelled and the call is
finalized.

**3. Speech-to-text** — [app/services/deepgram_service.py](app/services/deepgram_service.py)
`DeepgramService.stream_transcription()` opens one Deepgram connection with
`multichannel=true`, forwards audio, and parses `Results` messages into
`TranscriptSegment` objects — text + which channel (= which person) said it + word
timestamps. Auto-reconnects on transient failures without dropping the browser
connection.

**4. Conversation memory & the "current question"** — [app/modules/conversation_intelligence/conversation_manager.py](app/modules/conversation_intelligence/conversation_manager.py)
`ConversationManager.add_segments_and_get_focused_query()` is the function that turns
raw transcript segments into "what does the AI need to answer right now." It:
- Stores history per session (Redis if configured, else an in-process dict)
- Decides the lead speaker channel (`_lead_speaker_id()`: channel 1 if it's spoken,
  otherwise whichever single channel exists)
- Builds the retrieval query, stitching in the previous turn when the customer says
  something like "what about *that*?" (`_extract_best_query()`)

**5. Turn gating** — [app/services/transcript_processor.py](app/services/transcript_processor.py)
`TranscriptProcessor.process_stream()` is the main loop: one iteration per finished
customer sentence. It drops turns that are too short, pure filler, or (via
`looks_like_closing_or_acknowledgement()` in
[intent_heuristics.py](app/modules/rag/intent_heuristics.py)) just a "thank you" —
saving an LLM call and keeping the rep's screen quiet when nothing new was said. It
also cancels a still-streaming suggestion if the customer has moved on to a new topic
(barge-in), using a per-turn `generation_id` so stale results are never shown.

**6. Retrieval** — [app/modules/rag/retriever.py](app/modules/rag/retriever.py)
`RAGRetriever.retrieve()`: embeds the query (multilingual model, so Hindi and English
search the same space with no translation step), searches Qdrant, blends vector score
with keyword overlap, applies small metadata-based rank nudges, and reranks the
survivors with a cross-encoder — unless the query is too short to bother.

**7. Answer generation** — [app/modules/rag/pipeline.py](app/modules/rag/pipeline.py)
`RAGPipeline.stream_live()` is the heart of the live path: checks the answer cache,
retrieves chunks, then calls the LLM service's `stream_live()`. The **model itself**
classifies the turn (question / opener / objection / closing — see
`build_live_suggestion_prompt()` in [prompts.py](app/modules/rag/prompts.py)) and
writes the reply in one pass; `extract_intent()` in `pipeline.py` peels the tag line
off before the text is streamed onward. There's no keyword-based intent routing
anymore — the LLM understands any phrasing, any language.

**8. The LLM services** — [app/services/gemini_service.py](app/services/gemini_service.py) /
[app/services/openai_service.py](app/services/openai_service.py)
Both expose the same two methods: `stream_live()` (realtime, streamed) and
`generate_answer()` (used by the plain REST `/ask` endpoint). Provider choice is
config-driven via `get_llm_service()` in
[app/services/llm_factory.py](app/services/llm_factory.py) — `LLM_PROVIDER` /
`REALTIME_LLM_PROVIDER` in settings, so live calls can use a faster/cheaper model than
the REST path.

**9. Delivery + persistence** — [app/services/call_recorder.py](app/services/call_recorder.py)
`RecordingQueue` wraps the outbound event queue: every event is forwarded to the
browser **immediately**, and persisted to the database from a background writer task —
so a slow database write can never delay what the rep sees. `flush_and_close()` is
awaited when the session ends, guaranteeing everything is saved before analysis runs.

**10. Post-call analysis** — [app/services/post_call_analysis.py](app/services/post_call_analysis.py)
`run_post_call_analysis()` runs once per finished call:
- `compute_speech_metrics()` (in [speech_metrics.py](app/services/speech_metrics.py)) —
  pure arithmetic on the transcript: talk/listen ratio, pace, filler rate, questions
  asked, per-window activity. No LLM involved.
- One LLM call returns structured JSON (`PostCallAnalysisResult`) — client intent,
  objections, next steps, and sentiment per call phase, where **every score must be
  backed by a verbatim quote** from the transcript.
- `apply_computed_metrics()` overwrites any numeric field the LLM guessed with the
  real computed value — the LLM never gets the final say on a number that can be
  measured.
- Saved to `conversation_analyses`; the frontend renders it as-is (no re-deriving).

---

## 4. Database shape

Four tables, in [app/call_store.py](app/call_store.py):
- **`conversations`** — one row per call (status, duration, lead channel)
- **`transcript_segments`** — every finalized sentence, with speaker role and timestamps
- **`suggestions`** — every AI suggestion shown, with latency and cache-hit info
- **`conversation_analyses`** — the post-call report (versioned — re-analyzing keeps history)

Plus `knowledge_sources` for user-uploaded KB files ([app/api/v1/knowledge.py](app/api/v1/knowledge.py)).

---

## 5. REST API surface (non-realtime)

- `POST /api/v1/ask` ([app/api/v1/query.py](app/api/v1/query.py)) — runs
  `RAGPipeline.run()` synchronously for a single question. Used by the legacy static
  tester and any non-streaming client.
- `app/api/v1/conversations.py` — list/fetch calls, transcripts, analyses; trigger re-analysis.
- `app/api/v1/knowledge.py` — upload/manage knowledge-base files.
- `app/api/v1/auth.py` — signup/login/JWT.

---

## 6. Frontend, briefly

React + TypeScript + Vite. Routing in [App.tsx](frontend/src/App.tsx):

- `/live` — **LiveCallsPage**: the main screen during a call. Uses the
  `useAssistantWs()` hook ([hooks/useAssistantWs.ts](frontend/src/hooks/useAssistantWs.ts))
  to own the WebSocket connection and a reducer-based session state machine; renders
  the live transcript (`TranscriptFeed`) and streaming suggestions (`SuggestionPanel`).
- `/conversations/:id` — **CallReviewPage**: the post-call report. Everything it shows
  comes straight from the backend's saved analysis + metrics — the view layer
  ([pages/callReview/metrics.ts](frontend/src/pages/callReview/metrics.ts)) only reads
  and clamps values, it never re-derives or invents numbers.
- `/dashboard`, `/analytics`, `/knowledge` — call list, aggregate stats, KB file management.
- `/login`, `/signup` — auth, guarded by `ProtectedRoute` / `GuestRoute`.

The only non-trivial frontend logic is audio capture
([audio/pcmStream.ts](frontend/src/audio/pcmStream.ts), described in step 1 above) and
the WebSocket message reducer in `useAssistantWs.ts`, which merges streaming
`answer_delta` events into a single growing suggestion as they arrive.

---

## 7. Key config knobs

Everything tunable lives in [app/core/config.py](app/core/config.py) (loaded from
`.env`) — not hardcoded in logic. Notable ones: `LLM_PROVIDER` /
`REALTIME_LLM_PROVIDER` (Gemini vs OpenAI, live vs REST can differ),
`DEEPGRAM_MODEL` / `DEEPGRAM_LANGUAGE`, `RECALL_K` / `TOP_K` (retrieval breadth),
`USE_RERANKER`, `ANSWER_CACHE_*`, `RAG_TIMEOUT_SECONDS` (live-turn hard timeout),
`ANALYSIS_REPORT_LANGUAGE`.

---

## 8. What to read first, if you're new

1. [app/api/websocket/realtime.py](app/api/websocket/realtime.py) — see the whole
   session wired together in one file.
2. [app/services/transcript_processor.py](app/services/transcript_processor.py) — the
   main per-turn loop.
3. [app/modules/rag/pipeline.py](app/modules/rag/pipeline.py) — retrieval + LLM call.
4. [app/modules/rag/prompts.py](app/modules/rag/prompts.py) — the actual prompt the
   model sees; this is where "tone" and "intent classification" are defined.
5. [app/services/post_call_analysis.py](app/services/post_call_analysis.py) — the
   report generator.

That's the whole system. Everything else (auth, knowledge upload, analytics dashboard)
is standard CRUD around this core loop.
