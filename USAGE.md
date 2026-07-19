# AI Sales Assistant (Powered by HubCode) — How to run

## What you have

- **Backend (FastAPI)**: Speech → Deepgram (streaming) → transcript → RAG (Qdrant + Gemini) → **suggested reply** + **sources** over WebSocket.
- **React UI (`frontend/`)**: Streams your **microphone** as PCM to `/ws/realtime` and shows suggestions in real time.

Browsers **cannot** automatically capture “both sides” of Zoom/Teams/Meet (your voice + remote participants) as one stream without OS-level routing. For that you use a **virtual audio device** (VB-Cable, VoiceMeeter) or a **desktop/Electron** app. The UI explains this inline.

---

## 1. Prerequisites

- Python 3.11+
- Node 18+ (for the React app)
- Docker (optional) for Qdrant + Redis
- API keys in `.env`: `GEMINI_API_KEY`, `DEEPGRAM_API_KEY`
- Qdrant populated (run ingest script) so retrieval returns chunks

---

## 2. Start dependencies

**Qdrant** (example):

```bash
docker run -p 6333:6333 qdrant/qdrant
```

**Ingest knowledge** (from project root, with Qdrant up):

```bash
python -m app.scripts.ingest_data
```

---

## 3. Start the API

From the project root:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- REST: `POST /api/v1/ask` (optional header `X-API-Key` if `INTERNAL_API_KEY` is set)
- WebSocket: `ws://localhost:8000/ws/realtime` (optional `?api_key=` or header `x-api-key`)
- Health: `GET http://localhost:8000/health/live`

For production, set `ENVIRONMENT=production` and required secrets (see `app/core/config.py`).

---

## 4. Start the React UI (recommended)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/ws`, `/api`, and `/health` to **port 8000**, so you do not need CORS for local dev.

1. Enter **API key** only if the server has `INTERNAL_API_KEY` set.
2. Click **Start session** — grant microphone access.
3. Speak; after Deepgram finalizes each phrase, you get **suggested reply** and **sources**.

**Direct WebSocket (no Vite)**  
If you host the UI elsewhere, point it at `ws://<api-host>:8000/ws/realtime` and set backend:

```env
CORS_ORIGINS=http://localhost:5173,https://your-ui-host
```

---

## 5. “Background” + calls / Meet

- **Run API in background**: Windows Task Scheduler, `nssm`, systemd, or Docker Compose; keep **one process** per machine or scale with sticky sessions + Redis.
- **Hear both caller and rep in one stream**:  
  - Route **meeting output + mic** into one **virtual input** (VB-Cable / VoiceMeeter) and choose that device as the browser mic, **or**  
  - Build an **Electron** app with `desktopCapturer` / native APIs.

This project’s browser UI captures **one** `getUserMedia` stream — that device should already be the **mixed** feed if you configured Windows/macOS that way.

---

## 6. Accuracy and latency

- **Accuracy**: Improve Qdrant data, chunking, `RECALL_K` / `TOP_K`, prompts (`app/modules/rag/prompts.py`), and run `python -m app.scripts.eval_rag`.
- **Latency**: Keep API near Deepgram/Gemini regions; tune reranking; consider streaming LLM tokens later.

---

## 7. Static HTML (legacy)

`static/index.html` is still served at `/ui/` for a no-build **POST /ask** tester. The React app is the path for **live WebSocket + mic**.

---

## 8. Docker

From the project root (with `.env` filled: `GEMINI_API_KEY`, `DEEPGRAM_API_KEY`, etc.):

```bash
docker compose up -d --build
```

- **React UI:** `http://localhost:5173` — Vite dev server with hot reload; proxies `/api`, `/ws`, `/health`, and `/docs` to the API (`frontend/Dockerfile` is only needed if you build a static nginx image yourself).
- **API:** `http://localhost:8000` (Swagger at `/docs`; optional legacy static UI at `/ui/` if `static/` is present in the image)
- Qdrant: `http://localhost:6333`
- Redis: `localhost:6379`

Compose sets `QDRANT_URL=http://qdrant:6333` and `REDIS_URL=redis://redis:6379` so the backend reaches dependencies by **service name** inside the network.

**Model cache**: `hf_model_cache` volume stores Hugging Face / sentence-transformers downloads so restarts are faster.

**Ingest knowledge into Qdrant** (required before RAG/ask works; creates collection `real_estate` from `app/data/raymond_realty.json`):

```bash
docker compose --profile ingest run --rm --build ingest
```

The `ingest` service does **not** load your host `.env` for `QDRANT_URL` (that often points to `localhost`, which is wrong inside a container). Compose sets `QDRANT_URL=http://qdrant:6333` automatically.

Or locally with Qdrant running on `localhost:6333`:

```bash
python -m app.scripts.ingest_data
```

**Default stack** uses Vite on **:5173** and API **`--reload`** with the repo bind-mounted (`docker compose up -d --build`).

**Resource limits** (Swarm/Kubernetes): set CPU/memory on the API pod/container (embedding + rerank + PyTorch are memory-heavy; **2–4 GiB** is a reasonable starting point).

If Qdrant’s healthcheck fails on your image tag (missing `wget`), change that service to `condition: service_started` or adjust the healthcheck command for your environment.
