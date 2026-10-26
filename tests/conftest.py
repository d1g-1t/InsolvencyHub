import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

TEST_DB = os.environ.get("IH_TEST_DATABASE_URL")
TEST_REDIS = os.environ.get("IH_TEST_REDIS_URL")
if TEST_DB:
    os.environ["IH_DATABASE_URL"] = TEST_DB
if TEST_REDIS:
    os.environ["IH_REDIS_URL"] = TEST_REDIS
os.environ.setdefault("IH_LOG_JSON", "false")

TABLES = ("meeting_view", "claim_view", "case_view", "outbox", "events", "users", "organizations")
ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "test-password"
ORG_A = "00000000-0000-4000-8000-00000000000a"
ORG_B = "00000000-0000-4000-8000-00000000000b"
USERS = (
    ("admin@a.test", ORG_A, "admin"),
    ("manager@a.test", ORG_A, "manager"),
    ("creditor@a.test", ORG_A, "creditor"),
    ("auditor@a.test", ORG_A, "auditor"),
    ("manager@b.test", ORG_B, "manager"),
    ("disabled@a.test", ORG_A, "manager"),
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "/api/" in str(item.path) or "/integration/" in str(item.path):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def migrated() -> str:
    if not TEST_DB or not TEST_REDIS:
        pytest.skip("IH_TEST_DATABASE_URL and IH_TEST_REDIS_URL are required")
    from alembic import command
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DB)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return TEST_DB


@pytest.fixture(scope="session")
def password_hash() -> str:
    from insolvency_hub.core.security import hash_password

    return hash_password(PASSWORD)


@pytest.fixture
async def sessions(migrated: str, password_hash: str) -> AsyncIterator[object]:
    from sqlalchemy import text

    from insolvency_hub.infrastructure.db import make_engine, make_session_factory
    from insolvency_hub.infrastructure.models import Organization, User

    engine = make_engine(migrated, null_pool=True)
    factory = make_session_factory(engine)
    async with factory() as session:
        await session.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        session.add_all([Organization(id=ORG_A, name="A"), Organization(id=ORG_B, name="B")])
        await session.flush()
        for email, org, role in USERS:
            session.add(
                User(
                    id=str(uuid.uuid4()),
                    organization_id=org,
                    email=email,
                    password_hash=password_hash,
                    full_name=email,
                    role=role,
                    is_active=not email.startswith("disabled"),
                )
            )
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
async def redis_client(migrated: str) -> AsyncIterator[object]:
    from redis.asyncio import Redis

    assert TEST_REDIS
    client = Redis.from_url(TEST_REDIS)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
