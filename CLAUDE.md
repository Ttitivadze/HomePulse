# CLAUDE.md - HomePulse

## How We Work

You are my development partner. Follow these principles at all times:

**Be truthful, honest, and transparent.** Never fake certainty, hide problems, or gloss over risks. State what you know, what you assume, and what still needs verification.

**Work through issues directly.** When problems come up, break them down, explain the cause, evaluate options, and solve them step by step instead of using shallow fixes.

**Explain each step clearly.** Tell me what you are doing, why you are doing it, what you expect to happen, and what tradeoffs or risks exist.

**Treat this as a collaboration.** Ask for my input when decisions involve tradeoffs, priorities, risk tolerance, or design preference. We help each other.

**Keep security and optimization in mind throughout the build.** Prefer clean, maintainable, efficient, and secure solutions over unnecessary complexity.

**After the app is complete, do a full review of the finished codebase with knowledge of the final result.** Analyze how the code could now be written more efficiently, cleanly, consistently, and maintainably, then propose and apply worthwhile improvements.

**After that, perform a full security review.** Identify all meaningful risks, vulnerabilities, weak assumptions, and missing safeguards. Rank them by severity and practicality. For each risk, explain what it is, why it matters, what it would take to mitigate it, how difficult the mitigation is, and whether it is realistic or easy to implement. Then address them one by one with my approval.

**Focus on practical improvements, not theoretical perfection.** Preserve working behavior while improving internals. Stay accountable by always making clear what we are doing, why, what changed, what risks remain, and what comes next.

## Project Overview

HomePulse is a Docker-hosted monitoring dashboard for homelab infrastructure. Python/FastAPI backend with a vanilla JavaScript frontend that aggregates data from Proxmox, Docker, media services (Radarr/Sonarr/Lidarr), streaming sessions (Jellyfin/Plex/Tautulli), and an embedded OpenClaw AI chat assistant. Includes a JWT-based account system with an admin settings panel for UI customization and service configuration management.

## Tech Stack

- **Backend**: Python 3.12, FastAPI 0.115.6, Uvicorn
- **Frontend**: Vanilla JavaScript (ES6+), HTML5, CSS3 — no build step, no framework
- **Deployment**: Docker + Docker Compose (with healthcheck, log rotation, resource limits)
- **HTTP Client**: httpx (async, shared client for connection reuse)
- **Auth**: PyJWT (HS256 tokens), bcrypt (password hashing)
- **Database**: SQLite (WAL mode, async via `asyncio.to_thread`)
- **Config**: Environment variables via python-dotenv + YAML display config (`config/config.yml`) + SQLite overrides from admin panel
- **Testing**: pytest + pytest-asyncio, httpx test client
- **Logging**: Python `logging` module under the `homepulse.*` namespace
- **Versioning**: Semantic versioning via `VERSION` file (currently 1.1.2)

## Repository Structure

```
├── backend/
│   ├── main.py              # FastAPI app, CORS, lifespan, /api/dashboard endpoint
│   ├── config.py            # Settings class (env vars + YAML + DB overrides, validation)
│   ├── cache.py             # In-memory TTL cache (15s default)
│   ├── database.py          # SQLite setup, schema, async query helpers
│   ├── auth.py              # JWT auth, login/setup endpoints, password hashing
│   ├── integrations/        # One module per external service
│   │   ├── proxmox.py       # Proxmox VE API client (parallel node fetches)
│   │   ├── docker_int.py    # Docker socket integration (parallel stats, display labels)
│   │   ├── arr.py           # Radarr/Sonarr/Lidarr + streaming (Jellyfin/Plex/Tautulli)
│   │   ├── openclaw.py      # OpenClaw chat proxy (standard + streaming)
│   │   └── settings.py      # Admin settings CRUD (UI prefs, services, users)
│   └── static/              # Frontend assets served by FastAPI
│       ├── index.html        # SPA shell, settings overlay, mobile-ready meta tags
│       ├── js/
│       │   ├── utils.js      # Shared escapeHtml/escapeAttr utilities
│       │   ├── app.js        # Dashboard logic, single-request refresh, streaming chat
│       │   ├── auth.js       # JWT token management (localStorage), login/setup
│       │   └── settings.js   # Settings panel (tabs, forms, section ordering)
│       └── css/
│           ├── style.css     # Dark theme, responsive grid, phone portrait breakpoint
│           └── settings.css  # Settings overlay, login form, users table
├── config/
│   └── config.yml           # Dashboard display settings (section toggles, container labels)
├── data/                    # SQLite database (created at runtime, gitignored)
├── tests/                   # pytest test suite (51 tests)
│   ├── conftest.py          # Shared fixtures (async_client, cache clearing, test DB)
│   ├── test_health.py       # Health + root endpoint tests
│   ├── test_dashboard.py    # Aggregated dashboard endpoint tests
│   ├── test_arr.py          # Radarr/Sonarr/Lidarr/Jellyfin/Plex/Tautulli streaming tests
│   ├── test_proxmox.py      # Proxmox endpoint tests
│   ├── test_docker.py       # Docker endpoint tests
│   ├── test_openclaw.py     # OpenClaw endpoint tests
│   ├── test_cache.py        # TTL cache unit tests
│   ├── test_auth.py         # Auth system tests (setup, login, JWT, status)
│   └── test_settings.py     # Settings tests (UI, users, services, validation)
├── VERSION                  # Semantic version (1.1.2)
├── LICENSE                  # MIT License
├── .env.example             # All environment variables with descriptions
├── .dockerignore            # Excludes tests, .git, data, docs from Docker image
├── .gitignore               # Python, IDE, OS artifacts, data/
├── Dockerfile               # Python 3.12-slim, healthcheck, non-root user, data dir
├── docker-compose.yml       # Port 8450->8000, named volume for SQLite, resource limits
├── requirements.txt         # Runtime dependencies (pinned versions)
└── requirements-dev.txt     # Test dependencies (pytest, pytest-asyncio)
```

## Running the Application

### Via Docker (production)

```bash
cp .env.example .env   # Fill in real values
docker compose up -d   # Accessible at http://localhost:8450
```

Access from any device on the LAN: `http://<server-ip>:8450` — CORS is enabled for all origins. On first visit, click the gear icon to create your admin account.

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

### Dashboard (public)

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

### Authentication

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/auth/status` | Check if first-run setup is needed |
| POST | `/api/auth/setup` | Create first admin account (one-time) |
| POST | `/api/auth/login` | Authenticate and receive JWT |
| GET | `/api/auth/me` | Current user info from JWT |

### Settings (admin-only, requires JWT)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/settings/ui` | Get global UI settings (public) |
| PUT | `/api/settings/ui` | Update UI settings (admin) |
| POST | `/api/settings/ui/reset` | Reset UI to defaults (admin) |
| GET | `/api/settings/services` | Get service configs, secrets masked (admin) |
| PUT | `/api/settings/services` | Update service config overrides (admin) |
| POST | `/api/settings/services/test` | Test service connectivity (admin) |
| GET | `/api/settings/users` | List all user accounts (admin) |
| POST | `/api/settings/users` | Create a new user (admin) |
| PUT | `/api/settings/users/{id}/admin` | Toggle admin status (admin) |
| PUT | `/api/settings/users/{id}/password` | Reset a user's password (admin) |
| DELETE | `/api/settings/users/{id}` | Delete a user (admin) |

The frontend uses `/api/dashboard` for the main 30-second refresh cycle. Individual endpoints are called for per-section retries.

## Configuration

**Environment variables** (`.env`): Service URLs, API keys, tokens, and `JWT_SECRET`. See `.env.example` for the full list. Never commit `.env` — it contains secrets. Invalid values (e.g. non-numeric `REFRESH_INTERVAL`) are caught at startup with a warning and fall back to defaults. If `JWT_SECRET` is not set, an ephemeral one is generated (sessions reset on restart).

**Display config** (`config/config.yml`): Dashboard title, section visibility toggles, and friendly Docker container label mappings. Loaded at startup by `config.py`. This file is safe to commit.

**Web UI overrides** (SQLite): Admins can configure service URLs/keys and UI preferences through the settings panel. These are stored in SQLite and take precedence over `.env` values. The database lives in `data/homepulse.db` (local) or `/app/data/homepulse.db` (Docker).

## Architecture & Conventions

### Backend

- **Async-first**: All endpoint handlers and HTTP calls are async (`async def`, `httpx.AsyncClient`)
- **CORS enabled**: `CORSMiddleware` allows all origins with GET, POST, PUT, DELETE so the dashboard works from any LAN device
- **Concurrent I/O**: `asyncio.gather` for parallel API calls within each integration; `asyncio.to_thread` for blocking Docker stats calls and SQLite operations
- **Shared HTTP client**: `arr.py` maintains a module-level `httpx.AsyncClient` reused by arr + openclaw integrations (avoids per-request TCP/TLS overhead). Closed during app shutdown via the FastAPI lifespan.
- **TTL cache**: `backend/cache.py` provides a 15-second in-memory cache. Integration `fetch_*` functions check the cache before making external calls. This absorbs brief service outages and reduces redundant requests during the 30-second refresh cycle.
- **Two-tier data functions**: Each integration exposes `fetch_*_data()` (returns a dict, never raises) and a router endpoint (raises `HTTPException` on error). The dashboard endpoint calls the `fetch_*` functions directly.
- **Router-per-integration**: Each integration is a separate module with its own `APIRouter`, mounted in `main.py` with a prefix
- **Settings singleton**: `backend/config.py` exposes a `settings` object with instance attributes — import it, don't instantiate `Settings` again. Loads DB overrides > env vars > defaults. Loads YAML display config and validates env vars at startup.
- **Authentication**: JWT (HS256) via `backend/auth.py`. Dashboard is public; only settings endpoints require admin auth via `require_admin` dependency. First-run setup creates the initial admin. Timing-safe login prevents user enumeration.
- **Database**: SQLite with WAL mode via `backend/database.py`. Async lock protects writes; reads are lock-free (WAL safe). Connection timeout of 5s. Schema auto-initialized on startup.
- **Graceful degradation**: Integrations return `{"configured": False}` when unconfigured, or `{"error": "..."}` on failure — never crash the app
- **Input validation**: Pydantic models validate all request bodies. Color values validated via regex. Section order validated against known sections. Service config keys validated against an allowlist.
- **Error handling**: Use `fastapi.HTTPException` for individual API errors; the `/api/dashboard` endpoint wraps exceptions per-section. Error messages sent to clients are generic (no internal paths or stack traces); details are logged server-side.
- **Security headers**: `SecurityHeadersMiddleware` adds `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy` to all responses.
- **Logging**: All modules use `logging.getLogger("homepulse.<module>")`. Errors and connection failures are logged so `docker logs` is useful for debugging.

### Frontend

- **No framework or bundler**: Plain ES6+ JavaScript with Fetch API
- **Single-request refresh**: `loadDashboard()` calls `/api/dashboard` once per cycle; all data arrives in one response
- **Per-section retry**: Error cards include a "Retry" button that re-fetches only the failed section via the individual endpoint
- **Streaming chat**: The chat panel uses `/api/openclaw/chat/stream` (SSE) to display tokens as they arrive, with a non-streaming fallback
- **Chat history trimming**: Only the last 50 messages are sent in each chat request to keep payloads bounded
- **"Last updated" display**: Header shows relative timestamp ("Updated 5s ago") refreshed every 5 seconds
- **OpenClaw status check**: The chat panel calls `/api/openclaw/status` on open and displays Online/Offline
- **Module pattern**: `App` object in `app.js`, `Auth` in `auth.js`, `Settings` in `settings.js`
- **XSS prevention**: `escapeHtml()` for text content, `_escAttr()` for HTML attribute contexts (escapes quotes). Both used consistently in template literals.
- **Settings panel**: Modal overlay with three tabs — Appearance (colors, font, density, section order), Services (API URLs/keys with test button), Accounts (create/delete users, toggle admin). First-run shows setup wizard.
- **Global UI theming**: CSS custom properties loaded from `/api/settings/ui` on every page load and applied to `:root`
- **Dark theme**: CSS variables in `style.css` for consistent theming
- **Mobile-optimized**: Two responsive breakpoints (768px tablet, 480px phone portrait), icon-only header buttons on phone, touch-friendly 44px targets, `viewport-fit=cover` for notched phones, safe-area-inset support, 16px inputs to prevent iOS auto-zoom

### Naming & Style

- Python: snake_case, type hints where present (not comprehensive)
- JavaScript: camelCase functions, template literals for HTML generation
- Files: snake_case for Python modules, kebab-case not used

## Adding a New Integration

1. Create `backend/integrations/<service_name>.py`
2. Define an `APIRouter` named `router`
3. Implement a `fetch_<service>_data()` async function that returns a dict (never raises)
4. Add a router endpoint that calls the fetch function and raises `HTTPException` on error
5. Add config fields to `backend/config.py` (with env var defaults and DB override support)
6. Register the router in `backend/main.py` with `app.include_router(...)`
7. Add the fetch function to the `/api/dashboard` `asyncio.gather` call
8. Add env vars to `.env.example`
9. Add the service keys to `SERVICE_KEYS` in `backend/integrations/settings.py`
10. Add a UI section in `static/index.html` and render logic in `static/js/app.js`
11. Add tests in `tests/test_<service>.py`

## Testing

Tests live in `tests/` and use **pytest** + **pytest-asyncio** with **httpx** `AsyncClient` as the test transport.

```bash
pytest tests/ -v          # Run all tests (51 currently)
pytest tests/ -k radarr   # Run tests matching "radarr"
```

Key patterns:
- `conftest.py` provides an `async_client` fixture (httpx wired to the FastAPI app), auto-clears the TTL cache between tests, and provides `init_db` / `admin_token` fixtures for auth/settings tests
- Integration tests mock the `fetch_*_data()` functions to avoid real network calls
- Auth/settings tests use a temporary SQLite database per test (via `tmp_path`)
- Unit tests (cache, settings) test module behavior directly

## Docker Notes

- **Healthcheck**: Dockerfile and Compose both define a healthcheck against `/api/health`
- **Log rotation**: Compose limits logs to 3 x 10MB files to prevent disk bloat
- **Resource limits**: 512MB memory cap (configurable in `docker-compose.yml`)
- **PYTHONUNBUFFERED=1**: Ensures real-time log output in `docker logs`
- **`.dockerignore`**: Excludes tests, .git, data, cache, and docs from the image
- The Docker socket is mounted read-only (`/var/run/docker.sock:/var/run/docker.sock:ro`) for container monitoring
- `config/config.yml` is also mounted read-only
- `homepulse_data` named volume persists the SQLite database across container recreates
- The container runs as a non-root `homepulse` user with `/app/data` owned by that user (Docker socket access requires group-add at runtime)
- Port mapping: host 8450 -> container 8000

## Versioning

HomePulse uses [Semantic Versioning](https://semver.org/). The version is stored in the `VERSION` file at the repo root and referenced in `backend/main.py`.

- `1.1.2` — Performance optimizations, mobile UX, code cleanup (current)
- `1.1.1` — Security hardening, input validation, XSS fixes
- `1.1.0` — Account system, admin settings panel, UI customization
- `1.0.0` — First stable public release

## Important Warnings

- **Never commit `.env`** — it contains API keys and tokens
- **Docker socket access** grants significant host privileges; keep the mount read-only
- The Proxmox integration may disable SSL verification (`PROXMOX_VERIFY_SSL=false`) — this is intentional for self-signed certs in homelab environments
- If both `PLEX_URL` and `TAUTULLI_URL` are set, you may see duplicate streaming sessions — use one or the other for Plex
- Service config overrides in the admin panel take precedence over `.env` — changes require a restart to take effect in the running `settings` singleton
- The SQLite database in `data/` contains user password hashes — treat it with the same care as `.env`

## Version Bump Checklist

When bumping the version, update ALL of these:
1. `VERSION` file (the source of truth)
2. `backend/main.py` fallback version string
3. `README.md` changelog section (add new entry at top) + versioning list
4. `CLAUDE.md` version references (currently lines mentioning version number — use replace_all)

## Design Decisions & Context

These are deliberate choices made during development. Don't revert without discussion:

- **Login is timing-safe**: `auth.py` uses a dummy bcrypt hash for non-existent users so login time doesn't reveal whether a username exists
- **Setup endpoint has TOCTOU protection**: `auth.py` wraps the INSERT in try/except to handle the race between the existence check and insert
- **Two escape functions exist for a reason**: `escapeHtml()` for text content, `escapeAttr()` for HTML attribute contexts (escapes quotes). Both in `utils.js`, delegated from app.js and settings.js
- **Color values are regex-validated on the backend**: `settings.py` validates `#hex`, `rgb()`, and `hsl()` patterns before storing. This prevents CSS injection via the `setProperty` calls in the frontend
- **Section order is validated against an allowlist**: Only `["proxmox", "docker", "arr", "streaming"]` are accepted
- **Proxmox and arr use different client patterns but same principle**: Both reuse a module-level `httpx.AsyncClient`, closed in the lifespan shutdown. Proxmox client includes base_url and auth headers; arr client is generic.
- **Docker stats concurrency is already correct**: `docker_int.py` uses `asyncio.gather` with `asyncio.to_thread` per container — they run in parallel, not sequentially. No need to refactor.
- **Chat streaming uses a fast-path render**: During streaming, only the last message's `textContent` is updated (no innerHTML rebuild). Full rebuild happens only when a new message is added.
- **SQLite uses a persistent connection**: `database.py` reuses a single connection with `check_same_thread=False`. The async `_lock` protects writes; reads are lock-free (safe under WAL mode).

## Known Deferred Items

These were identified but intentionally deferred — not forgotten:

- **No rate limiting on login**: Brute force is possible. Would need `slowapi` or similar middleware. Low risk on a LAN-only homelab.
- **No CSRF protection**: State-changing endpoints (PUT/DELETE) don't use CSRF tokens. Low risk since CORS restricts origins and JWT is in Authorization header (not cookies).
- **Streaming session code duplication**: `arr.py` has similar fetch/parse patterns for Jellyfin, Plex, and Tautulli (~150 lines). Could be consolidated but works correctly as-is.
- **Settings singleton doesn't hot-reload DB overrides**: After changing service configs via the admin panel, the `settings` object in `config.py` still holds the old values until restart. This is documented in the admin panel ("Restart to apply").
