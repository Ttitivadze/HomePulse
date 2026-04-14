import logging
import os
import sqlite3
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("homepulse.config")


def _load_db_overrides() -> dict[str, str]:
    """Load service config overrides from SQLite (if the DB exists)."""
    for candidate in [Path("data/homepulse.db"), Path("/app/data/homepulse.db")]:
        if candidate.is_file():
            try:
                conn = sqlite3.connect(str(candidate))
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT key, value FROM service_config").fetchall()
                conn.close()
                return {r["key"]: r["value"] for r in rows}
            except Exception as e:
                logger.warning("Failed to load DB overrides from %s: %s", candidate, e)
    return {}


def _safe_int(value: str, default: int, name: str) -> tuple[int, str | None]:
    """Parse an int from a string, returning (value, warning) on failure."""
    try:
        n = int(value)
        if n < 1:
            return default, f"{name}={n} is invalid (must be >= 1), using default {default}"
        return n, None
    except (ValueError, TypeError):
        return default, f"{name}={value!r} is not a valid integer, using default {default}"


class Settings:
    def __init__(self):
        self.warnings: list[str] = []

        # Load DB overrides (web UI settings take precedence over .env)
        db_overrides = _load_db_overrides()

        def _get(key: str, default: str = "") -> str:
            """DB override > env var > default."""
            return db_overrides.get(key, os.getenv(key, default))

        # Proxmox
        self.PROXMOX_HOST: str = _get("PROXMOX_HOST").rstrip("/")
        self.PROXMOX_USER: str = _get("PROXMOX_USER", "root@pam")
        self.PROXMOX_TOKEN_NAME: str = _get("PROXMOX_TOKEN_NAME")
        self.PROXMOX_TOKEN_VALUE: str = _get("PROXMOX_TOKEN_VALUE")
        self.PROXMOX_VERIFY_SSL: bool = (
            _get("PROXMOX_VERIFY_SSL", "false").lower() == "true"
        )

        # Docker
        self.DOCKER_URL: str = _get("DOCKER_URL").rstrip("/")

        # Radarr
        self.RADARR_URL: str = _get("RADARR_URL").rstrip("/")
        self.RADARR_API_KEY: str = _get("RADARR_API_KEY")

        # Sonarr
        self.SONARR_URL: str = _get("SONARR_URL").rstrip("/")
        self.SONARR_API_KEY: str = _get("SONARR_API_KEY")

        # Lidarr
        self.LIDARR_URL: str = _get("LIDARR_URL").rstrip("/")
        self.LIDARR_API_KEY: str = _get("LIDARR_API_KEY")

        # Jellyfin (direct streaming sessions)
        self.JELLYFIN_URL: str = _get("JELLYFIN_URL").rstrip("/")
        self.JELLYFIN_API_KEY: str = _get("JELLYFIN_API_KEY")

        # Plex (direct streaming sessions)
        self.PLEX_URL: str = _get("PLEX_URL").rstrip("/")
        self.PLEX_TOKEN: str = _get("PLEX_TOKEN")

        # Tautulli (Plex monitoring wrapper — alternative to direct Plex)
        self.TAUTULLI_URL: str = _get("TAUTULLI_URL").rstrip("/")
        self.TAUTULLI_API_KEY: str = _get("TAUTULLI_API_KEY")

        # Claude
        self.CLAUDE_API_KEY: str = _get("CLAUDE_API_KEY")
        self.CLAUDE_MODEL: str = _get("CLAUDE_MODEL", "claude-sonnet-4-5")

        # Uptime Kuma
        self.UPTIME_KUMA_URL: str = _get("UPTIME_KUMA_URL").rstrip("/")
        # Optional: when set, enables per-monitor status via Uptime Kuma's
        # Prometheus /metrics endpoint. The token is the API key issued
        # from Uptime Kuma's Settings > API Keys page; the basic-auth
        # username can be any non-empty string.
        self.UPTIME_KUMA_METRICS_TOKEN: str = _get("UPTIME_KUMA_METRICS_TOKEN")

        # Infrastructure (NPM for SSL certs)
        self.NPM_URL: str = _get("NPM_URL").rstrip("/")
        self.NPM_API_TOKEN: str = _get("NPM_API_TOKEN")

        # NAS / external storage mounts. Comma-separated list of
        # filesystem paths visible inside the HomePulse container that
        # should be shown alongside Proxmox storages in the
        # Infrastructure widget. Each path is read via os.statvfs so
        # accuracy matches `df`. Empty by default.
        raw_nas = _get("NAS_MOUNTS", "")
        self.NAS_MOUNTS: list[str] = [p.strip() for p in raw_nas.split(",") if p.strip()]

        # Notifications
        self.TELEGRAM_BOT_TOKEN: str = _get("TELEGRAM_BOT_TOKEN")
        self.TELEGRAM_CHAT_ID: str = _get("TELEGRAM_CHAT_ID")

        # Dashboard
        raw_interval = _get("REFRESH_INTERVAL", "30")
        self.REFRESH_INTERVAL, warn = _safe_int(raw_interval, 30, "REFRESH_INTERVAL")
        if warn:
            self.warnings.append(warn)

        # When true, the dashboard and per-section read endpoints require
        # either a JWT or a valid X-API-Key header. Default false for
        # backward compatibility with pre-2.0 behaviour (dashboard public).
        self.DASHBOARD_REQUIRE_AUTH: bool = (
            _get("DASHBOARD_REQUIRE_AUTH", "false").lower() == "true"
        )

        # Registry authentication for container update checks.
        # REGISTRY_AUTH_JSON is expected to be a JSON object of the form:
        #   {"ghcr.io": {"username": "...", "password": "..."},
        #    "docker.io": {"username": "...", "password": "..."}}
        # Empty by default — public images work with no auth.
        self.REGISTRY_AUTH: dict = {}
        raw_registry_auth = _get("REGISTRY_AUTH_JSON", "")
        if raw_registry_auth:
            try:
                import json
                parsed = json.loads(raw_registry_auth)
                if isinstance(parsed, dict):
                    self.REGISTRY_AUTH = parsed
                else:
                    self.warnings.append(
                        "REGISTRY_AUTH_JSON must be a JSON object; ignoring"
                    )
            except Exception as e:
                self.warnings.append(f"Failed to parse REGISTRY_AUTH_JSON: {e}")

        # Display config from YAML (section toggles, labels)
        self.DISPLAY: dict = {}
        self._load_display_config()

        # Validate common mistakes
        self._validate()

    def _load_display_config(self):
        """Load optional config/config.yml for display settings."""
        for candidate in [
            Path("config/config.yml"),
            Path("/app/config/config.yml"),
        ]:
            if candidate.is_file():
                try:
                    self.DISPLAY = yaml.safe_load(candidate.read_text()) or {}
                    return
                except Exception as e:
                    self.warnings.append(f"Failed to parse {candidate}: {e}")

    def reload(self):
        """Reload settings from DB overrides, env vars, and YAML."""
        self.__init__()

    def _validate(self):
        """Warn about common misconfigurations at startup."""
        if self.PLEX_URL and self.TAUTULLI_URL:
            self.warnings.append(
                "Both PLEX_URL and TAUTULLI_URL are configured — "
                "you may see duplicate streaming sessions"
            )
        if self.PROXMOX_HOST and not self.PROXMOX_TOKEN_VALUE:
            self.warnings.append(
                "PROXMOX_HOST is set but PROXMOX_TOKEN_VALUE is empty — "
                "Proxmox API calls will fail"
            )

    @property
    def section_enabled(self) -> dict:
        """Which dashboard sections are enabled via config.yml."""
        return self.DISPLAY.get("sections", {})

    @property
    def docker_labels(self) -> dict:
        """Friendly names for Docker containers from config.yml."""
        return self.DISPLAY.get("docker_labels", {})

    @property
    def docker_links(self) -> dict:
        """Custom URLs for Docker containers from config.yml."""
        return self.DISPLAY.get("docker_links", {})

    @property
    def dashboard_title(self) -> str:
        return self.DISPLAY.get("dashboard", {}).get("title", "HomePulse")


settings = Settings()
