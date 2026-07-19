# -----------------------------------------------------------------------------
# AI Calling Assistant — API image (FastAPI + sentence-transformers + RAG)
# Single worker: in-process embedding/rerank models + WebSockets do not scale
# horizontally without sticky sessions / shared model servers.
#
# Build notes:
# - torch is installed CPU-only FIRST. Otherwise `sentence-transformers` drags in
#   ~2.5 GB of NVIDIA CUDA wheels the container can never use — that alone was
#   ~20 minutes of build time and a source of corrupted-download failures.
# - Pip's download cache persists across builds via a BuildKit cache mount, so
#   rebuilding after a requirements change re-downloads only what changed.
# -----------------------------------------------------------------------------

FROM python:3.11-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="ai-calling-assistant-api" \
      org.opencontainers.image.description="FastAPI RAG + realtime speech assistant"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    HOME=/home/appuser \
    HF_HOME=/home/appuser/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/appuser/.cache/huggingface \
    # Reduce thread oversubscription in small containers
    OMP_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2

WORKDIR /app

# Runtime libs: curl (healthcheck), libgomp1 (numpy/torch/sentence-transformers)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Layer cache: deps before app code
COPY requirements.txt .

# CPU-only torch first (see build notes), then the rest; drop the compiler
# toolchain afterwards to shrink attack surface & image size.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Application (respect .dockerignore)
COPY app ./app

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app /home/appuser/.cache

USER appuser

EXPOSE 8000

# First request may load the embedding + reranker models — allow warm-up
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health/live || exit 1

# One process: shared model singleton + WebSocket sessions
CMD [ \
    "uvicorn", "app.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--proxy-headers", \
    "--timeout-keep-alive", "120" \
]
