from typing import Any

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from insolvency_hub import __version__

router = APIRouter(tags=["system"])


@router.get("/health")
async def live() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
async def ready(request: Request, response: Response) -> dict[str, Any]:
    checks: dict[str, str] = {}
    try:
        async with request.app.state.sessions() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {type(exc).__name__}"
    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"
    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
