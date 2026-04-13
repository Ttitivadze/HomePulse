FROM python:3.12-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY config/ ./config/
COPY VERSION .

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Run as non-root user (note: Docker socket access requires the user to be in
# the docker group, or the socket GID must be passed via --group-add at runtime)
RUN useradd -r -s /bin/false homepulse && chown -R homepulse:homepulse /app/data
USER homepulse

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
