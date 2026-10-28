import httpx

from tests.api.conftest import Login
from tests.api.helpers import post, registry_case


async def test_meeting_flow(client: httpx.AsyncClient, manager: dict[str, str]) -> None:
    case_id = await registry_case(client, manager)
    base = f"/api/v1/cases/{case_id}"
    created = await client.post(
        f"{base}/meetings",
        headers=manager,
        json={
            "meeting_id": "m1",
            "meeting_on": "2026-06-15",
            "first": True,
            "agenda": [
                {"item_id": "i1", "question": "ordinary", "title": "Отчет"},
                {"item_id": "i2", "question": "bankruptcy_petition", "title": "Банкротство"},
            ],
        },
    )
    assert created.status_code == 201
    assert created.headers["Location"] == f"{base}/meetings/m1"
    meeting = f"{base}/meetings/m1"
    terms = (await client.get(f"{meeting}/terms", headers=manager)).json()
    assert {t["code"] for t in terms["notice"]} == {"notice_post", "notice_other", "notice_efrsb"}
    await post(client, f"{meeting}/notices", manager, {"method": "efrsb", "sent_on": "2026-05-20", "recipients": 3})
    notified = await post(
        client, f"{meeting}/notices", manager, {"method": "post", "sent_on": "2026-05-25", "recipients": 3}
    )
    assert notified["properly_notified"]
    assert {v["creditor_id"]: v["share_percent"] for v in notified["voters"]} == {
        "c-bank": "60.00",
        "c-sup": "30.00",
        "c-fns": "10.00",
    }
    for creditor in ("c-bank", "c-sup"):
        await post(client, f"{meeting}/participants", manager, {"creditor_id": creditor})
    await post(client, f"{meeting}/ballots", manager, {"item_id": "i1", "creditor_id": "c-bank", "vote": "for"})
    await post(client, f"{meeting}/ballots", manager, {"item_id": "i2", "creditor_id": "c-bank", "vote": "for"})
    duplicate = await client.post(
        f"{meeting}/ballots", headers=manager, json={"item_id": "i1", "creditor_id": "c-bank", "vote": "against"}
    )
    assert duplicate.status_code == 422
    concluded = await post(client, f"{meeting}/conclusion", manager)
    assert concluded["status"] == "held"
    assert concluded["quorum"]["reached"]
    results = {r["item_id"]: r for r in concluded["results"]}
    assert results["i1"]["adopted"]
    assert results["i2"]["adopted"]
    assert results["i2"]["rule"] == "majority_of_total"
    again = await client.post(f"{meeting}/conclusion", headers=manager)
    assert again.status_code == 409
    listed = (await client.get(f"{base}/meetings", headers=manager)).json()
    assert [m["meeting_id"] for m in listed] == ["m1"]
    deadlines = {d["code"] for d in (await client.get(f"{base}/deadlines", headers=manager)).json()}
    assert "protocol_to_court:m1" in deadlines
    assert (await client.get(f"{base}/meetings/nope", headers=manager)).status_code == 404
    assert (await client.get(f"{base}/meetings/nope/terms", headers=manager)).status_code == 404


async def test_cancel_meeting(client: httpx.AsyncClient, manager: dict[str, str]) -> None:
    case_id = await registry_case(client, manager)
    base = f"/api/v1/cases/{case_id}"
    meeting = await post(
        client,
        f"{base}/meetings",
        manager,
        {"meeting_on": "2026-06-15", "agenda": [{"question": "ordinary", "title": "Отчет"}]},
        201,
    )
    cancelled = await post(
        client, f"{base}/meetings/{meeting['meeting_id']}/cancellation", manager, {"reason": "перенос"}
    )
    assert cancelled["status"] == "cancelled"


async def test_requisitions_by_creditor(client: httpx.AsyncClient, manager: dict[str, str], login: Login) -> None:
    case_id = await registry_case(client, manager)
    base = f"/api/v1/cases/{case_id}"
    creditor = await login("creditor@a.test")
    created = await post(
        client,
        f"{base}/requisitions",
        creditor,
        {"requisition_id": "r1", "creditor_ids": ["c-sup"], "received_on": "2026-06-01", "agenda": ["Отчет"]},
        201,
    )
    assert created["valid"]
    assert created["hold_by"] == "2026-06-22"
    assert created["share_percent"] == "33.33"
    listed = (await client.get(f"{base}/requisitions", headers=creditor)).json()
    assert [r["requisition_id"] for r in listed] == ["r1"]
    auditor = await login("auditor@a.test")
    forbidden = await client.post(
        f"{base}/requisitions", headers=auditor, json={"creditor_ids": [], "received_on": "2026-06-01", "agenda": ["x"]}
    )
    assert forbidden.status_code == 403
