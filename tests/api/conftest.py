from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import pytest

from tests.conftest import PASSWORD

Login = Callable[[str], Awaitable[dict[str, str]]]


@pytest.fixture
async def client(sessions: Any, redis_client: Any) -> AsyncIterator[httpx.AsyncClient]:
    from insolvency_hub.api.app import create_app

    app = create_app()
    app.state.sessions = sessions
    app.state.redis = redis_client
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
def login(client: httpx.AsyncClient) -> Login:
    async def do(email: str) -> dict[str, str]:
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return do


@pytest.fixture
async def manager(login: Login) -> dict[str, str]:
    return await login("manager@a.test")
