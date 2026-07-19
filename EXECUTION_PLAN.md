# Execution Plan

The phased, step-by-step plan to take this project from "works well" to
"enterprise-grade product." Each phase has a goal, concrete tasks, and a
**Definition of Done** — a phase isn't finished until its DoD checks pass.

Detailed reasoning for each item lives in [IMPROVEMENTS_ROADMAP.md](IMPROVEMENTS_ROADMAP.md)
(referenced as §N below). This file is the *order of battle*; that file is the *why*.

**Rules of engagement**
- Phases are ordered by dependency and risk — don't skip ahead (e.g. no refactors
  before git exists; no customers before Phase 4).
- Every phase ends with: all tests pass, `tsc` clean, docs updated, one commit.

---

## Phase 0 — Foundation (git + key safety)   *~half a day*

The prerequisite for literally everything else. No code changes.

- [x] `git init` with `.gitignore` covering: `.env`, `data/`, `.venv/`,
      `node_modules/`, `__pycache__/`, `.pytest_cache/`, `.tmp_dg*`
- [x] Initial commit; push to a **private** GitHub repo
- [ ] Rotate every API key that has been exposed (Gemini, Deepgram, OpenAI, HF,
      Anthropic) — §9
- [x] Delete unused keys from `.env` (`GEMINI_API_KEY1..5`, `DEEPGRAM_API_KEY3`,
      `HUGGINGFACE_API_KEY`, `ANTHROPIC_API_KEY`) — §9

**Done when:** repo exists with a tagged first commit; `.env` contains only keys the
code actually reads; every key is freshly rotated.

---

## Phase 1 — Codebase Clarity (the comprehension fix)   *~1–2 days*

Goal: **any developer — including the owner — can open any file and know what it does
in 30 seconds.** This directly attacks the "too many files, unclear names, unnecessary
helpers" problem. Done immediately after Phase 0 so the churn is version-controlled and
happens *before* feature work (avoids painful conflicts later).

### 1a. Restructure folders to match the flow
Replace the arbitrary `modules/` vs `services/` split with packages named after what
they do, in call order:

```
app/
  api/        # HTTP + WebSocket endpoints (unchanged)
  core/       # config, logging, telemetry, warmup
  live/       # everything that runs DURING a call:
              #   deepgram_service, transcript_processor,
              #   conversation_manager, call_recorder, intent gate
  rag/        # knowledge search + answering:
              #   pipeline, retriever, prompts, embedding, qdrant,
              #   answer_cache, gemini_service, openai_service, llm_factory
  analysis/   # AFTER the call: post_call_analysis, speech_metrics
  storage/    # database models (call_store)
  scripts/    # ingest, eval, seeds
```

Six top-level concepts that mirror ARCHITECTURE.md's flow diagram — the folder tree
*is* the architecture.

### 1b. Rename for plain English  ✅ done
Applied rename map:
- `modules/conversation_intelligence/` → gone (file moved to `live/`)
- `add_segments_and_get_focused_query()` → `record_turn()`
- `looks_like_closing_or_acknowledgement()` → `is_closing_pleasantry()`
- `intent_heuristics.py` → `turn_gate.py`
- `query_normalize.py` + `query_intent.py` → merged into `query_cleanup.py`
- `core/loggin.py` (typo) → `core/logging.py`

### 1c. File headers + helper audit
- [x] Every file starts with 2–3 plain-English lines: what it does, and where it sits
      in the call flow.
- [x] Inline every helper with exactly one caller (unless it exists to be tested).
- [x] Merge files under ~40 lines into their only consumer where sensible
      (e.g. frontend `json.ts`/`utils.ts` candidates).

### 1d. Dead code sweep (§9)
- [x] Remove `static/index.html` legacy tester + `/ui` mount + root redirect
- [x] Delete `.tmp_dg/`, `.tmp_dg2/`
- [x] Move stale docs (`PROJECT_OVERVIEW.md`, `AI_Calling_Assistant_Full_Production_Guide.md`)
      into `docs/archive/` with a "superseded by ARCHITECTURE.md" note
- [x] Verify every `config.py` setting still has a caller; delete orphans

### 1e. Mechanical style enforcement (§8)
- [x] `ruff` (lint + format) for Python — done; `eslint`/`prettier` for TS deferred to Phase 5 CI setup
- [x] Fix everything they flag once; from then on it's automatic (ruff: clean)

**Done when:** folder tree matches the diagram above; every file has a header; no
single-caller helpers remain; ruff/eslint pass clean; all tests + `tsc` pass; imports
in ARCHITECTURE.md updated. **Measurable check: a new developer can trace one customer
turn end-to-end by opening files in `live/` → `rag/` in order, without jumping back.**

---

## Phase 2 — Security Hardening (§3)   *~1 day*

Do this before any real user touches the system.

- [ ] `validate_production_settings()` also enforces `JWT_SECRET`: present, not the
      dev default, ≥32 bytes. Generate a strong secret for every environment.
- [ ] Move WebSocket auth from `?token=` in the URL to the first WS message
      (tokens must never appear in access logs).
- [ ] Rate limiting on `/auth/*` and `/ask`; cap concurrent live sessions per user.
- [ ] Backend must not start in production mode with CORS wide open / missing origins.

**Done when:** a request log contains zero tokens; production boot fails loudly on a
weak secret; a script hammering `/auth/login` gets 429s.

---

## Phase 3 — Live-Session Resilience (§2 + §1 quick win)   *~2–3 days*

The biggest real-world reliability gap: today a 2-second network blip kills a call.

- [ ] **Reconnect + resume**: client retries with the same session id on drop; server
      holds the session open for a grace period (~60s) before finalizing. Transcript
      history and suggestion state survive the blip.
- [ ] Deepgram circuit breaker: after N failed reconnects, send an `error` event —
      the rep sees "transcription unavailable", never silence.
- [ ] `MAX_SESSION_MINUTES` cap with a UI warning before cut-off.
- [ ] "**No customer audio detected**" banner when channel 1 stays silent ~15s while
      the mic is live (catches a fumbled tab-share immediately) — §1 quick win.
- [ ] Serialize session-state writes (per-session lock) — closes the Redis
      lost-update race.
- [ ] (Optional, flag-gated) automatic LLM provider failover Gemini ⇄ OpenAI on
      live-path failure.

**Done when:** the pull-the-plug test passes — disable Wi-Fi for 30s mid-call,
re-enable, and the same session continues with full history; a rep who forgets tab
audio is warned within 15 seconds.

---

## Phase 4 — Production Deployment (§4)   *~2–3 days*

Today's compose file is a dev stack. This phase creates the thing you can actually
put a customer on.

- [ ] `docker-compose.prod.yml`: frontend built with `vite build`, served as static
      files (nginx/caddy); backend via uvicorn **without** `--reload`; TLS terminated
      at the reverse proxy.
- [ ] Alembic: initial migration generated from current models; `create_all` retired
      for production; migration step wired into deploy.
- [ ] Nightly backups: `pg_dump` + Qdrant snapshot, copied off-box; a written,
      tested restore procedure.
- [ ] Pin all dependencies with a lockfile (`uv` or `pip-tools`); commit it.
- [ ] A one-page `DEPLOY.md`: fresh-VM to running-app, every step.

**Done when:** you can deploy to a clean VM by following `DEPLOY.md` only, restore
yesterday's backup on a second machine, and the app serves over HTTPS.

---

## Phase 5 — CI + Observability (§7)   *~1–2 days*

- [ ] GitHub Actions on every push: `ruff` + `pytest` + `tsc --noEmit`;
      `eval_rag.py` against a Qdrant service container (retrieval quality gate).
- [ ] Sentry (or equivalent) on backend + frontend — unhandled errors page you.
- [ ] Ops metrics page (can live inside the existing Analytics page): p50/p95 of
      `suggestions.latency_ms`, calls/day, analysis failure rate.
- [ ] OTel export enabled in production config.

**Done when:** a deliberately broken test blocks the merge; a deliberately thrown
exception in prod shows up in the error tracker within a minute.

---

## Phase 6 — Analysis Robustness (§6)   *~1 day*

- [ ] Startup sweep: conversations stuck in `analyzing`/`running` beyond N minutes are
      re-queued (or marked failed with a visible reason).
- [ ] Auto-retry failed analyses with backoff (periodic task; no queue infra needed).
- [ ] Localize `_DUPLICATE_NUDGE` (last hardcoded-English user-facing string).

**Done when:** killing the backend mid-analysis and restarting produces a completed
report with no human intervention; a Hindi call's nudge is not English.

---

## Phase 7 — Latency, Round 2 (§5)   *~2 days*

- [ ] Async LLM path (`google-genai` async client) — deletes the thread-per-turn
      bridge in the transcript processor; cancellation becomes plain task cancellation.
- [ ] Speculative retrieval on Deepgram interim transcripts — retrieval runs while the
      customer is still talking; ~200–500ms off perceived latency.
- [ ] *(Business task, not code)*: move the Gemini key to a paid tier — still the
      single biggest latency/reliability lever.

**Done when:** measured p95 first-token latency drops vs. the Phase 5 dashboard
baseline; zero `threading.Thread` in the live path.

---

## Phase 8 — Multi-Tenancy (§3)   *gated: build when the second customer signs*

- [ ] `workspace_id` filter on every Qdrant search + answer-cache key.
- [ ] Per-workspace knowledge bases; user→workspace membership; roles (rep/manager).
- [ ] Workspace scoping on all conversation/analysis endpoints.

**Done when:** two test workspaces cannot see each other's documents, calls, or
cached answers — verified by an automated test.

---

## Phase 9 — Enterprise Audio Capture (§1)   *gated: after pilots reveal how reps call*

The strategic initiative — pick based on pilot data:
- Telephony integration (Twilio/Exotel media streams) if calls are dialer-based.
- Meeting-bot (Zoom/Meet/Teams APIs) if calls are meeting-based.
- Desktop capture app only as a fallback tier.

Plus the independent quick win at any point: Opus compression in the browser
(~10× less bandwidth, no WebRTC needed).

---

## Sequence summary

```
Phase 0  git + keys            ─ must be first
Phase 1  clarity pass          ─ before all feature work (churn needs git, avoids conflicts)
Phase 2  security              ─ before any real user
Phase 3  session resilience    ─ before pilots
Phase 4  prod deployment       ─ before first customer
Phase 5  CI + observability    ─ alongside/right after 4
Phase 6  analysis robustness   ─ anytime after 1; low risk
Phase 7  latency round 2       ─ after 5 (needs the baseline dashboard)
Phase 8  multi-tenancy         ─ when the second customer is real
Phase 9  enterprise capture    ─ when pilots say which prong
```

Rough total for Phases 0–7: **~10–14 working days** of focused effort.
