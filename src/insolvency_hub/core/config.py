from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_KEY = "0" * 64


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IH_", env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://ih:ih@localhost:5426/insolvency_hub"
    redis_url: str = "redis://localhost:6326/0"
    paseto_key_hex: SecretStr = Field(default=SecretStr(DEV_KEY))
    token_ttl_minutes: int = 60
    events_stream: str = "insolvency_hub:events"
    reminders_stream: str = "insolvency_hub:reminders"
    reminder_horizon_days: int = 5
    outbox_batch: int = 100
    log_json: bool = True
    today_override: str | None = None

    @model_validator(mode="after")
    def check_key(self) -> Self:
        key = self.paseto_key_hex.get_secret_value()
        if len(key) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in key):
            raise ValueError("IH_PASETO_KEY_HEX must be 32 bytes in hex")
        if self.env == "prod" and key == DEV_KEY:
            raise ValueError("IH_PASETO_KEY_HEX must be set in prod")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
