from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from insolvency_hub.core.config import get_settings

MOSCOW = ZoneInfo("Europe/Moscow")


def today() -> date:
    override = get_settings().today_override
    return date.fromisoformat(override) if override else datetime.now(MOSCOW).date()


def now() -> datetime:
    return datetime.now(UTC)
