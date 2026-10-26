from typing import Any

import httpx

CASE = {
    "case_number": "А00-7/2026",
    "court": "Тестовый арбитражный суд",
    "debtor": {"kind": "legal_entity", "name": "ООО «Тест»", "inn": "0000000018", "ogrn": "1000000000010"},
    "petition_received_on": "2026-02-02",
}


async def post(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], body: Any = None, expected: int = 200
) -> Any:
    response = await client.post(url, json=body, headers=headers)
    assert response.status_code == expected, response.text
    return response.json()


async def observation_case(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    case = await post(client, "/api/v1/cases", headers, CASE, 201)
    base = f"/api/v1/cases/{case['case_id']}"
    await post(
        client,
        f"{base}/transitions",
        headers,
        {"target": "observation", "court_act_date": "2026-03-02", "hearing_on": "2026-09-01"},
    )
    await post(client, f"{base}/publications", headers, {"kind": "observation", "published_on": "2026-03-07"})
    return str(case["case_id"])


async def registry_case(client: httpx.AsyncClient, headers: dict[str, str]) -> str:
    case_id = await observation_case(client, headers)
    base = f"/api/v1/cases/{case_id}"
    claims = [
        ("bank", "c-bank", "competitive", {"principal": "600", "interest": "0", "sanctions": "0"}, True),
        ("supplier", "c-sup", "competitive", {"principal": "300", "interest": "0", "sanctions": "50"}, False),
        ("tax", "c-fns", "authorized_body", {"principal": "100"}, False),
    ]
    for claim_id, creditor, kind, amounts, secured in claims:
        await post(
            client,
            f"{base}/claims",
            headers,
            {
                "claim_id": claim_id,
                "creditor_id": creditor,
                "creditor_name": creditor,
                "creditor_kind": kind,
                "amounts": amounts,
                "filed_on": "2026-03-20",
                "grounds": "договор",
                "secured": secured,
                "credit_agreement": secured,
            },
            201,
        )
        await post(client, f"{base}/claims/{claim_id}/ruling", headers, {"included": True, "ruling_date": "2026-05-12"})
    return case_id
