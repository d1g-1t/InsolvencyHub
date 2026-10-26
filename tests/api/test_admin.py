import httpx

from tests.api.conftest import Login
from tests.api.helpers import observation_case


async def test_outbox_and_rebuild(client: httpx.AsyncClient, manager: dict[str, str], login: Login) -> None:
    await observation_case(client, manager)
    admin = await login("admin@a.test")
    outbox = (await client.get("/api/v1/admin/outbox", headers=admin)).json()
    assert outbox["pending"] == 3
    assert outbox["failing"] == 0
    assert outbox["lag_seconds"] >= 0
    rebuilt = (await client.post("/api/v1/admin/projections/rebuild", headers=admin)).json()
    assert rebuilt == {"cases": 1}
    assert len((await client.get("/api/v1/cases", headers=admin)).json()) == 1
