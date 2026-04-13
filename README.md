# HomePulse

A self-hosted monitoring dashboard for your homelab. See your entire infrastructure at a glance — Proxmox nodes, Docker containers, media libraries, active streams, and an AI chat assistant — all in one dark-themed, mobile-friendly page.

![Python 3.12](https://img.shields.io/badge/python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green) ![License: MIT](https://img.shields.io/badge/license-MIT-purple)

## Features

- **Proxmox VE** — Nodes, VMs, and LXC containers with live CPU/RAM bars and uptime
- **Docker** — Every container with status, resource usage, ports, and friendly display names
- **Media Library** — Radarr (movies), Sonarr (TV), Lidarr (music) showing downloaded, requested, and missing counts plus download queue progress
- **Active Streams** — Jellyfin, Plex (direct), or Tautulli — see who's watching what, transcode status, and playback progress
- **OpenClaw Chat** — Slide-out AI chat panel with streaming token display, connected to your self-hosted OpenClaw instance
- **Single-request refresh** — One API call fetches everything in parallel; 30-second auto-refresh cycle
- **Per-section retry** — If one service is down, retry just that section without reloading
- **Mobile-ready** — Responsive grid, dark theme, iOS home screen support

## Quick Start

```bash
git clone https://github.com/Ttitivadze/ClaudeCode.git homepulse
cd homepulse
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
|---------|-----------------|
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
  config.py              # Settings from env + YAML
  cache.py               # 15-second TTL cache
  integrations/
    proxmox.py           # Proxmox VE (parallel node fetches)
    docker_int.py        # Docker socket (parallel stats)
    arr.py               # Radarr/Sonarr/Lidarr + Jellyfin/Plex/Tautulli
    openclaw.py          # Chat proxy (streaming + non-streaming)
  static/
    index.html           # SPA shell
    js/app.js            # Frontend logic
    css/style.css        # Dark theme
config/config.yml        # Display settings
tests/                   # 24 pytest tests
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

## Docker Notes

- **Healthcheck** built into both Dockerfile and Compose
- **Log rotation**: 3 x 10MB max to prevent disk bloat
- **Memory limit**: 512MB (configurable in `docker-compose.yml`)
- **Docker socket**: Mounted read-only for container monitoring
- **Port**: Host 8450 -> Container 8000

## Versioning

HomePulse uses [Semantic Versioning](https://semver.org/). The current version is in the `VERSION` file.

- `0.x.y` — Pre-release development
- `1.0.0` — First stable public release

## License

MIT
