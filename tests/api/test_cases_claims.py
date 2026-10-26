import httpx

from tests.api.conftest import Login
from tests.api.helpers import CASE, observation_case, post, registry_case


async def test_case_lifecycle_with_etag(client: httpx.AsyncClient, manager: dict[str, str]) -> None:
    created = await client.post("/api/v1/cases", json=CASE, headers=manager)
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    assert created.headers["ETag"] == '"1"'
    assert created.headers["Location"] == f"/api/v1/cases/{case_id}"
    base = f"/api/v1/cases/{case_id}"
    stale = await client.post(
        f"{base}/transitions",
        headers={**manager, "If-Match": '"7"'},
        json={"target": "observation", "court_act_date": "2026-03-02"},
    )
    assert stale.status_code == 412
    assert stale.json() == {
        "error": "version_conflict",
        "message": "expected version 7, actual 1",
        "current_version": 1,
    }
    bad = await client.post(
        f"{base}/transitions",
        headers={**manager, "If-Match": "abc"},
        json={"target": "observation", "court_act_date": "2026-03-02"},
    )
    assert bad.status_code == 400
    moved = await client.post(
        f"{base}/transitions",
        headers={**manager, "If-Match": 'W/"1"'},
        json={"target": "observation", "court_act_date": "2026-03-02"},
    )
    assert moved.status_code == 200
    assert moved.headers["ETag"] == '"2"'
    assert "bankruptcy_proceedings" in moved.json()["allowed_transitions"]
    wrong = await client.post(
        f"{base}/transitions", headers=manager, json={"target": "restructuring", "court_act_date": "2026-03-03"}
    )
    assert wrong.status_code == 409
    assert wrong.json()["basis"]["code"] == "127-FZ:27"
    await post(client, f"{base}/manager", manager, {"full_name": "ВУ", "sro": "СРО", "approved_on": "2026-03-02"})
    await post(client, f"{base}/publications", manager, {"kind": "observation", "published_on": "2026-03-07"})
    case = (await client.get(base, headers=manager)).json()
    assert case["version"] == 4
    assert case["manager"]["full_name"] == "ВУ"
    events = (await client.get(f"{base}/events", headers=manager)).json()
    assert [e["type"] for e in events] == ["CaseOpened", "PhaseChanged", "ManagerApproved", "PublicationRecorded"]
    listed = (await client.get("/api/v1/cases?phase=observation", headers=manager)).json()
    assert [c["case_id"] for c in listed] == [case_id]
    assert (await client.get("/api/v1/cases?phase=completed", headers=manager)).json() == []
    deadlines = (await client.get(f"{base}/deadlines", headers=manager)).json()
    assert {d["code"] for d in deadlines} >= {"claims_first_meeting", "case_consideration"}


async def test_invalid_case_payloads(client: httpx.AsyncClient, manager: dict[str, str]) -> None:
    bad_inn = {**CASE, "debtor": {**CASE["debtor"], "inn": "0000000019"}}
    response = await client.post("/api/v1/cases", json=bad_inn, headers=manager)
    assert response.status_code == 422
    assert response.json()["error"] == "validation_failed"
    extra = await client.post("/api/v1/cases", json={**CASE, "extra": 1}, headers=manager)
    assert extra.status_code == 422


async def test_organization_isolation(client: httpx.AsyncClient, manager: dict[str, str], login: Login) -> None:
    case_id = await observation_case(client, manager)
    other = await login("manager@b.test")
    assert (await client.get(f"/api/v1/cases/{case_id}", headers=other)).status_code == 404
    assert (await client.get("/api/v1/cases", headers=other)).json() == []
    missing = await client.get("/api/v1/cases/00000000-0000-0000-0000-000000000000", headers=manager)
    assert missing.status_code == 404
    assert missing.json()["error"] == "not_found"


async def test_claims_flow(client: httpx.AsyncClient, manager: dict[str, str]) -> None:
    case_id = await observation_case(client, manager)
    base = f"/api/v1/cases/{case_id}"
    filed = await client.post(
        f"{base}/claims",
        headers=manager,
        json={
            "creditor_id": "c1",
            "creditor_name": "К1",
            "creditor_kind": "competitive",
            "amounts": {"principal": "1000.10", "interest": "10", "sanctions": "5"},
            "filed_on": "2026-03-20",
            "grounds": "договор",
        },
    )
    assert filed.status_code == 201
    claim = filed.json()
    claim_url = f"{base}/claims/{claim['claim_id']}"
    assert filed.headers["Location"] == claim_url
    assert claim["review_not_before"] == "2026-05-06"
    assert claim["queue"] == "third"
    early = await client.post(
        f"{claim_url}/ruling", headers=manager, json={"included": True, "ruling_date": "2026-05-05"}
    )
    assert early.status_code == 422
    assert early.json()["basis"]["code"] == "127-FZ:71.2"
    await post(
        client, f"{claim_url}/objections", manager, {"objector": "К2", "reason": "размер", "filed_on": "2026-04-01"}
    )
    ruled = await post(
        client,
        f"{claim_url}/ruling",
        manager,
        {"included": True, "ruling_date": "2026-05-06", "amounts": {"principal": "1000.10", "interest": "10"}},
    )
    assert ruled["status"] == "included"
    assert ruled["included"]["total"] == "1010.10"
    sanction_first = await client.post(
        f"{claim_url}/payments",
        headers=manager,
        json={"amounts": {"principal": "1", "sanctions": "1"}, "paid_on": "2026-06-01"},
    )
    assert sanction_first.status_code == 422
    paid = await post(
        client, f"{claim_url}/payments", manager, {"amounts": {"principal": "500"}, "paid_on": "2026-06-01"}
    )
    assert paid["outstanding"]["principal"] == "500.10"
    excluded = await post(client, f"{claim_url}/exclusion", manager, {"ruling_date": "2026-07-01", "reason": "отмена"})
    assert excluded["status"] == "excluded"
    assert (await client.get(f"{base}/claims?status=excluded", headers=manager)).json()[0]["claim_id"] == claim[
        "claim_id"
    ]
    assert (await client.get(f"{base}/claims?status=included", headers=manager)).json() == []
    assert (await client.get(f"{base}/claims/nope", headers=manager)).status_code == 404
    zero = await client.post(
        f"{base}/claims",
        headers=manager,
        json={
            "creditor_id": "c",
            "creditor_name": "К",
            "creditor_kind": "competitive",
            "amounts": {"principal": "0"},
            "filed_on": "2026-03-20",
            "grounds": "д",
        },
    )
    assert zero.status_code == 422


async def test_registry_csv_and_distribution(client: httpx.AsyncClient, manager: dict[str, str]) -> None:
    case_id = await registry_case(client, manager)
    base = f"/api/v1/cases/{case_id}"
    registry = (await client.get(f"{base}/registry?as_of=2026-06-01", headers=manager)).json()
    third = next(q for q in registry["queues"] if q["queue"] == "third")
    assert registry["total"] == "1050.00"
    assert third["secured"] == "600.00"
    assert len(third["claims"]) == 3
    for url in (f"{base}/registry.csv?as_of=2026-06-01", f"/api/v1/exports/registry/{case_id}?as_of=2026-06-01"):
        csv = await client.get(url, headers=manager)
        assert csv.status_code == 200
        assert csv.headers["content-type"].startswith("text/csv")
        lines = csv.content.decode("utf-8-sig").strip().splitlines()
        assert lines[0].startswith("queue;claim_id")
        assert len(lines) == 4
    distribution = (
        await client.post(
            f"{base}/distribution?as_of=2026-06-01",
            headers=manager,
            json={
                "available": "250",
                "current_payments": [{"payment_id": "fee", "order": "first", "amount": "50", "due_date": "2026-05-01"}],
            },
        )
    ).json()
    assert distribution["paid"] == "250.00"
    assert distribution["remainder"] == "0.00"
    tiers = {t["tier"]: t for t in distribution["tiers"]}
    assert tiers["registry:third"]["allocated"] == "200.00"
    assert tiers["registry:third_sanctions"]["allocated"] == "0.00"
    collateral = (
        await client.post(f"{base}/collateral", headers=manager, json={"proceeds": "1000", "claim_id": "bank"})
    ).json()
    assert collateral["to_secured"] == "600.00"
    assert collateral["basis"][0] == "127-FZ:138.2"
    not_secured = await client.post(
        f"{base}/collateral", headers=manager, json={"proceeds": "1000", "claim_id": "supplier"}
    )
    assert not_secured.status_code == 422
    unknown = await client.post(f"{base}/collateral", headers=manager, json={"proceeds": "1", "claim_id": "x"})
    assert unknown.status_code == 404
    manual = await client.post(f"{base}/collateral", headers=manager, json={"proceeds": "10", "secured_debt": "5"})
    assert manual.json()["to_secured"] == "5.00"
    neither = await client.post(f"{base}/collateral", headers=manager, json={"proceeds": "10"})
    assert neither.status_code == 422
