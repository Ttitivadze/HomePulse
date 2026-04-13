import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    def __init__(self):
        # Proxmox
        self.PROXMOX_HOST: str = os.getenv("PROXMOX_HOST", "")
        self.PROXMOX_USER: str = os.getenv("PROXMOX_USER", "root@pam")
        self.PROXMOX_TOKEN_NAME: str = os.getenv("PROXMOX_TOKEN_NAME", "")
        self.PROXMOX_TOKEN_VALUE: str = os.getenv("PROXMOX_TOKEN_VALUE", "")
        self.PROXMOX_VERIFY_SSL: bool = (
            os.getenv("PROXMOX_VERIFY_SSL", "false").lower() == "true"
        )

        # Radarr
        self.RADARR_URL: str = os.getenv("RADARR_URL", "")
        self.RADARR_API_KEY: str = os.getenv("RADARR_API_KEY", "")

        # Sonarr
        self.SONARR_URL: str = os.getenv("SONARR_URL", "")
        self.SONARR_API_KEY: str = os.getenv("SONARR_API_KEY", "")

        # Lidarr
        self.LIDARR_URL: str = os.getenv("LIDARR_URL", "")
        self.LIDARR_API_KEY: str = os.getenv("LIDARR_API_KEY", "")

        # Jellyfin (direct streaming sessions)
        self.JELLYFIN_URL: str = os.getenv("JELLYFIN_URL", "")
        self.JELLYFIN_API_KEY: str = os.getenv("JELLYFIN_API_KEY", "")

        # Plex (direct streaming sessions)
        self.PLEX_URL: str = os.getenv("PLEX_URL", "")
        self.PLEX_TOKEN: str = os.getenv("PLEX_TOKEN", "")

        # Tautulli (Plex monitoring wrapper — alternative to direct Plex)
        self.TAUTULLI_URL: str = os.getenv("TAUTULLI_URL", "")
        self.TAUTULLI_API_KEY: str = os.getenv("TAUTULLI_API_KEY", "")

        # OpenClaw
        self.OPENCLAW_URL: str = os.getenv("OPENCLAW_URL", "")
        self.OPENCLAW_API_KEY: str = os.getenv("OPENCLAW_API_KEY", "")
        self.OPENCLAW_MODEL: str = os.getenv("OPENCLAW_MODEL", "default")

        # Dashboard
        self.REFRESH_INTERVAL: int = int(os.getenv("REFRESH_INTERVAL", "30"))


settings = Settings()
