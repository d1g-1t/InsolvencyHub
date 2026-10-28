from typing import Any

import httpx

from tests.api.conftest import Login


async def test_health(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health")).json()["status"] == "ok"
    ready = (await client.get("/health/ready")).json()
    assert ready == {"status": "ok", "checks": {"postgres": "ok", "redis": "ok"}}


async def test_readiness_reports_broken_dependencies(client: httpx.AsyncClient) -> None:
    app: Any = client._transport.app
    healthy_sessions, healthy_redis = app.state.sessions, app.state.redis

    def broken() -> None:
        raise ConnectionError("down")

    class BrokenRedis:
        async def ping(self) -> None:
            raise ConnectionError("down")

    app.state.sessions, app.state.redis = broken, BrokenRedis()
    response = await client.get("/health/ready")
    app.state.sessions, app.state.redis = healthy_sessions, healthy_redis
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


async def test_login_and_me(client: httpx.AsyncClient, login: Login) -> None:
    headers = await login("Manager@A.test".lower())
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["role"] == "manager"


async def test_login_failures(client: httpx.AsyncClient) -> None:
    wrong = await client.post("/api/v1/auth/login", json={"email": "manager@a.test", "password": "nope"})
    assert wrong.status_code == 401
    unknown = await client.post("/api/v1/auth/login", json={"email": "ghost@a.test", "password": "x"})
    assert unknown.status_code == 401
    disabled = await client.post("/api/v1/auth/login", json={"email": "disabled@a.test", "password": "test-password"})
    assert disabled.status_code == 401


async def test_missing_and_invalid_tokens(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/cases")).status_code == 401
    bad = await client.get("/api/v1/cases", headers={"Authorization": "Bearer v4.local.garbage"})
    assert bad.status_code == 401


async def test_role_permissions(client: httpx.AsyncClient, login: Login) -> None:
    auditor = await login("auditor@a.test")
    creditor = await login("creditor@a.test")
    assert (await client.get("/api/v1/cases", headers=auditor)).status_code == 200
    assert (await client.post("/api/v1/cases", headers=auditor, json={})).status_code == 403
    assert (await client.get("/api/v1/admin/outbox", headers=creditor)).status_code == 403
