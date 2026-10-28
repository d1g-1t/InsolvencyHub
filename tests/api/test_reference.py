import httpx


async def test_norms_catalog(client: httpx.AsyncClient) -> None:
    norms = (await client.get("/api/v1/reference/norms")).json()
    assert norms["checked_on"] == "2026-10-16"
    assert any(n["code"] == "127-FZ:71.1" for n in norms["norms"])
    one = (await client.get("/api/v1/reference/norms/127-FZ:138.1")).json()
    assert "семьдесят процентов" in one["quote"]
    assert (await client.get("/api/v1/reference/norms/nope")).status_code == 404


async def test_procedures(client: httpx.AsyncClient) -> None:
    data = (await client.get("/api/v1/reference/procedures/citizen")).json()
    assert {"from": "restructuring", "to": "property_realization", "basis": "ст. 213.24 127-ФЗ"} in data["transitions"]
    assert data["durations"]["external_management"]["extension"] == 6


async def test_calendar(client: httpx.AsyncClient) -> None:
    data = (await client.get("/api/v1/reference/calendar/2027")).json()
    assert data["verified"]
    assert "2027-11-05" in data["non_working_weekdays"]
    assert data["basis"] == ["TK:112", "PP:1187"]
    old = (await client.get("/api/v1/reference/calendar/2026")).json()
    assert old["basis"] == ["TK:112", "PP:1466"]
    assert not (await client.get("/api/v1/reference/calendar/2030")).json()["verified"]
    assert (await client.get("/api/v1/reference/calendar/1990")).status_code == 422


async def test_term_calculator(client: httpx.AsyncClient) -> None:
    after = (
        await client.post("/api/v1/reference/terms", json={"start": "2026-06-15", "amount": 5, "unit": "calendar_days"})
    ).json()
    assert after["due"] == "2026-06-22"
    assert after["shifted"]
    before = (
        await client.post(
            "/api/v1/reference/terms",
            json={"start": "2026-06-15", "amount": 14, "unit": "calendar_days", "direction": "before"},
        )
    ).json()
    assert before["due"] == "2026-06-01"
    assert before["basis"] == []


async def test_petition_check(client: httpx.AsyncClient) -> None:
    result = (
        await client.post(
            "/api/v1/reference/petition-check",
            json={
                "debtor_kind": "legal_entity",
                "filed_on": "2026-06-01",
                "debts": [{"amount": "2000000", "due_date": "2026-03-01"}],
            },
        )
    ).json()
    assert result["admissible"]
    assert result["threshold"] == "2000000.00"


async def test_collateral_calculator(client: httpx.AsyncClient) -> None:
    result = (
        await client.post(
            "/api/v1/reference/collateral",
            json={"proceeds": "1000", "secured_debt": "500", "first_second_unpaid": "100"},
        )
    ).json()
    assert result["to_secured"] == "500.00"
    assert result["to_estate"] == "400.00"
    assert (await client.post("/api/v1/reference/collateral", json={"proceeds": "1"})).status_code == 422


async def test_validation_errors(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/reference/terms", json={"start": "x", "amount": -1, "unit": "years"})
    assert response.status_code == 422
