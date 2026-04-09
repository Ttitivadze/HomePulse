# HomeLab Dashboard

A Docker-hosted homepage for your homelab that monitors Proxmox VMs, Docker containers, media library (*arr suite), streaming activity, and includes an integrated OpenClaw AI chat assistant.

![Dark Theme Dashboard](https://img.shields.io/badge/theme-dark-1e2130) ![Python](https://img.shields.io/badge/python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)

## Features

- **Proxmox VE Monitoring** — View all nodes, VMs, and LXC containers with CPU/RAM usage and uptime
- **Docker Container Status** — Live container list with resource usage, ports, and status
- **Media Library Stats** — Radarr (movies), Sonarr (TV shows), and Lidarr (music) integration showing downloaded counts, missing items, and download queue progress
- **Active Streaming** — Tautulli/Plex integration showing who's watching what, with quality and transcode info
- **OpenClaw Chat** — Embedded AI chat panel to interact with your self-hosted OpenClaw instance while monitoring your homelab

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url> homelab-dashboard
cd homelab-dashboard
cp .env.example .env
```

Edit `.env` with your service URLs and API keys.

### 2. Deploy with Docker Compose

```bash
docker compose up -d
```

The dashboard will be available at `http://your-host:8450`.

## Configuration

### Environment Variables (`.env`)

| Variable | Description | Required |
|---|---|---|
| `PROXMOX_HOST` | Proxmox VE URL (e.g., `https://192.168.1.100:8006`) | For Proxmox |
| `PROXMOX_USER` | API user (e.g., `root@pam`) | For Proxmox |
| `PROXMOX_TOKEN_NAME` | API token name | For Proxmox |
| `PROXMOX_TOKEN_VALUE` | API token value | For Proxmox |
| `PROXMOX_VERIFY_SSL` | Verify SSL certificate (`true`/`false`) | No |
| `RADARR_URL` | Radarr URL | For Radarr |
| `RADARR_API_KEY` | Radarr API key (Settings > General) | For Radarr |
| `SONARR_URL` | Sonarr URL | For Sonarr |
| `SONARR_API_KEY` | Sonarr API key | For Sonarr |
| `LIDARR_URL` | Lidarr URL | For Lidarr |
| `LIDARR_API_KEY` | Lidarr API key | For Lidarr |
| `TAUTULLI_URL` | Tautulli URL | For Streaming |
| `TAUTULLI_API_KEY` | Tautulli API key | For Streaming |
| `OPENCLAW_URL` | OpenClaw instance URL | For Chat |
| `OPENCLAW_API_KEY` | OpenClaw API key | For Chat |
| `OPENCLAW_MODEL` | Model to use (default: `default`) | No |
| `REFRESH_INTERVAL` | Auto-refresh interval in seconds (default: `30`) | No |

### Getting API Keys

- **Proxmox**: Datacenter > Permissions > API Tokens > Add
- **Radarr/Sonarr/Lidarr**: Settings > General > API Key
- **Tautulli**: Settings > Web Interface > API Key
- **OpenClaw**: Your OpenClaw instance settings

## Architecture

```
homelab-dashboard/
├── docker-compose.yml       # Container deployment
├── Dockerfile               # Python 3.12 slim image
├── requirements.txt         # Python dependencies
├── .env.example             # Configuration template
├── config/
│   └── config.yml           # Display settings
└── backend/
    ├── main.py              # FastAPI app entry point
    ├── config.py            # Settings from env vars
    ├── integrations/
    │   ├── proxmox.py       # Proxmox VE API client
    │   ├── docker_int.py    # Docker socket integration
    │   ├── arr.py           # Radarr/Sonarr/Lidarr/Tautulli
    │   └── openclaw.py      # OpenClaw chat proxy
    └── static/
        ├── index.html       # Dashboard SPA
        ├── css/style.css    # Dark theme styles
        └── js/app.js        # Frontend application
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Dashboard UI |
| `GET /api/health` | Health check |
| `GET /api/proxmox/status` | Proxmox nodes, VMs, containers |
| `GET /api/docker/containers` | Docker container list with stats |
| `GET /api/arr/radarr` | Radarr movie stats and queue |
| `GET /api/arr/sonarr` | Sonarr TV show stats and queue |
| `GET /api/arr/lidarr` | Lidarr music stats and queue |
| `GET /api/arr/streaming` | Active Plex/Tautulli streams |
| `GET /api/openclaw/status` | OpenClaw connection status |
| `POST /api/openclaw/chat` | Send chat message to OpenClaw |
| `POST /api/openclaw/chat/stream` | Streaming chat response |

## License

MIT
