"""Tests for the service instances CRUD endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_instances_empty(admin_token, async_client):
    resp = await async_client.get(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_proxmox_instance(admin_token, async_client):
    resp = await async_client.post(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "service_type": "proxmox",
            "instance_name": "Office PVE",
            "config": {"host": "https://192.168.2.100:8006", "user": "root@pam", "token_name": "dash", "token_value": "secret"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_type"] == "proxmox"
    assert data["instance_name"] == "Office PVE"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_docker_instance(admin_token, async_client):
    resp = await async_client.post(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "service_type": "docker",
            "instance_name": "Remote Docker",
            "config": {"host": "tcp://192.168.2.200:2375", "url": "http://192.168.2.200"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_type"] == "docker"
    assert data["instance_name"] == "Remote Docker"


@pytest.mark.asyncio
async def test_create_instance_invalid_type(admin_token, async_client):
    resp = await async_client.post(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "service_type": "radarr",
            "instance_name": "Test",
            "config": {"host": "http://example.com"},
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_instance_missing_host(admin_token, async_client):
    resp = await async_client.post(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "service_type": "proxmox",
            "instance_name": "No Host",
            "config": {"user": "root@pam"},
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_instance(admin_token, async_client):
    # Create
    create_resp = await async_client.post(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "service_type": "proxmox",
            "instance_name": "Original",
            "config": {"host": "https://10.0.0.1:8006"},
        },
    )
    instance_id = create_resp.json()["id"]

    # Update
    resp = await async_client.put(
        f"/api/settings/instances/{instance_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"instance_name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"


@pytest.mark.asyncio
async def test_delete_instance(admin_token, async_client):
    # Create
    create_resp = await async_client.post(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "service_type": "docker",
            "instance_name": "To Delete",
            "config": {"host": "tcp://10.0.0.2:2375"},
        },
    )
    instance_id = create_resp.json()["id"]

    # Delete
    resp = await async_client.delete(
        f"/api/settings/instances/{instance_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_nonexistent_instance(admin_token, async_client):
    resp = await async_client.delete(
        "/api/settings/instances/99999",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_instances_shows_created(admin_token, async_client):
    # Create two instances
    await async_client.post(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"service_type": "proxmox", "instance_name": "PVE 1", "config": {"host": "https://10.0.0.1:8006"}},
    )
    await async_client.post(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"service_type": "docker", "instance_name": "Docker 2", "config": {"host": "tcp://10.0.0.2:2375"}},
    )

    resp = await async_client.get(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    instances = resp.json()
    assert len(instances) == 2
    names = {i["instance_name"] for i in instances}
    assert "PVE 1" in names
    assert "Docker 2" in names


@pytest.mark.asyncio
async def test_instance_secrets_masked(admin_token, async_client):
    await async_client.post(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "service_type": "proxmox",
            "instance_name": "Secret Test",
            "config": {"host": "https://10.0.0.1:8006", "token_value": "my-secret-token"},
        },
    )

    resp = await async_client.get(
        "/api/settings/instances",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    instances = resp.json()
    assert len(instances) == 1
    assert instances[0]["config"]["token_value"] == "••••••••"


@pytest.mark.asyncio
async def test_instances_require_admin(init_db, async_client):
    resp = await async_client.get("/api/settings/instances")
    assert resp.status_code in (401, 403)
