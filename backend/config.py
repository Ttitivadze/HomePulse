import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("homepulse.config")


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

        # Proxmox
        self.PROXMOX_HOST: str = os.getenv("PROXMOX_HOST", "").rstrip("/")
        self.PROXMOX_USER: str = os.getenv("PROXMOX_USER", "root@pam")
        self.PROXMOX_TOKEN_NAME: str = os.getenv("PROXMOX_TOKEN_NAME", "")
        self.PROXMOX_TOKEN_VALUE: str = os.getenv("PROXMOX_TOKEN_VALUE", "")
        self.PROXMOX_VERIFY_SSL: bool = (
            os.getenv("PROXMOX_VERIFY_SSL", "false").lower() == "true"
        )

        # Radarr
        self.RADARR_URL: str = os.getenv("RADARR_URL", "").rstrip("/")
        self.RADARR_API_KEY: str = os.getenv("RADARR_API_KEY", "")

        # Sonarr
        self.SONARR_URL: str = os.getenv("SONARR_URL", "").rstrip("/")
        self.SONARR_API_KEY: str = os.getenv("SONARR_API_KEY", "")

        # Lidarr
        self.LIDARR_URL: str = os.getenv("LIDARR_URL", "").rstrip("/")
        self.LIDARR_API_KEY: str = os.getenv("LIDARR_API_KEY", "")

        # Jellyfin (direct streaming sessions)
        self.JELLYFIN_URL: str = os.getenv("JELLYFIN_URL", "").rstrip("/")
        self.JELLYFIN_API_KEY: str = os.getenv("JELLYFIN_API_KEY", "")

        # Plex (direct streaming sessions)
        self.PLEX_URL: str = os.getenv("PLEX_URL", "").rstrip("/")
        self.PLEX_TOKEN: str = os.getenv("PLEX_TOKEN", "")

        # Tautulli (Plex monitoring wrapper — alternative to direct Plex)
        self.TAUTULLI_URL: str = os.getenv("TAUTULLI_URL", "").rstrip("/")
        self.TAUTULLI_API_KEY: str = os.getenv("TAUTULLI_API_KEY", "")

        # OpenClaw
        self.OPENCLAW_URL: str = os.getenv("OPENCLAW_URL", "").rstrip("/")
        self.OPENCLAW_API_KEY: str = os.getenv("OPENCLAW_API_KEY", "")
        self.OPENCLAW_MODEL: str = os.getenv("OPENCLAW_MODEL", "default")

        # Dashboard
        raw_interval = os.getenv("REFRESH_INTERVAL", "30")
        self.REFRESH_INTERVAL, warn = _safe_int(raw_interval, 30, "REFRESH_INTERVAL")
        if warn:
            self.warnings.append(warn)

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
    def dashboard_title(self) -> str:
        return self.DISPLAY.get("dashboard", {}).get("title", "HomePulse")


settings = Settings()
