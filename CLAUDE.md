# CLAUDE.md - HomeLab Dashboard

## Project Overview

A Docker-hosted monitoring dashboard for homelab infrastructure. Python/FastAPI backend with a vanilla JavaScript frontend that aggregates data from Proxmox, Docker, media services (Radarr/Sonarr/Lidarr), Plex (via Tautulli), and an embedded OpenClaw AI chat assistant.

## Tech Stack

- **Backend**: Python 3.12, FastAPI 0.115.6, Uvicorn
- **Frontend**: Vanilla JavaScript (ES6+), HTML5, CSS3 — no build step, no framework
- **Deployment**: Docker + Docker Compose
- **HTTP Client**: httpx (async)
- **Config**: Environment variables via python-dotenv + YAML display config

## Repository Structure

```
├── backend/
│   ├── main.py              # FastAPI app entry point, routers, static mount
│   ├── config.py            # Settings class (loads env vars)
│   ├── integrations/        # One module per external service
│   │   ├── proxmox.py       # Proxmox VE API client
│   │   ├── docker_int.py    # Docker socket integration
│   │   ├── arr.py           # Radarr/Sonarr/Lidarr/Tautulli APIs
│   │   └── openclaw.py      # OpenClaw chat proxy (standard + streaming)
│   └── static/              # Frontend assets served by FastAPI
│       ├── index.html
│       ├── js/app.js         # SPA logic, auto-refresh, chat UI
│       └── css/style.css     # Dark theme, responsive grid
├── config/
│   └── config.yml           # Dashboard display settings (section toggles, labels)
├── .env.example             # All required environment variables
├── Dockerfile               # Python 3.12-slim, single stage
├── docker-compose.yml       # Port 8450->8000, docker socket mount
└── requirements.txt         # Python dependencies (pinned versions)
```

## Running the Application

### Via Docker (production)

```bash
cp .env.example .env   # Fill in real values
docker compose up -d   # Accessible at http://localhost:8450
```

### Local development (without Docker)

```bash
pip install -r requirements.txt
cp .env.example .env   # Fill in real values
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

The dashboard is then at `http://localhost:8000`.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Dashboard UI (serves index.html) |
| GET | `/api/health` | Health check |
| GET | `/api/proxmox/status` | Proxmox nodes, VMs, LXC containers |
| GET | `/api/docker/containers` | Docker container list with stats |
| GET | `/api/arr/radarr` | Movie library stats + download queue |
| GET | `/api/arr/sonarr` | TV show stats + download queue |
| GET | `/api/arr/lidarr` | Music library stats + download queue |
| GET | `/api/arr/streaming` | Active Plex streams (Tautulli) |
| GET | `/api/openclaw/status` | OpenClaw connection check |
| POST | `/api/openclaw/chat` | Chat message (JSON response) |
| POST | `/api/openclaw/chat/stream` | Chat message (streaming response) |

## Configuration

**Environment variables** (`.env`): Service URLs, API keys, and tokens for all integrations. See `.env.example` for the full list. Never commit `.env` — it contains secrets.

**Display config** (`config/config.yml`): Dashboard title, refresh interval, section visibility toggles, and friendly Docker container labels. This file is safe to commit.

## Architecture & Conventions

### Backend

- **Async-first**: All endpoint handlers and HTTP calls are async (`async def`, `httpx.AsyncClient`)
- **Router-per-integration**: Each integration is a separate module with its own `APIRouter`, mounted in `main.py` with a prefix
- **Settings singleton**: `backend/config.py` exposes a `settings` object — import it, don't instantiate `Settings` again
- **Graceful degradation**: Integrations return error responses when unconfigured or unreachable rather than crashing the app
- **Error handling**: Use `fastapi.HTTPException` for API errors

### Frontend

- **No framework or bundler**: Plain ES6+ JavaScript with Fetch API
- **Module pattern**: `App` object in `app.js` with methods for each dashboard section
- **Auto-refresh**: `setInterval` at 30-second default (configurable)
- **XSS prevention**: HTML-escape user content before inserting into DOM
- **Dark theme**: CSS variables in `style.css` for consistent theming

### Naming & Style

- Python: snake_case, type hints where present (not comprehensive)
- JavaScript: camelCase functions, template literals for HTML generation
- Files: snake_case for Python modules, kebab-case not used

## Adding a New Integration

1. Create `backend/integrations/<service_name>.py`
2. Define an `APIRouter` named `router`
3. Add async endpoint(s) using `httpx.AsyncClient` for external calls
4. Add config fields to `backend/config.py` (with env var defaults)
5. Register the router in `backend/main.py` with `app.include_router(...)`
6. Add env vars to `.env.example`
7. Add a UI section in `static/index.html` and fetch logic in `static/js/app.js`

## Testing & CI

No test suite or CI pipeline exists yet. When adding tests:

- Use **pytest** + **pytest-asyncio** for backend tests
- Use **httpx** test client (`from httpx import ASGITransport, AsyncClient`) for API endpoint tests
- Place tests in a `tests/` directory at the project root

## Docker Notes

- The Docker socket is mounted read-only (`/var/run/docker.sock:/var/run/docker.sock:ro`) for container monitoring
- `config/config.yml` is also mounted read-only
- The container runs as root (required for Docker socket access)
- Port mapping: host 8450 -> container 8000

## Important Warnings

- **Never commit `.env`** — it contains API keys and tokens
- **Docker socket access** grants significant host privileges; keep the mount read-only
- The Proxmox integration may disable SSL verification (`PROXMOX_VERIFY_SSL=false`) — this is intentional for self-signed certs in homelab environments
