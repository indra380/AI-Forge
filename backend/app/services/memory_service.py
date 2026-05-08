from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.core.config import settings
from app.core.logging import get_logger
from app.services.memory_repository import MemoryRepository, get_memory_repository

logger = get_logger(__name__)

MessageRole = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class ConversationMessage:
    role: MessageRole
    content: str
    timestamp: str
    session_id: str


class MemoryService:
    """Business logic for short-term conversational memory."""

    def __init__(self, repository: MemoryRepository):
        self._repository = repository
        self._max_history_messages = settings.MAX_HISTORY_MESSAGES

    async def get_history(self, session_id: str) -> list[ConversationMessage]:
        payload = await self._repository.get_messages(session_id)
        if not payload:
            logger.debug("No session history found for session_id=%s", session_id)
        history: list[ConversationMessage] = []
        for item in payload:
            role = item.get("role")
            content = item.get("content")
            timestamp = item.get("timestamp")
            stored_session_id = item.get("session_id")

            if role not in {"system", "user", "assistant"}:
                continue
            if not isinstance(content, str) or not isinstance(timestamp, str):
                continue
            if not isinstance(stored_session_id, str):
                continue

            history.append(
                ConversationMessage(
                    role=role,
                    content=content,
                    timestamp=timestamp,
                    session_id=stored_session_id,
                )
            )

        return history

    async def save_message(self, session_id: str, role: MessageRole, content: str) -> None:
        trimmed_content = content.strip()
        if not trimmed_content:
            return

        history = await self.get_history(session_id)
        history.append(
            ConversationMessage(
                role=role,
                content=trimmed_content,
                timestamp=datetime.now(UTC).isoformat(),
                session_id=session_id,
            )
        )

        trimmed = self._trim_messages(history)
        await self._repository.save_messages(
            session_id,
            [
                {
                    "role": item.role,
                    "content": item.content,
                    "timestamp": item.timestamp,
                    "session_id": item.session_id,
                }
                for item in trimmed
            ],
        )

    async def clear_session(self, session_id: str) -> None:
        await self._repository.clear_messages(session_id)

    async def build_messages_with_context(
        self,
        *,
        session_id: str,
        system_prompt: str,
        latest_user_message: str,
    ) -> list[dict[str, str]]:
        history = await self.get_history(session_id)
        history = self._trim_messages(history)

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": item.role, "content": item.content} for item in history)
        messages.append({"role": "user", "content": latest_user_message.strip()})

        return self._trim_for_context_budget(messages)

    def _trim_messages(self, history: list[ConversationMessage]) -> list[ConversationMessage]:
        if len(history) <= self._max_history_messages:
            return history
        return history[-self._max_history_messages :]

    def _trim_for_context_budget(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        max_context_chars = settings.MAX_CONTEXT_CHARS
        if max_context_chars <= 0:
            return messages

        if len(messages) <= 2:
            return messages

        system_message = messages[0]
        latest_user_message = messages[-1]
        middle = messages[1:-1]

        budget = max_context_chars - len(system_message["content"]) - len(latest_user_message["content"])
        if budget <= 0:
            logger.warning("Context budget too small; sending only system and latest message")
            return [system_message, latest_user_message]

        kept_reversed: list[dict[str, str]] = []
        used = 0
        for msg in reversed(middle):
            content_len = len(msg.get("content", ""))
            if used + content_len > budget:
                break
            kept_reversed.append(msg)
            used += content_len

        kept_middle = list(reversed(kept_reversed))
        return [system_message, *kept_middle, latest_user_message]


def get_memory_service() -> MemoryService:
    """Dependency provider for memory service."""

    repository: MemoryRepository = get_memory_repository()
    return MemoryService(repository)
