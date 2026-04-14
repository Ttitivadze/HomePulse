"""Tests for the HomePulse self-monitoring integration."""

import pytest

from backend import cache
from backend.integrations import self_stats


@pytest.mark.asyncio
async def test_self_stats_returns_ok_on_linux(async_client):
    """The CI runners are Linux — /proc/meminfo and friends exist. The
    integration should return configured=True with positive numbers.

    On non-Linux platforms this will skip via the configured-false branch
    and the assertion just checks it doesn't crash.
    """
    cache.clear()
    data = await self_stats.fetch_self_stats_data()
    assert "configured" in data
    assert "error" in data
    if not data["configured"]:
        # Non-Linux runner — nothing else to assert
        return
    assert data["mem_total"] is None or data["mem_total"] > 0
    assert data["cpu_count"] is not None and data["cpu_count"] >= 1
    # sampled_at should be a recent unix time
    assert data["sampled_at"] > 0


@pytest.mark.asyncio
async def test_self_stats_endpoint(async_client):
    resp = await async_client.get("/api/self-stats/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data


def test_meminfo_parser_with_fixture(tmp_path, monkeypatch):
    """Parser should cope with realistic /proc/meminfo content."""
    sample = (
        "MemTotal:       16384000 kB\n"
        "MemFree:         1024000 kB\n"
        "MemAvailable:    4096000 kB\n"
        "Buffers:          204800 kB\n"
        "Cached:          2048000 kB\n"
    )
    fake = tmp_path / "meminfo"
    fake.write_text(sample)

    monkeypatch.setattr(self_stats, "_PROC", tmp_path)

    result = self_stats._read_meminfo()
    assert result is not None
    assert result["MemTotal"] == 16384000 * 1024
    assert result["MemAvailable"] == 4096000 * 1024


def test_meminfo_parser_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(self_stats, "_PROC", tmp_path)
    assert self_stats._read_meminfo() is None
