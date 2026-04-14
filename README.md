# HomePulse

A self-hosted monitoring dashboard for your homelab. See your entire infrastructure at a glance — Proxmox nodes, Docker containers, media libraries, active streams, and an AI chat assistant — all in one dark-themed, mobile-friendly page.

[![tests](https://github.com/Ttitivadze/HomePulse/actions/workflows/tests.yml/badge.svg)](https://github.com/Ttitivadze/HomePulse/actions/workflows/tests.yml)
[![docker](https://github.com/Ttitivadze/HomePulse/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Ttitivadze/HomePulse/actions/workflows/docker-publish.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![License: MIT](https://img.shields.io/badge/license-MIT-purple)

## Changelog

### v2.1.0

Minor release focused on broader-market polish: onboarding, CI/CD,
parity with other homelab dashboards, and internal code quality. No
breaking changes.

**New widgets**
- **Bookmarks / app launcher** — Admin-curated grid of quick-launch
  links on the dashboard. Optional grouping and emoji/image icons.
  URL allow-list (http/https/mailto) blocks XSS via malicious schemes.
- **HomePulse Host** — Self-monitoring card showing CPU load, memory
  usage, system + process uptime, and HomePulse's own RSS, scraped
  from `/proc`. Competing dashboards don't ship this.

**Distribution & onboarding**
- **Published Docker image** — `ghcr.io/ttitivadze/homepulse:latest`
  (multi-arch: `linux/amd64` + `linux/arm64`). End users can
  `docker compose pull` instead of `docker compose build`.
- **GitHub Actions CI** — pytest runs on every push to main and on
  PRs; new status badges in the README.
- **Multi-stage Dockerfile** — Code changes no longer invalidate the
  `pip install` layer; local rebuilds are much faster.
- **PWA manifest + icons** — "Add to Home Screen" installs HomePulse
  as a standalone app on iOS and Android.
- **Rewritten Quick Start** — Three paths (GHCR image, minimum-viable
  `.env`, build from source) so strangers get running in minutes.

**Security & hardening**
- `DASHBOARD_REQUIRE_AUTH=true` now narrows CORS to
  `ALLOWED_ORIGINS` instead of leaving `*` wide open. `allow_credentials`
  is explicitly `False` (no cookies).
- `Path(ge=1)` on every `{id}` path parameter across settings and
  api-keys endpoints — zero/negative IDs return 422 instead of
  reaching the DB layer.
- `REGISTRY_AUTH_JSON` env var lets operators configure per-registry
  credentials for private image update checks.

**Code quality**
- New `backend/integrations/_status.py` exposes `ok()` / `failure()`
  / `unconfigured()` so every integration returns the same envelope.
- New `backend.cache.TTL` class centralises every cache TTL — no more
  magic numbers scattered across modules.
- `arr.py`'s `_fetch` and `_fetch_tautulli` consolidated around a
  shared `_api_get` helper.
- Dead `config.yml` `sections:` block removed (unused since v1.1).
- Stale OpenClaw references scrubbed from README/CLAUDE.md/.env.example.

**Tests**
- 128 tests (up from 116). New modules for bookmarks, self-stats;
  regression cases for Path validation, CORS gating, container-update
  registry auth, NAS mount statvfs.

### v2.0.0

Major release. This version consolidates the unreleased 1.3.0 homelab work
and adds new features on top. Breaking change: `OpenClaw` chat integration
is removed in favour of Anthropic Claude.

- **Claude AI chat** — Replaces OpenClaw. Uses `AsyncAnthropic` (non-blocking), keeps the existing streaming-SSE frontend. New env vars: `CLAUDE_API_KEY`, `CLAUDE_MODEL`.
- **Uptime Kuma integration** — New dashboard section showing monitoring status with a one-click open link. Env: `UPTIME_KUMA_URL`.
- **Infrastructure monitoring** — Combined widget for storage usage (Proxmox API), last-backup status per CT, and SSL cert expiry countdown (NPM API). Env: `NPM_URL`, `NPM_API_TOKEN`.
- **Telegram notifications** — Framework for sending alerts with a `POST /api/notifications/test` smoke endpoint. Env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- **Login rate limiting** — 5 failed attempts / IP / 60 s returns 429. In-memory, no extra dependency.
- **Settings hot-reload** — Service config changes via the admin panel apply immediately; no restart required.
- **Light theme + theme toggle** — CSS-variable-driven light theme, toggle button in the header, persisted in `localStorage`.
- **Container update badges** — Frontend shows "Update" on containers whose running image digest differs from the registry's `latest`. Cached 6 h per image to respect Docker Hub's rate limit; capped at 3 uncached lookups per refresh cycle.
- **Settings live preview** — Appearance tab applies changes in real time via `setProperty`; a "Preview active — Save to persist" indicator appears and auto-reverts on cancel/close.
- **External API keys** — New `API Keys` settings tab. Admins issue `hp_…` keys (bcrypt-hashed in DB, plaintext shown once). Optional `DASHBOARD_REQUIRE_AUTH` env var gates the dashboard behind JWT or `X-API-Key`.
- **docker_links** — Error-path Docker responses now include the `docker_links` mapping so the frontend can still render per-container URLs even when the socket is unreachable (Report #2 bug).
- **Bump script** — `scripts/bump-version.sh <version>` updates `VERSION`, `backend/main.py`, `CLAUDE.md`, and `README.md` in one shot.
- **Tests** — 93 tests (up from 66). New modules for Claude, Uptime Kuma, Infrastructure, Notifications, rate-limit, API keys, container updates; regression test for docker_links on error paths.

### v1.2.4
- **Cache-busting**: All CSS/JS references now include `?v={version}` query params — browsers automatically fetch fresh files on redeploy, no manual cache clearing needed
- **Version in header**: App version displayed next to "HomePulse" title in the header
- **Cache headers**: `Cache-Control: no-cache` on index.html (always check for updates), `Cache-Control: public, max-age=86400` on static assets (cached 24h, busted by version param)

### v1.2.3
- **UX**: Login form now dismisses on successful authentication and reopens directly into the settings panel — no lingering login window

### v1.2.2
- **Bugfix**: Frontend no longer crashes on missing/incomplete arrays in API responses — all `.map()`, `.filter()`, `.length` calls now use safe defaults
- **UX**: Render exceptions now show "received data but failed to render" instead of the misleading "Failed to connect" — backend and frontend errors are clearly distinguished
- **Logging**: Render errors logged to browser console with full stack traces for debugging

### v1.2.1
- **Bugfix**: Docker socket permission detection — shows "Docker socket mounted but not accessible" instead of "not configured" when the container user lacks socket group permissions
- **Config**: New `DOCKER_GID` env var passed via `group_add` in docker-compose.yml so the non-root container can access the host Docker socket
- **Docs**: Updated README, `.env.example`, and CLAUDE.md with Docker socket setup instructions

### v1.2.0
- **Multi-instance support** — Connect multiple Proxmox VE and Docker hosts, managed entirely through the admin panel with "Add Instance" buttons (no `.env` clutter)
- **Docker card overhaul** — Removed image tag and port text; added clickable service link (opens container's web UI in a new tab); status badge moved to top-left
- **Download queue filtering** — Media Library queue now only shows active (incomplete) downloads, with first 3 visible and a "Show More" expand button
- **Proxmox open link** — "Open" button on Proxmox section to launch the web UI in a new tab
- **New `DOCKER_URL` setting** — Base URL for building Docker container web links
- **New DB table** `service_instances` — Stores additional Proxmox/Docker instances with JSON config blobs
- **New API endpoints** — Full CRUD for `/api/settings/instances` (list, create, update, delete, test connectivity)
- **Security**: Fix XSS in delete button handlers (switched to data-attribute event delegation)
- **Reliability**: Proper async Docker client cleanup, improved Proxmox error logging, consistent HTTP 503 for service failures
- **Tests**: 66 tests (up from 51)

### v1.1.2
- **Performance**: Persistent httpx client for Proxmox (reuse TCP/TLS connections across fetches)
- **Performance**: Persistent SQLite connection (eliminates per-query open/close overhead)
- **Performance**: Chat streaming renders only the last message in-place instead of full DOM rebuild
- **Performance**: Cache auto-cleans expired entries on read
- **UX**: 15s request timeout on admin API calls (prevents hanging UI)
- **UX**: Loading skeletons shown while Services/Users settings tabs fetch data
- **UX**: Mobile portrait optimizations — icon-only header, 480px breakpoint, 44px touch targets, safe-area-inset for notched phones
- **Cleanup**: Shared `utils.js` for escapeHtml/escapeAttr, DB username index, module-level imports

### v1.1.1
- **Security**: Fix CORS to allow PUT/DELETE methods (admin settings were blocked)
- **Security**: Fix XSS — add attribute-safe escaping for quotes in settings panel
- **Security**: Add CSS color validation and section order validation on backend
- **Security**: Timing-safe login to prevent user enumeration
- **Security**: Fix TOCTOU race condition in first-run setup endpoint
- **Hardening**: Add SQLite connection timeout, log DB override failures
- **Tests**: 5 new validation tests (invalid colors, section order, unknown config keys)

### v1.1.0
- **Account system** with admin privileges and JWT authentication
- **Settings panel** — admin-only gear icon with three tabs:
  - **Appearance**: accent/background/card/text colors, font selector, card density (compact/comfortable), drag section ordering
  - **Services**: manage all API URLs and keys from the web UI (overrides .env), with masked secrets
  - **Accounts**: create/delete users, promote/demote admins, password resets
- **First-run setup wizard** — creates initial admin on first visit
- **Global UI theming** — CSS custom properties driven from SQLite, applied on every page load
- **SQLite database** — persistent storage for accounts, UI prefs, and service config overrides
- Dashboard remains **public** — no login required to view; only settings requires admin auth

### v1.0.0
- First stable public release
- Proxmox VE, Docker, Radarr/Sonarr/Lidarr, Jellyfin/Plex/Tautulli, OpenClaw chat
- Single-request dashboard refresh, per-section retry, security headers, 24 tests

## Features

- **Proxmox VE** — Nodes, VMs, and LXC containers with live CPU/RAM bars, uptime, and a link to open the Proxmox web UI. Supports multiple independent Proxmox environments.
- **Docker** — Every container with status, resource usage, clickable service links, and friendly display names. Supports multiple Docker hosts (local socket + remote TCP).
- **Media Library** — Radarr (movies), Sonarr (TV), Lidarr (music) showing downloaded, requested, and missing counts plus active download queue (completed items filtered out, first 3 shown with expand)
- **Active Streams** — Jellyfin, Plex (direct), or Tautulli — see who's watching what, transcode status, and playback progress
- **Claude AI Chat** — Slide-out chat panel with streaming token display, backed by Anthropic's API. Ask questions about your homelab, get troubleshooting help, or use it as a general assistant.
- **Uptime Kuma** — Per-monitor status cards (requires `UPTIME_KUMA_METRICS_TOKEN`); falls back to a single reachability indicator otherwise
- **Infrastructure** — Storage usage (Proxmox + optional NAS mounts), last-backup status per CT, SSL cert expiry via NPM
- **Container updates** — Registry-digest comparison shows which containers have newer images available (6 h cached, rate-limit aware, private-registry auth supported)
- **Telegram notifications** — Send test alerts from the dashboard; framework ready for auto-triggers in 2.1
- **Light / dark theme** — Toggle in the header, persisted in localStorage
- **External API keys** — Issue `hp_…` keys for external tools; optional `DASHBOARD_REQUIRE_AUTH` gate accepts JWT or `X-API-Key`
- **Multi-instance support** — Add multiple Proxmox and Docker hosts through the admin panel — no `.env` numbering needed
- **Single-request refresh** — One API call fetches everything in parallel; 30-second auto-refresh cycle
- **Per-section retry** — If one service is down, retry just that section without reloading
- **Admin Settings** — Account system with UI customization (colors, fonts, layout), web-based service config management, and instance management
- **Mobile-ready** — Responsive grid, dark theme, iOS home screen support

## Quick Start

### Fastest path (pre-built image)

No build required — pull the published image from GHCR:

```bash
mkdir homepulse && cd homepulse

# Fetch the example compose file + .env template (no git clone needed)
curl -sSfL https://raw.githubusercontent.com/Ttitivadze/HomePulse/main/docker-compose.yml -o docker-compose.yml
curl -sSfL https://raw.githubusercontent.com/Ttitivadze/HomePulse/main/.env.example -o .env

# Swap `build: .` for the published image (one-time tweak)
sed -i 's|build: \.|image: ghcr.io/ttitivadze/homepulse:latest|' docker-compose.yml

docker compose up -d
```

Open **http://localhost:8450** (or `http://<server-ip>:8450` from any device on the LAN).
On the first visit, click the gear icon to create the admin account — everything else is configured from the in-app **Settings → Services** panel.

### Minimum viable `.env`

HomePulse ships with every integration **optional**. The smallest useful `.env` is:

```ini
# Host-visible Docker socket group (find with: stat -c '%g' /var/run/docker.sock)
DOCKER_GID=999
# Strong random string, anything 48+ chars. Sessions survive restarts when set.
JWT_SECRET=change-me-to-a-long-random-string
```

That's it — start the container and you'll see the Docker section populate. Add Proxmox / Radarr / Sonarr / Claude / etc. through the admin panel later (no restart needed for service config changes).

### Build from source (contributors)

```bash
git clone https://github.com/Ttitivadze/HomePulse.git
cd HomePulse
cp .env.example .env
docker compose up -d --build
```

Or run the FastAPI server directly:

```bash
pip install -r requirements.txt -r requirements-dev.txt
uvicorn backend.main:app --reload    # http://localhost:8000
pytest tests/ -q                     # run the suite
```

### Accessing the dashboard

- **Browser** — `http://<server-ip>:8450` works from any device on the LAN (CORS is wide-open by default)
- **Mobile** — visit the URL and use "Add to Home Screen"; the PWA manifest gives you a standalone app icon
- **External tools** — create an API key in **Settings → API Keys**, then `curl -H "X-API-Key: hp_…" http://<server>:8450/api/dashboard`

## Configuration

### Environment Variables (`.env`)

All integrations are optional — configure only the services you use.

| Variable | Description |
|---|---|
| **Proxmox** | |
| `PROXMOX_HOST` | Proxmox VE URL (e.g. `https://192.168.1.100:8006`) |
| `PROXMOX_USER` | API user (default: `root@pam`) |
| `PROXMOX_TOKEN_NAME` | API token name |
| `PROXMOX_TOKEN_VALUE` | API token value |
| `PROXMOX_VERIFY_SSL` | Verify SSL cert (`true`/`false`, default: `false`) |
| **Docker** | |
| `DOCKER_GID` | Host Docker group ID for socket access (find with `stat -c '%g' /var/run/docker.sock`) |
| `DOCKER_URL` | Base URL for container web links (e.g. `http://192.168.1.100`) |
| **Radarr / Sonarr / Lidarr** | |
| `RADARR_URL`, `RADARR_API_KEY` | Radarr instance |
| `SONARR_URL`, `SONARR_API_KEY` | Sonarr instance |
| `LIDARR_URL`, `LIDARR_API_KEY` | Lidarr instance |
| **Streaming** | |
| `JELLYFIN_URL`, `JELLYFIN_API_KEY` | Jellyfin (direct sessions API) |
| `PLEX_URL`, `PLEX_TOKEN` | Plex (direct sessions API) |
| `TAUTULLI_URL`, `TAUTULLI_API_KEY` | Tautulli (richer Plex stats) |
| **Claude AI** | |
| `CLAUDE_API_KEY` | Anthropic API key (https://console.anthropic.com/) |
| `CLAUDE_MODEL` | Model ID (default: `claude-sonnet-4-5`) |
| **Uptime Kuma** | |
| `UPTIME_KUMA_URL` | Reachability probe |
| `UPTIME_KUMA_METRICS_TOKEN` | Optional — enables per-monitor cards via `/metrics` |
| **Infrastructure** | |
| `NPM_URL`, `NPM_API_TOKEN` | Nginx Proxy Manager API for SSL cert expiry |
| `NAS_MOUNTS` | Comma-separated container-visible paths (e.g. `/mnt/nas,/mnt/backup`) |
| **Notifications** | |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram alerting |
| **Security** | |
| `DASHBOARD_REQUIRE_AUTH` | When `true`, dashboard requires JWT or `X-API-Key` (default `false`) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins when auth is on (default: same-origin) |
| `REGISTRY_AUTH_JSON` | JSON map `{"ghcr.io":{"username":"…","password":"…"}}` for private-registry update checks |
| **Dashboard** | |
| `REFRESH_INTERVAL` | Auto-refresh in seconds (default: `30`) |

> **Tip:** Use either Plex direct *or* Tautulli for streaming — not both — to avoid duplicate sessions.

### Display Config (`config/config.yml`)

Set the dashboard title, friendly container names, and custom per-container URLs:

```yaml
dashboard:
  title: "HomePulse"
  refresh_interval: 30

docker_labels:
  plex: "Plex Media Server"
  radarr: "Radarr"

docker_links:
  # Optional: override the ↗ link target per container.
  # Defaults to http://<docker host>:<first exposed port> when empty.
  plex: "https://plex.example.com"
```

Section ordering is controlled from the admin Settings panel (Appearance → Section Order) — no YAML toggle.

### Getting API Keys

| Service | Where to find it |
|---------|------------------|
| Proxmox | Datacenter > Permissions > API Tokens > Add |
| Radarr/Sonarr/Lidarr | Settings > General > API Key |
| Jellyfin | Dashboard > API Keys > Add |
| Plex | https://www.plex.tv/claim/ or Plex settings |
| Tautulli | Settings > Web Interface > API Key |

## Development

### Run locally (without Docker)

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### Run tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
```

### Project structure

```
backend/
  main.py                # FastAPI app, CORS, /api/dashboard
  config.py              # Settings from env + YAML + DB overrides
  cache.py               # 15-second TTL cache
  database.py            # SQLite setup and async helpers
  auth.py                # JWT auth, login/setup endpoints
  integrations/
    proxmox.py           # Proxmox VE (parallel node fetches)
    docker_int.py        # Docker socket (parallel stats)
    docker_updates.py    # Container update checks (registry digest, 6h cached)
    arr.py               # Radarr/Sonarr/Lidarr + Jellyfin/Plex/Tautulli
    claude_chat.py       # Anthropic Claude chat proxy (streaming SSE)
    uptime_kuma.py       # Uptime Kuma reachability + /metrics parser
    infrastructure.py    # Proxmox storage, backups, SSL certs, NAS mounts
    api_keys.py          # External API key CRUD + X-API-Key verification
    settings.py          # Admin settings (UI, services, users)
  notifications.py       # Telegram notification provider
  static/
    index.html           # SPA shell
    js/utils.js          # Shared escapeHtml/escapeAttr utilities
    js/app.js            # Dashboard logic (multi-instance rendering)
    js/auth.js           # Authentication (JWT token management)
    js/settings.js       # Settings panel logic (instance management)
    css/style.css        # Dark theme with CSS custom properties
    css/settings.css     # Settings panel styles
config/config.yml        # Display settings
data/                    # SQLite database (created at runtime)
tests/                   # pytest test suite
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (Docker HEALTHCHECK target) |
| GET | `/api/dashboard` | All sections in one concurrent request |
| GET | `/api/proxmox/status` | Proxmox nodes, VMs, LXC |
| GET | `/api/docker/containers` | Docker containers with stats |
| GET | `/api/arr/radarr` | Movie library + queue |
| GET | `/api/arr/sonarr` | TV library + queue |
| GET | `/api/arr/lidarr` | Music library + queue |
| GET | `/api/arr/streaming` | Active streams |
| GET | `/api/uptime-kuma/status` | Uptime Kuma reachability + monitors |
| GET | `/api/infrastructure/status` | Storage / backups / SSL / NAS |
| GET | `/api/claude/status` | Claude chat configured? |
| POST | `/api/claude/chat` | Chat (JSON response) |
| POST | `/api/claude/chat/stream` | Chat (SSE streaming) |
| POST | `/api/notifications/test` | Send a Telegram test alert |
| GET | `/api/auth/status` | Check if setup is needed |
| POST | `/api/auth/setup` | Create first admin account |
| POST | `/api/auth/login` | Login and get JWT |
| GET | `/api/auth/me` | Current user info |
| GET | `/api/settings/ui` | Get UI settings (public) |
| PUT | `/api/settings/ui` | Update UI settings (admin) |
| GET | `/api/settings/services` | Get service configs (admin) |
| PUT | `/api/settings/services` | Update service configs (admin) |
| GET | `/api/settings/instances` | List service instances (admin) |
| POST | `/api/settings/instances` | Create service instance (admin) |
| PUT | `/api/settings/instances/{id}` | Update service instance (admin) |
| DELETE | `/api/settings/instances/{id}` | Delete service instance (admin) |
| POST | `/api/settings/instances/{id}/test` | Test instance connectivity (admin) |
| GET | `/api/settings/users` | List users (admin) |
| POST | `/api/settings/users` | Create user (admin) |
| GET | `/api/settings/api-keys` | List API keys (admin) |
| POST | `/api/settings/api-keys` | Create API key — plaintext shown once (admin) |
| DELETE | `/api/settings/api-keys/{id}` | Revoke API key (admin) |

## Docker Notes

- **Healthcheck** built into both Dockerfile and Compose
- **Log rotation**: 3 x 10MB max to prevent disk bloat
- **Memory limit**: 512MB (configurable in `docker-compose.yml`)
- **Docker socket**: Mounted read-only for container monitoring. The container runs as a non-root user, so you **must** set `DOCKER_GID` in `.env` to the host Docker group ID (run `stat -c '%g' /var/run/docker.sock` to find it). Without this, the dashboard will show "Docker socket mounted but not accessible".
- **Port**: Host 8450 -> Container 8000

## Versioning

HomePulse uses [Semantic Versioning](https://semver.org/). The current version is in the `VERSION` file.

- `2.1.0` — Bookmarks widget, self-monitoring widget, PWA manifest, multi-arch GHCR image, GitHub Actions CI, multi-stage Dockerfile, shared error-return envelope, central cache TTL policy, CORS hardening + Path(ge=1), private-registry auth, NAS mounts
- `2.0.0` — Claude chat (replaces OpenClaw), Uptime Kuma + Infrastructure widgets, Telegram notifications, login rate limiting, settings hot-reload, light-theme toggle, container update badges + registry-digest backend, live preview, external API keys, DASHBOARD_REQUIRE_AUTH gate
- `1.2.4` — Cache-busting static assets, version display in header
- `1.2.3` — Login form dismisses on successful auth
- `1.2.2` — Defensive frontend rendering, distinguish render errors from API failures
- `1.2.1` — Fix Docker socket permission detection, add DOCKER_GID config
- `1.2.0` — Multi-instance Proxmox/Docker, UI improvements, download queue filtering
- `1.1.2` — Performance optimizations, mobile UX, code cleanup
- `1.1.1` — Security hardening, input validation, XSS fixes
- `1.1.0` — Account system, admin settings panel, UI customization
- `1.0.0` — First stable public release

## License

MIT
