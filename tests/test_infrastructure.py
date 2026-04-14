"""Tests for infrastructure monitoring (storage, backups, SSL certs, NAS mounts)."""

import pytest

from backend import cache
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


def test_statvfs_usage_nonexistent_path():
    assert infrastructure._statvfs_usage("/path/that/does/not/exist") is None


def test_statvfs_usage_real_path(tmp_path):
    """Reads a real directory and returns positive usage numbers."""
    usage = infrastructure._statvfs_usage(str(tmp_path))
    assert usage is not None
    assert usage["path"] == str(tmp_path)
    assert usage["total"] > 0
    assert 0 <= usage["percent"] <= 100
    assert usage["type"] == "mount"


@pytest.mark.asyncio
async def test_fetch_nas_mounts_empty(monkeypatch):
    monkeypatch.setattr(settings, "NAS_MOUNTS", [])
    result = await infrastructure._fetch_nas_mounts()
    assert result == []


@pytest.mark.asyncio
async def test_fetch_nas_mounts_collects_real(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "NAS_MOUNTS", [str(tmp_path)])
    result = await infrastructure._fetch_nas_mounts()
    assert len(result) == 1
    assert result[0]["path"] == str(tmp_path)


@pytest.mark.asyncio
async def test_fetch_nas_mounts_skips_invalid(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings, "NAS_MOUNTS",
        [str(tmp_path), "/definitely/not/a/mount"],
    )
    result = await infrastructure._fetch_nas_mounts()
    # Only the valid path should appear.
    assert len(result) == 1
    assert result[0]["path"] == str(tmp_path)


@pytest.mark.asyncio
async def test_nas_mounts_merged_into_storage(tmp_path, monkeypatch):
    """fetch_infrastructure_data merges NAS mounts with Proxmox storage,
    with NAS mounts listed first."""
    cache.clear()
    monkeypatch.setattr(settings, "NAS_MOUNTS", [str(tmp_path)])

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
    assert len(data["storage"]) == 2
    # NAS mount appears first
    assert data["storage"][0]["type"] == "mount"
    assert data["storage"][1]["name"] == "local"
