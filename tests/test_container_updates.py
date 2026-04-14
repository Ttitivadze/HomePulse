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


def test_registry_host_docker_hub():
    # Unprefixed and `library/` refs resolve to Docker Hub.
    assert docker_updates._registry_host("nginx:latest") == "docker.io"
    assert docker_updates._registry_host("library/nginx:latest") == "docker.io"


def test_registry_host_explicit():
    assert docker_updates._registry_host("ghcr.io/foo/bar:latest") == "ghcr.io"
    assert docker_updates._registry_host("lscr.io/linuxserver/radarr:latest") == "lscr.io"
    assert docker_updates._registry_host("localhost/foo:dev") == "localhost"
    assert docker_updates._registry_host("registry.example.com:5000/foo:dev") == "registry.example.com:5000"


def test_auth_config_lookup(monkeypatch):
    from backend.config import settings
    # No map -> no auth
    monkeypatch.setattr(settings, "REGISTRY_AUTH", {}, raising=False)
    assert docker_updates._auth_config_for("ghcr.io/foo/bar") is None

    # Host match
    monkeypatch.setattr(
        settings, "REGISTRY_AUTH",
        {"ghcr.io": {"username": "u", "password": "p"}},
        raising=False,
    )
    assert docker_updates._auth_config_for("ghcr.io/foo/bar") == {"username": "u", "password": "p"}

    # Docker Hub alias (docker.io <-> index.docker.io)
    monkeypatch.setattr(
        settings, "REGISTRY_AUTH",
        {"index.docker.io": {"username": "u", "password": "p"}},
        raising=False,
    )
    assert docker_updates._auth_config_for("nginx:latest") == {"username": "u", "password": "p"}


@pytest.mark.asyncio
async def test_auth_config_passed_to_registry_call(monkeypatch):
    """When REGISTRY_AUTH has a match, the Docker SDK call receives auth_config."""
    cache.clear()
    from backend.config import settings
    monkeypatch.setattr(
        settings, "REGISTRY_AUTH",
        {"ghcr.io": {"username": "u", "password": "p"}},
        raising=False,
    )

    captured = {}

    class _SpyImages:
        def get_registry_data(self, image_ref, **kwargs):
            captured["image_ref"] = image_ref
            captured["kwargs"] = kwargs
            return _FakeRegistryData("sha256:same")

    class _SpyClient:
        images = _SpyImages()

    infos = [{"image": "ghcr.io/foo/bar:latest"}]
    containers = [_FakeContainer("sha256:same")]
    await docker_updates.annotate_update_available(_SpyClient(), containers, infos)

    assert captured["kwargs"].get("auth_config") == {"username": "u", "password": "p"}
    assert infos[0]["update_available"] is False
