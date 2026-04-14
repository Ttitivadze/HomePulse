# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# HomePulse — multi-stage build
#
# Stage 1 (builder): install Python deps into a cache-friendly virtualenv.
# Stage 2 (runtime): slim image with only the venv + application code.
#
# Why split? Copying the app source (which changes on every commit) used
# to invalidate the pip-install layer in the single-stage Dockerfile,
# making every `docker compose up --build` reinstall every dependency.
# With a separate builder stage, requirements.txt is the only thing the
# dep layer depends on, so local iteration only rebuilds the app layer.
# ---------------------------------------------------------------------------

# ---------- Stage 1: builder ----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build-time tooling for any pip package that needs to compile C
# extensions. Kept out of the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated venv under /opt/venv so the runtime stage can copy
# a single directory over without reasoning about site-packages layouts.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dependencies first — this layer is only invalidated when
# requirements.txt changes.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime deps: curl for the healthcheck only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the prepared virtualenv from the builder.
COPY --from=builder /opt/venv /opt/venv

# Application code — this layer is the one that actually changes per
# commit, and it doesn't invalidate anything above it.
COPY backend/ ./backend/
COPY config/ ./config/
COPY VERSION .

# Writable data directory for the SQLite database.
RUN mkdir -p /app/data

# Run as non-root. Docker socket access is configured by the host
# operator via DOCKER_GID + group_add in docker-compose.yml.
RUN useradd -r -s /bin/false homepulse && chown -R homepulse:homepulse /app/data
USER homepulse

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
