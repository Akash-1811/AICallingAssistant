# Improvements & Roadmap

A running list of planned improvements across the whole system. Each area captures the
current state, why it matters, and the plan — so anyone can pick it up later without
re-deriving the context. **Nothing here is built unless marked done.**

Add new areas as new sections. Keep each self-contained.

---

## Index

1. [Audio Capture](#1-audio-capture)
2. [Live-Session Reliability](#2-live-session-reliability)
3. [Security & Multi-Tenancy](#3-security--multi-tenancy)
4. [Deployment & Scale](#4-deployment--scale)
5. [Latency (remaining wins)](#5-latency-remaining-wins)
6. [Post-Call Analysis Robustness](#6-post-call-analysis-robustness)
7. [Observability & Quality Gates](#7-observability--quality-gates)
8. [Coding Standards (the 10-year rules)](#8-coding-standards-the-10-year-rules)
9. [Dead Code & Repo Hygiene](#9-dead-code--repo-hygiene)

**Architecture verdict (reviewed end-to-end):** the core 10-step design — stereo capture
→ streaming STT → turn gating → RAG → one intent-aware LLM call → write-behind
persistence → measured post-call analysis — is the *right shape*; it matches how the
best products in this category (Gong/Cresta-class) are built. The weaknesses are not in
the flow itself but around its edges: session resilience, security hardening, and the
fact that the current deployment setup is a dev stack. Those are what the sections
below fix.

---

## 1. Audio Capture

### How it works today
- The rep's **browser** captures two audio sources:
  - Microphone via `getUserMedia` → channel 0 (the rep)
  - Shared meeting-tab audio via `getDisplayMedia` (with "share tab audio") → channel 1 (the customer)
- Merged into **stereo PCM** in an `AudioWorklet`, streamed to the backend over a plain
  **WebSocket** (not WebRTC).
- Code: [frontend/src/audio/pcmStream.ts](frontend/src/audio/pcmStream.ts)

Good enough to launch and run pilots; the stereo channel split is a solid design (clean
speaker separation without guessing). But it's the most fragile part of the system.

### Why it's the weak link
Every failure mode lives on the rep's machine and depends on the rep doing the right
thing — which we can't control:
1. **"Share tab audio" is easy to get wrong** → customer's voice silently missing.
2. **Browser/OS lottery** — reliable in Chrome/Edge, flaky elsewhere.
3. **Phone calls aren't really covered** — phone-on-speaker mixes both voices into one channel.
4. **Background-tab throttling** — mitigated by the AudioWorklet, but still fighting the browser.

### Quick win (low effort)
- [ ] **"No customer audio detected" warning.** If channel 1 stays silent for ~15s while
      the mic is active, show the rep a clear banner immediately — so a fumbled tab-share
      is caught at the start, not after a dead call. (Mirror of the existing silent-*mic*
      warning.)

### The real fix (enterprise-grade, later)
Move capture **off the rep's browser entirely** — how Gong / Chorus / Cresta do it:
- **Prong A — Telephony integration** (phone calls): plug into the dialer platform
  (Twilio Voice Media Streams, Exotel, Ozonetel) server-side; audio arrives already
  split into two clean channels, no laptop involved. Removes failure modes 1–4.
- **Prong B — Meeting-bot integration** (Zoom/Meet/Teams): a bot joins the meeting as an
  official participant via platform APIs; clean per-person audio server-side, no "share
  tab audio" step.
- **Prong C — Desktop app** (fallback tier): native OS-level capture (Windows WASAPI /
  Mac Core Audio) for gaps the above don't cover. Still needs per-machine install, so
  it's a fallback, not the foundation.

### Efficiency note (independent)
- Browser sends **uncompressed** stereo 16kHz PCM (~512 kbps). On weak connections,
  encode to **Opus** in the browser before sending — Deepgram accepts Opus directly over
  the same WebSocket. Does **not** require WebRTC.

### Decisions this depends on
- **Which integration first depends on how customers actually take calls** (phone dialer
  vs. Zoom vs. Teams). Learn from pilots before committing.
- **Compliance:** server-side capture makes call-recording consent a hard requirement
  (jurisdiction-dependent). Decide the consent model early — it shapes the integration.

### Recommended order
1. Quick win — "no customer audio" warning (now).
2. Learn from pilots how reps actually call.
3. Telephony integration (if phone-based) — highest leverage.
4. Meeting-bot integration (if Zoom/Meet-based).
5. Desktop app — only for remaining gaps.

---

## 2. Live-Session Reliability

### What's weak today
1. **A network blip kills the whole call.** If the browser's WebSocket drops for even
   2 seconds, the session ends permanently ([useAssistantWs.ts](frontend/src/hooks/useAssistantWs.ts)
   `onclose` → disconnect, no retry). The call's history splits into two conversations
   and the rep must manually restart mid-call.
2. **Deepgram outage is silent.** [deepgram_service.py](app/live/deepgram_service.py)
   reconnects forever with backoff but never tells the rep transcription is down — the
   screen just goes quiet.
3. **No session duration cap.** A forgotten open tab streams audio (and burns Deepgram
   credit) indefinitely.
4. **No LLM provider failover.** If Gemini errors on the live path, the turn fails —
   even though an OpenAI key is configured and one `get_llm_service()` call away.
5. **Session-memory race (minor).** `set_last_turn()` and `add_segments…()` both do
   load-modify-save on one Redis JSON blob from concurrent tasks — a lost update can
   drop a few history lines (DB transcript unaffected).

### The fix
- [ ] **Client reconnect + server-side session resume**: on drop, the client retries
      with the same session id; the server keeps the session alive for a grace period
      (~60s) instead of finalizing instantly. This is the single most important
      reliability item.
- [ ] After N failed Deepgram reconnects, emit an `error` event so the rep sees
      "transcription unavailable" instead of silence.
- [ ] `MAX_SESSION_MINUTES` config; warn at the limit, then end gracefully.
- [ ] Optional automatic fallback to the other configured LLM provider on live-path
      failure.
- [ ] Serialize session-state writes (per-session lock, or split the blob into
      Redis list + hash).

---

## 3. Security & Multi-Tenancy

### What's weak today (all verified in code)
1. **JWT travels in the URL** for WebSocket auth (`?token=…`,
   [auth.py](app/api/v1/auth.py)) — full tokens appear in server access logs (we have
   literally seen this happen in our own logs). Should move to the first WebSocket
   message or a subprotocol header.
2. **Production can run with the default JWT secret.** `validate_production_settings()`
   checks API keys but *not* `JWT_SECRET` — `"dev-change-me-in-production"` would pass.
   Also the current secret is under the 32-byte minimum for HS256 (PyJWT warns on
   every request).
3. **The knowledge base has no tenant isolation.** `QdrantService.search()` takes no
   filter — every call searches the entire collection, so with multiple customer
   accounts, one user's uploaded documents can surface in another user's calls. Fine
   for a single-company deployment; a blocker for SaaS. (The answer cache is similarly
   global.)
4. **No rate limiting** on REST or WebSocket endpoints.
5. **Secrets in a plaintext `.env`** in a OneDrive-synced folder; keys were exposed
   earlier and still need rotation; no secrets manager.

### The fix
- [ ] Enforce `JWT_SECRET` strength in `validate_production_settings()` (present, not
      the default, ≥32 bytes).
- [ ] WS auth via first message instead of query param.
- [ ] Add a `workspace_id` payload filter to Qdrant search + cache keys (the
      `conversations.workspace_id` column already exists — the concept is half-built).
- [ ] Conversation/analytics REST endpoints must also filter by workspace —
      verified 2026-07-20: any logged-in user can read any user's calls,
      transcripts, analyses, and audio.
- [ ] Rate limiting (e.g. `slowapi`) on auth + ask endpoints; cap concurrent WS
      sessions per user.
- [ ] Rotate all keys; move production secrets to a secrets manager.

---

## 4. Deployment & Scale

### What's weak today
1. **The only deployment config is a dev stack.** `docker-compose.yml` runs the
   frontend as a Vite *dev server* (`npm run dev`) and the backend with `--reload`.
   There is no production build path at all: no `vite build` + static serving, no
   multi-worker/non-reload backend, no TLS story.
2. **No database migrations.** Schema comes from `create_all` only — the first schema
   change against a live customer database has no upgrade path. Needs Alembic.
3. **No backups** for Postgres/Qdrant volumes.
4. **Single-process by design** (in-process generation counters, model weights in the
   API process). Fine for one instance; horizontal scaling needs sticky sessions and,
   eventually, splitting model inference from the API process. Document the limit now,
   split later when load demands it.
5. **Dependencies are unpinned** (`requirements.txt` mostly versionless) — a rebuild
   two years from now produces a different app. Needs a lockfile (`uv`/`pip-tools`).

### The fix
- [ ] Production compose (or K8s manifest): `vite build` → nginx static, uvicorn
      without reload, TLS via reverse proxy.
- [ ] Introduce Alembic; generate the initial migration from current models.
- [ ] Nightly `pg_dump` + Qdrant snapshot to off-box storage.
- [ ] Pin dependencies with a lockfile; upgrade deliberately, not accidentally.

---

## 5. Latency (remaining wins)

Current post-optimization state is healthy (~0.7–1.3s to first token). Known remaining
wins:

- [ ] **Speculative retrieval on interim transcripts** — start embedding + Qdrant +
      rerank while the customer is still finishing the sentence; reuse if the final
      text matches. Removes ~200–500ms of perceived latency. (Deepgram already streams
      the interims; they're currently display-only.)
- [ ] **Async LLM path** — `google-genai` has an async client; using it removes the
      thread-per-turn + `call_soon_threadsafe` bridge in
      [transcript_processor.py](app/live/transcript_processor.py). Cleaner
      cancellation, no thread growth under many concurrent sessions.
- [ ] The paid-tier Gemini key (business task, not code) remains the biggest single
      latency/reliability lever.

---

## 6. Post-Call Analysis Robustness

### What's weak today
1. **A crash or restart mid-analysis strands the call.** Analysis runs as a
   fire-and-forget task; if the process dies, the conversation sits in `analyzing`
   forever. Nothing sweeps or retries.
2. **A transient LLM failure (e.g. quota) marks the analysis `failed`** and waits for
   a human to click Re-analyze — it should retry itself later.
3. **The duplicate-question nudge is hardcoded English** — a Hindi call gets an
   English coaching line ([transcript_processor.py](app/live/transcript_processor.py)
   `_DUPLICATE_NUDGE`).

### The fix
- [ ] On startup, sweep conversations stuck in `analyzing`/`running` older than N
      minutes → re-queue or mark failed with reason.
- [ ] Retry failed analyses automatically with backoff (a simple periodic task is
      enough; no queue infrastructure needed at this scale).
- [ ] Localize the duplicate-nudge line (or generate it via the live prompt like
      everything else).

---

## 7. Observability & Quality Gates

### What's weak today
- OpenTelemetry is wired throughout but **disabled**; no error alerting (Sentry-class),
  no uptime monitoring, no latency dashboards — despite the data existing
  (`suggestions.latency_ms` records every turn's true latency).
- **No CI.** Tests exist (49) but nothing runs them automatically; no `tsc` gate; the
  retrieval eval (`eval_rag.py`) is manual.

### The fix
- [ ] CI pipeline (GitHub Actions once the repo exists): `pytest` + `tsc --noEmit` +
      lint on every push; `eval_rag` against a Qdrant service container.
- [ ] Error tracking (Sentry or equivalent) on backend + frontend.
- [ ] A tiny ops dashboard: p50/p95 of `latency_ms`, calls/day, analysis failure rate.
- [ ] Enable OTel export in production.

---

## 8. Coding Standards (the 10-year rules)

The codebase's current style is good — keep it that way deliberately. These are the
rules every change must follow, written down so they survive team growth:

1. **One source of truth per fact.** A number, threshold, or derivation lives in
   exactly one place (config or one function) — never re-derived in a second layer.
   (This rule already deleted ~500 lines of frontend re-derivation; keep enforcing it.)
2. **Small, single-purpose functions with honest names.** If a function needs "and"
   in its description, split it. No helper is created until the *second* caller exists.
3. **Comments explain *why*, never *what*.** Every non-obvious constant carries the
   reason it has that value (see `FILLER_PATTERN`, `_INTENT_LINE_MAX_CHARS`).
4. **No speculative abstraction.** No interfaces/base-classes/options "for later" —
   build for the second use-case when it arrives, not before.
5. **Graceful degradation over hard failure** on the live path: every stage falls back
   (cache → retrieval → generic prompt; regex gate → LLM classification) and a failed
   turn is skipped, never crashes the session.
6. **Tests pin contracts, not implementations.** Each behavioral guarantee gets a test
   naming the guarantee (e.g. "curves must be measured only", "malformed intent tags
   fall back to question").
7. **Config over constants; constants over magic numbers** — anything an operator might
   tune goes in `config.py` with a comment; the rest is a named constant next to its use.
8. **Docs are code.** `ARCHITECTURE.md` / `HOW_IT_WORKS.md` are updated in the same
   change that alters behavior — a stale doc is treated as a bug (this repo has already
   been bitten by stale docs).
9. **Enforce mechanically, not by vigilance:**
   - [ ] Add `ruff` (lint + format) for Python, `eslint` + `prettier` for TS — wired
         into CI so style is never a review topic.
   - [ ] Soft limits as review flags: function > ~50 lines or file > ~400 lines needs a
         stated reason.

---

## 9. Dead Code & Repo Hygiene

- [ ] **Initialize the git repository.** Still the single cheapest, highest-value
      outstanding task: `.gitignore` (`.env`, `data/`, `.venv/`, `node_modules/`,
      `__pycache__/`, `.tmp_dg*`) → initial commit. Everything else in this document
      assumes version control exists.
- [ ] Remove the legacy static tester (`static/index.html` + the `/ui` mount and root
      redirect in [main.py](app/main.py)) — superseded by the React app; the root
      endpoint should return API info.
- [ ] Delete scratch directories: `.tmp_dg/`, `.tmp_dg2/`.
- [ ] Retire or clearly mark the stale docs (`PROJECT_OVERVIEW.md`,
      `AI_Calling_Assistant_Full_Production_Guide.md`) — they describe the
      pre-migration architecture (mono audio, manual calibration, keyword intents) and
      will mislead any new reader. `ARCHITECTURE.md` + `HOW_IT_WORKS.md` are current.
- [ ] Sweep for unused exports/config after the recent refactors (confirm every
      setting in `config.py`, old CSS modules, and frontend types still have callers).
- [ ] Unused spare keys in `.env` (`GEMINI_API_KEY1..5`, `DEEPGRAM_API_KEY3`,
      `HUGGINGFACE_API_KEY`, `ANTHROPIC_API_KEY`) — remove what isn't used, rotate what
      was exposed.

---

<!--
Template for a new area — copy this block:

## N. <Area name>

### How it works today
### Why it matters / what's wrong
### Quick win (if any)
- [ ] ...
### The real fix
### Decisions this depends on
### Recommended order
-->
