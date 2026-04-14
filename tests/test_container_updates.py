"""Tests for docker container update-checking."""

import pytest

from backend import cache
from backend.integrations import docker_updates


class _FakeImage:
    def __init__(self, digest: str | None):
        if digest is None:
            self.attrs = {"RepoDigests": []}
        else:
            self.attrs = {"RepoDigests": [f"nginx@{digest}"]}


class _FakeContainer:
    def __init__(self, digest: str | None):
        self.image = _FakeImage(digest)


class _FakeRegistryData:
    def __init__(self, digest: str):
        self.id = digest
        self.attrs = {}


class _FakeClient:
    def __init__(self, remote_digest: str | None, raises: bool = False):
        self._remote = remote_digest
        self._raises = raises
        self.images = self

    def get_registry_data(self, image_ref):
        if self._raises:
            raise RuntimeError("registry unreachable")
        if self._remote is None:
            raise RuntimeError("unknown image")
        return _FakeRegistryData(self._remote)


@pytest.mark.asyncio
async def test_update_available_when_digests_differ():
    cache.clear()
    client = _FakeClient(remote_digest="sha256:new")
    containers = [_FakeContainer("sha256:old")]
    infos = [{"image": "nginx:latest"}]
    await docker_updates.annotate_update_available(client, containers, infos)
    assert infos[0]["update_available"] is True


@pytest.mark.asyncio
async def test_no_update_when_digests_match():
    cache.clear()
    client = _FakeClient(remote_digest="sha256:same")
    containers = [_FakeContainer("sha256:same")]
    infos = [{"image": "nginx:latest"}]
    await docker_updates.annotate_update_available(client, containers, infos)
    assert infos[0]["update_available"] is False


@pytest.mark.asyncio
async def test_unknown_when_registry_errors():
    cache.clear()
    client = _FakeClient(remote_digest=None, raises=True)
    containers = [_FakeContainer("sha256:old")]
    infos = [{"image": "nginx:latest"}]
    await docker_updates.annotate_update_available(client, containers, infos)
    assert infos[0]["update_available"] is None


@pytest.mark.asyncio
async def test_cache_avoids_refetch():
    cache.clear()
    client = _FakeClient(remote_digest="sha256:new")
    containers = [_FakeContainer("sha256:old")]
    infos = [{"image": "nginx:latest"}]
    await docker_updates.annotate_update_available(client, containers, infos)
    assert infos[0]["update_available"] is True

    # Now swap in a client that would raise — cached result should apply.
    failing_client = _FakeClient(remote_digest=None, raises=True)
    infos2 = [{"image": "nginx:latest"}]
    await docker_updates.annotate_update_available(failing_client, [_FakeContainer("sha256:old")], infos2)
    assert infos2[0]["update_available"] is True


@pytest.mark.asyncio
async def test_rate_limit_caps_uncached_checks(monkeypatch):
    cache.clear()
    monkeypatch.setattr(docker_updates, "MAX_CHECKS_PER_CYCLE", 2)

    client = _FakeClient(remote_digest="sha256:new")
    # 4 distinct images — only 2 should be looked up this cycle.
    infos = [
        {"image": "nginx:latest"},
        {"image": "redis:latest"},
        {"image": "postgres:latest"},
        {"image": "mariadb:latest"},
    ]
    containers = [_FakeContainer("sha256:old") for _ in infos]
    await docker_updates.annotate_update_available(client, containers, infos)

    checked = [i for i in infos if i["update_available"] is True]
    skipped = [i for i in infos if i["update_available"] is None]
    assert len(checked) == 2
    assert len(skipped) == 2


@pytest.mark.asyncio
async def test_digest_pinned_images_skipped():
    cache.clear()
    client = _FakeClient(remote_digest="sha256:new")
    infos = [{"image": "nginx@sha256:pinned"}]
    containers = [_FakeContainer("sha256:pinned")]
    await docker_updates.annotate_update_available(client, containers, infos)
    assert infos[0]["update_available"] is None
