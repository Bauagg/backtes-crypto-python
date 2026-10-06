# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------------------------
# Tahap 1: install dependency ke virtualenv terpisah (pip cache & build tools tidak ikut ke runtime).
# ---------------------------------------------------------------------------------------------
FROM python:3.13-slim AS builder
WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Hanya dependency runtime backend (bukan requirements.txt yang berisi alat notebook).
COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

# ---------------------------------------------------------------------------------------------
# Tahap 2: image runtime kecil — virtualenv + kode backend (main.py, src/). notebooks/ & docs/
# tidak ikut (lihat .dockerignore).
# ---------------------------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# Jalan sebagai user biasa, bukan root.
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app main.py ./
COPY --chown=app:app src ./src

USER app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8080
EXPOSE 8080

# /health tidak butuh API key; container ditandai unhealthy kalau API tidak menjawab.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4); sys.exit(0)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
