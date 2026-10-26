from typing import Any

from sqlalchemy import text


async def test_main_app_lifespan_opens_and_closes_resources(sessions: Any, redis_client: Any) -> None:
    from insolvency_hub.main import app

    async with app.router.lifespan_context(app):
        async with app.state.sessions() as session:
            assert await session.scalar(text("SELECT 1")) == 1
        assert await app.state.redis.ping()
