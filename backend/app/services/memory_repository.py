from __future__ import annotations

import json
import time
from collections.abc import Sequence
from typing import Protocol

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class MemoryRepository(Protocol):
    """Abstraction for session memory persistence backends."""

    async def get_messages(self, session_id: str) -> list[dict[str, str]]:
        ...

    async def save_messages(self, session_id: str, messages: Sequence[dict[str, str]]) -> None:
        ...

    async def clear_messages(self, session_id: str) -> None:
        ...


class RedisMemoryRepository:
    """Redis implementation for storing per-session chat messages as a JSON array."""

    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int,
        fail_open: bool = True,
        connect_timeout_seconds: float = 0.15,
        operation_timeout_seconds: float = 0.25,
        retry_after_seconds: float = 15.0,
    ):
        self._redis_url = redis_url
        self._ttl_seconds = ttl_seconds
        self._fail_open = fail_open
        self._retry_after_seconds = retry_after_seconds
        self._redis_unavailable_until = 0.0
        self._client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=connect_timeout_seconds,
            socket_timeout=operation_timeout_seconds,
            retry_on_timeout=False,
            health_check_interval=0,
        )
        # In-memory fallback when Redis is temporarily unavailable.
        self._fallback_store: dict[str, list[dict[str, str]]] = {}

    def _can_attempt_redis(self) -> bool:
        return time.monotonic() >= self._redis_unavailable_until

    def _mark_redis_unavailable(self) -> None:
        self._redis_unavailable_until = time.monotonic() + self._retry_after_seconds

    def _clear_unavailable_marker(self) -> None:
        self._redis_unavailable_until = 0.0

    @staticmethod
    def _key(session_id: str) -> str:
        return f"chat:session:{session_id}"

    async def get_messages(self, session_id: str) -> list[dict[str, str]]:
        if self._fail_open and not self._can_attempt_redis():
            return list(self._fallback_store.get(session_id, []))

        key = self._key(session_id)
        try:
            payload = await self._client.get(key)
        except RedisError as exc:
            if self._fail_open:
                self._mark_redis_unavailable()
                logger.warning(
                    "Redis read failed for session %s; using in-process fallback memory", session_id
                )
                return list(self._fallback_store.get(session_id, []))
            logger.exception("Redis read failed for session %s", session_id)
            raise RuntimeError("Session memory unavailable") from exc

        self._clear_unavailable_marker()
        if not payload:
            return list(self._fallback_store.get(session_id, []))

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON payload in Redis for session %s", session_id)
            return []

        if not isinstance(parsed, list):
            logger.warning("Unexpected Redis memory format for session %s", session_id)
            return []

        return [entry for entry in parsed if isinstance(entry, dict)]

    async def save_messages(self, session_id: str, messages: Sequence[dict[str, str]]) -> None:
        if self._fail_open and not self._can_attempt_redis():
            self._fallback_store[session_id] = list(messages)
            return

        key = self._key(session_id)
        serialized = json.dumps(list(messages), ensure_ascii=True)

        try:
            await self._client.set(name=key, value=serialized, ex=self._ttl_seconds)
        except RedisError as exc:
            if self._fail_open:
                self._mark_redis_unavailable()
                logger.warning(
                    "Redis write failed for session %s; storing in in-process fallback memory",
                    session_id,
                )
                self._fallback_store[session_id] = list(messages)
                return
            logger.exception("Redis write failed for session %s", session_id)
            raise RuntimeError("Session memory unavailable") from exc
        self._clear_unavailable_marker()
        self._fallback_store.pop(session_id, None)

    async def clear_messages(self, session_id: str) -> None:
        if self._fail_open and not self._can_attempt_redis():
            self._fallback_store.pop(session_id, None)
            return

        key = self._key(session_id)
        try:
            await self._client.delete(key)
        except RedisError as exc:
            if self._fail_open:
                self._mark_redis_unavailable()
                logger.warning(
                    "Redis delete failed for session %s; clearing in-process fallback memory",
                    session_id,
                )
                self._fallback_store.pop(session_id, None)
                return
            logger.exception("Redis delete failed for session %s", session_id)
            raise RuntimeError("Session memory unavailable") from exc
        self._clear_unavailable_marker()
        self._fallback_store.pop(session_id, None)


_memory_repository_singleton: MemoryRepository | None = None


def get_memory_repository() -> MemoryRepository:
    """Dependency provider for memory repository."""

    global _memory_repository_singleton
    if _memory_repository_singleton is None:
        _memory_repository_singleton = RedisMemoryRepository(
            redis_url=settings.REDIS_URL,
            ttl_seconds=settings.SESSION_MEMORY_TTL_HOURS * 3600,
            fail_open=settings.SESSION_MEMORY_FAIL_OPEN,
            connect_timeout_seconds=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            operation_timeout_seconds=settings.REDIS_OPERATION_TIMEOUT_SECONDS,
            retry_after_seconds=settings.REDIS_RETRY_AFTER_SECONDS,
        )
    return _memory_repository_singleton
