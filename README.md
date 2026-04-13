# HomePulse

A self-hosted monitoring dashboard for your homelab. See your entire infrastructure at a glance — Proxmox nodes, Docker containers, media libraries, active streams, and an AI chat assistant — all in one dark-themed, mobile-friendly page.

![Python 3.12](https://img.shields.io/badge/python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green) ![License: MIT](https://img.shields.io/badge/license-MIT-purple)

## Changelog

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

- **Proxmox VE** — Nodes, VMs, and LXC containers with live CPU/RAM bars and uptime
- **Docker** — Every container with status, resource usage, ports, and friendly display names
- **Media Library** — Radarr (movies), Sonarr (TV), Lidarr (music) showing downloaded, requested, and missing counts plus download queue progress
- **Active Streams** — Jellyfin, Plex (direct), or Tautulli — see who's watching what, transcode status, and playback progress
- **OpenClaw Chat** — Slide-out AI chat panel with streaming token display, connected to your self-hosted OpenClaw instance
- **Single-request refresh** — One API call fetches everything in parallel; 30-second auto-refresh cycle
- **Per-section retry** — If one service is down, retry just that section without reloading
- **Admin Settings** — Account system with UI customization (colors, fonts, layout) and web-based service config management
- **Mobile-ready** — Responsive grid, dark theme, iOS home screen support

## Quick Start

```bash
git clone https://github.com/Ttitivadze/HomePulse.git
cd HomePulse
cp .env.example .env     # Edit with your service URLs and API keys
docker compose up -d     # Dashboard at http://your-server:8450
```

Access from any device on your LAN: `http://<server-ip>:8450`

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
| **Radarr / Sonarr / Lidarr** | |
| `RADARR_URL`, `RADARR_API_KEY` | Radarr instance |
| `SONARR_URL`, `SONARR_API_KEY` | Sonarr instance |
| `LIDARR_URL`, `LIDARR_API_KEY` | Lidarr instance |
| **Streaming** | |
| `JELLYFIN_URL`, `JELLYFIN_API_KEY` | Jellyfin (direct sessions API) |
| `PLEX_URL`, `PLEX_TOKEN` | Plex (direct sessions API) |
| `TAUTULLI_URL`, `TAUTULLI_API_KEY` | Tautulli (richer Plex stats) |
| **Chat** | |
| `OPENCLAW_URL`, `OPENCLAW_API_KEY` | OpenClaw instance |
| `OPENCLAW_MODEL` | Model to use (default: `default`) |
| **Dashboard** | |
| `REFRESH_INTERVAL` | Auto-refresh in seconds (default: `30`) |

> **Tip:** Use either Plex direct *or* Tautulli for streaming — not both — to avoid duplicate sessions.

### Display Config (`config/config.yml`)

Toggle dashboard sections and set friendly Docker container names:

```yaml
dashboard:
  title: "HomePulse"
  refresh_interval: 30

sections:
  proxmox: true
  docker: true
  arr_suite: true
  openclaw_chat: true

docker_labels:
  plex: "Plex Media Server"
  radarr: "Radarr"
```

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
    arr.py               # Radarr/Sonarr/Lidarr + Jellyfin/Plex/Tautulli
    openclaw.py          # Chat proxy (streaming + non-streaming)
    settings.py          # Admin settings (UI, services, users)
  static/
    index.html           # SPA shell
    js/app.js            # Dashboard logic
    js/auth.js           # Authentication (JWT token management)
    js/settings.js       # Settings panel logic
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
| GET | `/api/openclaw/status` | OpenClaw online/offline |
| POST | `/api/openclaw/chat` | Chat (JSON response) |
| POST | `/api/openclaw/chat/stream` | Chat (SSE streaming) |
| GET | `/api/auth/status` | Check if setup is needed |
| POST | `/api/auth/setup` | Create first admin account |
| POST | `/api/auth/login` | Login and get JWT |
| GET | `/api/auth/me` | Current user info |
| GET | `/api/settings/ui` | Get UI settings (public) |
| PUT | `/api/settings/ui` | Update UI settings (admin) |
| GET | `/api/settings/services` | Get service configs (admin) |
| PUT | `/api/settings/services` | Update service configs (admin) |
| GET | `/api/settings/users` | List users (admin) |
| POST | `/api/settings/users` | Create user (admin) |

## Docker Notes

- **Healthcheck** built into both Dockerfile and Compose
- **Log rotation**: 3 x 10MB max to prevent disk bloat
- **Memory limit**: 512MB (configurable in `docker-compose.yml`)
- **Docker socket**: Mounted read-only for container monitoring
- **Port**: Host 8450 -> Container 8000

## Versioning

HomePulse uses [Semantic Versioning](https://semver.org/). The current version is in the `VERSION` file.

- `1.1.2` — Performance optimizations, mobile UX, code cleanup
- `1.1.1` — Security hardening, input validation, XSS fixes
- `1.1.0` — Account system, admin settings panel, UI customization
- `1.0.0` — First stable public release

## License

MIT
