import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Proxmox
    PROXMOX_HOST: str = os.getenv("PROXMOX_HOST", "")
    PROXMOX_USER: str = os.getenv("PROXMOX_USER", "root@pam")
    PROXMOX_TOKEN_NAME: str = os.getenv("PROXMOX_TOKEN_NAME", "")
    PROXMOX_TOKEN_VALUE: str = os.getenv("PROXMOX_TOKEN_VALUE", "")
    PROXMOX_VERIFY_SSL: bool = os.getenv("PROXMOX_VERIFY_SSL", "false").lower() == "true"

    # Radarr
    RADARR_URL: str = os.getenv("RADARR_URL", "")
    RADARR_API_KEY: str = os.getenv("RADARR_API_KEY", "")

    # Sonarr
    SONARR_URL: str = os.getenv("SONARR_URL", "")
    SONARR_API_KEY: str = os.getenv("SONARR_API_KEY", "")

    # Lidarr
    LIDARR_URL: str = os.getenv("LIDARR_URL", "")
    LIDARR_API_KEY: str = os.getenv("LIDARR_API_KEY", "")

    # Tautulli
    TAUTULLI_URL: str = os.getenv("TAUTULLI_URL", "")
    TAUTULLI_API_KEY: str = os.getenv("TAUTULLI_API_KEY", "")

    # OpenClaw
    OPENCLAW_URL: str = os.getenv("OPENCLAW_URL", "")
    OPENCLAW_API_KEY: str = os.getenv("OPENCLAW_API_KEY", "")
    OPENCLAW_MODEL: str = os.getenv("OPENCLAW_MODEL", "default")

    # Dashboard
    REFRESH_INTERVAL: int = int(os.getenv("REFRESH_INTERVAL", "30"))


settings = Settings()
