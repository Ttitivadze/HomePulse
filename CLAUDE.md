# CLAUDE.md - HomeLab Dashboard

## Project Overview

A Docker-hosted monitoring dashboard for homelab infrastructure. Python/FastAPI backend with a vanilla JavaScript frontend that aggregates data from Proxmox, Docker, media services (Radarr/Sonarr/Lidarr), streaming sessions (Jellyfin/Plex/Tautulli), and an embedded OpenClaw AI chat assistant.

## Tech Stack

- **Backend**: Python 3.12, FastAPI 0.115.6, Uvicorn
- **Frontend**: Vanilla JavaScript (ES6+), HTML5, CSS3 — no build step, no framework
- **Deployment**: Docker + Docker Compose (with healthcheck, log rotation, resource limits)
- **HTTP Client**: httpx (async, shared client for connection reuse)
- **Config**: Environment variables via python-dotenv + YAML display config (`config/config.yml`)
- **Testing**: pytest + pytest-asyncio, httpx test client
- **Logging**: Python `logging` module under the `homelab.*` namespace

## Repository Structure

```
├── backend/
│   ├── main.py              # FastAPI app, CORS, lifespan, /api/dashboard endpoint
│   ├── config.py            # Settings class (env vars + YAML config, validation)
│   ├── cache.py             # In-memory TTL cache (15s default)
│   ├── integrations/        # One module per external service
│   │   ├── proxmox.py       # Proxmox VE API client (parallel node fetches)
│   │   ├── docker_int.py    # Docker socket integration (parallel stats, display labels)
│   │   ├── arr.py           # Radarr/Sonarr/Lidarr + streaming (Jellyfin/Plex/Tautulli)
│   │   └── openclaw.py      # OpenClaw chat proxy (standard + streaming)
│   └── static/              # Frontend assets served by FastAPI
│       ├── index.html        # Mobile-ready meta tags, dark theme-color
│       ├── js/app.js         # SPA logic, single-request refresh, streaming chat
│       └── css/style.css     # Dark theme, responsive grid
├── config/
│   └── config.yml           # Dashboard display settings (section toggles, container labels)
├── tests/                   # pytest test suite
│   ├── conftest.py          # Shared fixtures (async_client, cache clearing)
│   ├── test_health.py       # Health + root endpoint tests
│   ├── test_dashboard.py    # Aggregated dashboard endpoint tests
│   ├── test_arr.py          # Radarr/Sonarr/Lidarr/Jellyfin/Plex/Tautulli streaming tests
│   ├── test_proxmox.py      # Proxmox endpoint tests
│   ├── test_docker.py       # Docker endpoint tests
│   ├── test_openclaw.py     # OpenClaw endpoint tests
│   └── test_cache.py        # TTL cache unit tests
├── .env.example             # All environment variables with descriptions
├── .dockerignore            # Excludes tests, .git, cache from Docker image
├── .gitignore               # Python, IDE, OS artifacts
├── Dockerfile               # Python 3.12-slim, healthcheck, curl
├── docker-compose.yml       # Port 8450->8000, resource limits, log rotation
├── requirements.txt         # Runtime dependencies (pinned versions)
└── requirements-dev.txt     # Test dependencies (pytest, pytest-asyncio)
```

## Running the Application

### Via Docker (production)

```bash
cp .env.example .env   # Fill in real values
docker compose up -d   # Accessible at http://localhost:8450
```

Access from any device on the LAN: `http://<server-ip>:8450` — CORS is enabled for all origins.

### Local development (without Docker)

```bash
pip install -r requirements.txt
cp .env.example .env   # Fill in real values
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

The dashboard is then at `http://localhost:8000`.

### Running tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Dashboard UI (serves index.html) |
| GET | `/api/health` | Health check (used by Docker HEALTHCHECK) |
| GET | `/api/dashboard` | **All sections in one request** (concurrent fetch) |
| GET | `/api/proxmox/status` | Proxmox nodes, VMs, LXC containers |
| GET | `/api/docker/containers` | Docker container list with stats |
| GET | `/api/arr/radarr` | Movie library stats + download queue |
| GET | `/api/arr/sonarr` | TV show stats + download queue |
| GET | `/api/arr/lidarr` | Music library stats + download queue |
| GET | `/api/arr/streaming` | Active streams (Jellyfin, Plex, and/or Tautulli) |
| GET | `/api/openclaw/status` | OpenClaw connection check |
| POST | `/api/openclaw/chat` | Chat message (JSON response) |
| POST | `/api/openclaw/chat/stream` | Chat message (streaming SSE response) |

The frontend uses `/api/dashboard` for the main 30-second refresh cycle. Individual endpoints are called for per-section retries.

## Configuration

**Environment variables** (`.env`): Service URLs, API keys, and tokens for all integrations. See `.env.example` for the full list. Never commit `.env` — it contains secrets. Invalid values (e.g. non-numeric `REFRESH_INTERVAL`) are caught at startup with a warning and fall back to defaults.

**Display config** (`config/config.yml`): Dashboard title, section visibility toggles, and friendly Docker container label mappings. Loaded at startup by `config.py`. This file is safe to commit.

## Architecture & Conventions

### Backend

- **Async-first**: All endpoint handlers and HTTP calls are async (`async def`, `httpx.AsyncClient`)
- **CORS enabled**: `CORSMiddleware` allows all origins so the dashboard works from any LAN device
- **Concurrent I/O**: `asyncio.gather` for parallel API calls within each integration; `asyncio.to_thread` for blocking Docker stats calls
- **Shared HTTP client**: `arr.py` maintains a module-level `httpx.AsyncClient` reused by arr + openclaw integrations (avoids per-request TCP/TLS overhead). Closed during app shutdown via the FastAPI lifespan.
- **TTL cache**: `backend/cache.py` provides a 15-second in-memory cache. Integration `fetch_*` functions check the cache before making external calls. This absorbs brief service outages and reduces redundant requests during the 30-second refresh cycle.
- **Two-tier data functions**: Each integration exposes `fetch_*_data()` (returns a dict, never raises) and a router endpoint (raises `HTTPException` on error). The dashboard endpoint calls the `fetch_*` functions directly.
- **Router-per-integration**: Each integration is a separate module with its own `APIRouter`, mounted in `main.py` with a prefix
- **Settings singleton**: `backend/config.py` exposes a `settings` object with instance attributes — import it, don't instantiate `Settings` again. Instance-based `__init__` allows overriding in tests. Loads YAML display config and validates env vars at startup.
- **Graceful degradation**: Integrations return `{"configured": False}` when unconfigured, or `{"error": "..."}` on failure — never crash the app
- **Error handling**: Use `fastapi.HTTPException` for individual API errors; the `/api/dashboard` endpoint wraps exceptions per-section
- **Logging**: All modules use `logging.getLogger("homelab.<module>")`. Errors and connection failures are logged so `docker logs` is useful for debugging.

### Frontend

- **No framework or bundler**: Plain ES6+ JavaScript with Fetch API
- **Single-request refresh**: `loadDashboard()` calls `/api/dashboard` once per cycle; all data arrives in one response
- **Per-section retry**: Error cards include a "Retry" button that re-fetches only the failed section via the individual endpoint
- **Streaming chat**: The chat panel uses `/api/openclaw/chat/stream` (SSE) to display tokens as they arrive, with a non-streaming fallback
- **Chat history trimming**: Only the last 50 messages are sent in each chat request to keep payloads bounded
- **"Last updated" display**: Header shows relative timestamp ("Updated 5s ago") refreshed every 5 seconds
- **OpenClaw status check**: The chat panel calls `/api/openclaw/status` on open and displays Online/Offline
- **Module pattern**: `App` object in `app.js` with methods for each dashboard section
- **XSS prevention**: HTML-escape user content before inserting into DOM
- **Dark theme**: CSS variables in `style.css` for consistent theming
- **Mobile-ready**: Viewport, theme-color, and apple-mobile-web-app meta tags

### Naming & Style

- Python: snake_case, type hints where present (not comprehensive)
- JavaScript: camelCase functions, template literals for HTML generation
- Files: snake_case for Python modules, kebab-case not used

## Adding a New Integration

1. Create `backend/integrations/<service_name>.py`
2. Define an `APIRouter` named `router`
3. Implement a `fetch_<service>_data()` async function that returns a dict (never raises)
4. Add a router endpoint that calls the fetch function and raises `HTTPException` on error
5. Add config fields to `backend/config.py` (with env var defaults)
6. Register the router in `backend/main.py` with `app.include_router(...)`
7. Add the fetch function to the `/api/dashboard` `asyncio.gather` call
8. Add env vars to `.env.example`
9. Add a UI section in `static/index.html` and render logic in `static/js/app.js`
10. Add tests in `tests/test_<service>.py`

## Testing

Tests live in `tests/` and use **pytest** + **pytest-asyncio** with **httpx** `AsyncClient` as the test transport.

```bash
pytest tests/ -v          # Run all tests
pytest tests/ -k radarr   # Run tests matching "radarr"
```

Key patterns:
- `conftest.py` provides an `async_client` fixture (httpx wired to the FastAPI app) and auto-clears the TTL cache between tests
- Integration tests mock the `fetch_*_data()` functions to avoid real network calls
- Unit tests (cache, settings) test module behavior directly

## Docker Notes

- **Healthcheck**: Dockerfile and Compose both define a healthcheck against `/api/health`
- **Log rotation**: Compose limits logs to 3 x 10MB files to prevent disk bloat
- **Resource limits**: 512MB memory cap (configurable in `docker-compose.yml`)
- **PYTHONUNBUFFERED=1**: Ensures real-time log output in `docker logs`
- **`.dockerignore`**: Excludes tests, .git, cache, and docs from the image
- The Docker socket is mounted read-only (`/var/run/docker.sock:/var/run/docker.sock:ro`) for container monitoring
- `config/config.yml` is also mounted read-only
- The container runs as root (required for Docker socket access)
- Port mapping: host 8450 -> container 8000

## Important Warnings

- **Never commit `.env`** — it contains API keys and tokens
- **Docker socket access** grants significant host privileges; keep the mount read-only
- The Proxmox integration may disable SSL verification (`PROXMOX_VERIFY_SSL=false`) — this is intentional for self-signed certs in homelab environments
- If both `PLEX_URL` and `TAUTULLI_URL` are set, you may see duplicate streaming sessions — use one or the other for Plex
