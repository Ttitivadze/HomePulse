"""Tests for infrastructure monitoring (storage, backups, SSL certs)."""

import pytest

from backend.integrations import infrastructure
from backend.config import settings


@pytest.mark.asyncio
async def test_infrastructure_unconfigured_when_all_empty(monkeypatch):
    # All three fetchers return empty lists (no Proxmox token, no NPM URL)
    monkeypatch.setattr(settings, "PROXMOX_HOST", "")
    monkeypatch.setattr(settings, "PROXMOX_TOKEN_VALUE", "")
    monkeypatch.setattr(settings, "NPM_URL", "")
    monkeypatch.setattr(settings, "NPM_API_TOKEN", "")

    data = await infrastructure.fetch_infrastructure_data()
    assert data["configured"] is False
    assert data["storage"] == []
    assert data["backups"] == []
    assert data["ssl_certs"] == []


@pytest.mark.asyncio
async def test_infrastructure_configured_when_any_section_has_data(monkeypatch):
    async def fake_storage():
        return [{"name": "local", "type": "dir", "total": 100, "used": 50, "percent": 50.0}]

    async def fake_backups():
        return []

    async def fake_ssl():
        return []

    monkeypatch.setattr(infrastructure, "_fetch_storage_data", fake_storage)
    monkeypatch.setattr(infrastructure, "_fetch_backup_data", fake_backups)
    monkeypatch.setattr(infrastructure, "_fetch_ssl_data", fake_ssl)

    data = await infrastructure.fetch_infrastructure_data()
    assert data["configured"] is True
    assert len(data["storage"]) == 1
    assert data["storage"][0]["name"] == "local"
