from typing import Protocol

from redis.asyncio import Redis


class Publisher(Protocol):
    async def publish(self, stream: str, fields: dict[str, str]) -> str: ...


class RedisStreamPublisher:
    def __init__(self, client: Redis, maxlen: int = 100_000) -> None:
        self._client = client
        self._maxlen = maxlen

    async def publish(self, stream: str, fields: dict[str, str]) -> str:
        message_id = await self._client.xadd(stream, dict(fields.items()), maxlen=self._maxlen, approximate=True)
        return message_id.decode() if isinstance(message_id, bytes) else str(message_id)

    async def remember_once(self, key: str, ttl_seconds: int) -> bool:
        return bool(await self._client.set(key, "1", nx=True, ex=ttl_seconds))
