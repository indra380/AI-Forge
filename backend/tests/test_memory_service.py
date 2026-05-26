from __future__ import annotations

from collections.abc import Sequence

import pytest

from app.services.memory_repository import MemoryRepository
from app.services.memory_service import MemoryService


class InMemoryRepository(MemoryRepository):
    def __init__(self):
        self.storage: dict[str, list[dict[str, str]]] = {}

    async def get_messages(self, session_id: str) -> list[dict[str, str]]:
        return list(self.storage.get(session_id, []))

    async def save_messages(self, session_id: str, messages: Sequence[dict[str, str]]) -> None:
        self.storage[session_id] = list(messages)

    async def clear_messages(self, session_id: str) -> None:
        self.storage.pop(session_id, None)


@pytest.mark.asyncio
async def test_session_isolation() -> None:
    repo = InMemoryRepository()
    service = MemoryService(repo)

    await service.save_message("session-a", "user", "I use AWS DevOps")
    await service.save_message("session-b", "user", "I use Azure")

    history_a = await service.get_history("session-a")
    history_b = await service.get_history("session-b")

    assert len(history_a) == 1
    assert len(history_b) == 1
    assert history_a[0].content == "I use AWS DevOps"
    assert history_b[0].content == "I use Azure"


@pytest.mark.asyncio
async def test_history_retrieval_and_persistence() -> None:
    repo = InMemoryRepository()
    service = MemoryService(repo)

    await service.save_message("session-1", "user", "My name is John")
    await service.save_message("session-1", "assistant", "Nice to meet you John")

    history = await service.get_history("session-1")

    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"
    assert history[0].session_id == "session-1"
    assert history[1].session_id == "session-1"


@pytest.mark.asyncio
async def test_trimming_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = InMemoryRepository()
    service = MemoryService(repo)
    monkeypatch.setattr(service, "_max_history_messages", 3)

    await service.save_message("session-1", "user", "m1")
    await service.save_message("session-1", "assistant", "m2")
    await service.save_message("session-1", "user", "m3")
    await service.save_message("session-1", "assistant", "m4")

    history = await service.get_history("session-1")
    assert [item.content for item in history] == ["m2", "m3", "m4"]


@pytest.mark.asyncio
async def test_context_injection_includes_recent_history() -> None:
    repo = InMemoryRepository()
    service = MemoryService(repo)

    await service.save_message("session-1", "user", "My name is John")
    await service.save_message("session-1", "assistant", "Nice to meet you John")

    context = await service.build_messages_with_context(
        session_id="session-1",
        system_prompt="You are helpful.",
        latest_user_message="What is my name?",
    )

    assert context[0] == {"role": "system", "content": "You are helpful."}
    assert context[1] == {"role": "user", "content": "My name is John"}
    assert context[2] == {"role": "assistant", "content": "Nice to meet you John"}
    assert context[3] == {"role": "user", "content": "What is my name?"}


@pytest.mark.asyncio
async def test_clear_session_memory() -> None:
    repo = InMemoryRepository()
    service = MemoryService(repo)

    await service.save_message("session-1", "user", "persist me")
    await service.clear_session("session-1")

    history = await service.get_history("session-1")
    assert history == []


# ==============================================================================
# 5 Conversation Window Tests (10 Messages)
# ==============================================================================


@pytest.mark.asyncio
async def test_memory_window_stores_exactly_5_conversations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify latest 5 conversations (10 messages) are stored."""
    repo = InMemoryRepository()
    service = MemoryService(repo)
    monkeypatch.setattr(service, "_max_history_messages", 10)

    session_id = "test-5-conversations"

    # Save 6 conversations (12 messages)
    for i in range(6):
        await service.save_message(session_id, "user", f"User Q{i}")
        await service.save_message(session_id, "assistant", f"Assistant A{i}")

    history = await service.get_history(session_id)

    # Should keep only latest 10 messages (conversations 1-5)
    assert len(history) == 10
    assert "User Q0" not in [m.content for m in history]  # Oldest conversation trimmed
    assert "User Q1" in [m.content for m in history]  # Conversation 1 kept
    assert "Assistant A5" in [m.content for m in history]  # Latest conversation kept


@pytest.mark.asyncio
async def test_memory_window_preserves_conversation_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify user-assistant pairs maintain correct order."""
    repo = InMemoryRepository()
    service = MemoryService(repo)
    monkeypatch.setattr(service, "_max_history_messages", 10)

    session_id = "test-conversation-order"

    conversations = [
        ("What is Python?", "Python is a programming language."),
        ("Is it dynamically typed?", "Yes, Python is dynamically typed."),
        ("What frameworks exist?", "Django, FastAPI, Flask are popular."),
    ]

    for user_msg, assistant_msg in conversations:
        await service.save_message(session_id, "user", user_msg)
        await service.save_message(session_id, "assistant", assistant_msg)

    history = await service.get_history(session_id)

    # Verify correct order and alternation
    assert len(history) == 6
    assert history[0].role == "user" and history[0].content == "What is Python?"
    assert history[1].role == "assistant" and "language" in history[1].content
    assert history[2].role == "user" and "dynamically" in history[2].content
    assert history[3].role == "assistant" and "dynamically" in history[3].content


# ==============================================================================
# Context Building Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_context_always_includes_system_prompt() -> None:
    """Verify system prompt is always first."""
    repo = InMemoryRepository()
    service = MemoryService(repo)

    messages = await service.build_messages_with_context(
        session_id="empty-session",
        system_prompt="You are helpful.",
        latest_user_message="Hello",
    )

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are helpful."
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Hello"


@pytest.mark.asyncio
async def test_context_budget_trimming(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify middle messages are trimmed when context exceeds budget."""
    repo = InMemoryRepository()
    service = MemoryService(repo)
    monkeypatch.setattr(service, "_max_context_chars", 100)

    # Create messages with predictable sizes
    messages = [
        {"role": "system", "content": "System"},  # ~6 chars
        {"role": "user", "content": "A" * 40},  # 40 chars (will be trimmed)
        {"role": "assistant", "content": "B" * 40},  # 40 chars (kept)
        {"role": "user", "content": "Latest"},  # 6 chars
    ]

    trimmed = service._trim_for_context_budget(messages)

    # Should keep system + at least one middle + latest
    assert trimmed[0]["role"] == "system"
    assert trimmed[-1]["content"] == "Latest"
    # First middle message (A*40) should be removed
    assert not any("A" * 40 in m.get("content", "") for m in trimmed)


@pytest.mark.asyncio
async def test_context_never_drops_latest_user_message() -> None:
    """Verify latest user message is always included, even if over budget."""
    repo = InMemoryRepository()
    service = MemoryService(repo)
    # Force very tight budget
    service._max_context_chars = 10

    messages = [
        {"role": "system", "content": "Help"},
        {"role": "user", "content": "X" * 100},
        {"role": "assistant", "content": "Y" * 100},
        {"role": "user", "content": "Latest query that must stay"},
    ]

    trimmed = service._trim_for_context_budget(messages)

    assert trimmed[-1]["role"] == "user"
    assert "Latest query" in trimmed[-1]["content"]


# ==============================================================================
# Message Trimming Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_trim_oldest_messages_first_fifo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify FIFO: oldest messages are removed first."""
    repo = InMemoryRepository()
    service = MemoryService(repo)
    monkeypatch.setattr(service, "_max_history_messages", 2)

    session_id = "test-fifo-trim"

    await service.save_message(session_id, "user", "First")
    await service.save_message(session_id, "user", "Second")
    await service.save_message(session_id, "user", "Third")

    history = await service.get_history(session_id)

    assert len(history) == 2
    assert "First" not in [m.content for m in history]
    assert "Second" in [m.content for m in history]
    assert "Third" in [m.content for m in history]


@pytest.mark.asyncio
async def test_empty_messages_not_stored() -> None:
    """Verify empty and whitespace-only messages are not saved."""
    repo = InMemoryRepository()
    service = MemoryService(repo)

    session_id = "test-empty"

    await service.save_message(session_id, "user", "")
    await service.save_message(session_id, "user", "   \n\t  ")
    await service.save_message(session_id, "user", "Real message")

    history = await service.get_history(session_id)

    assert len(history) == 1
    assert history[0].content == "Real message"


# ==============================================================================
# Multi-Session Isolation Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_clearing_one_session_preserves_others() -> None:
    """Verify clearing one session doesn't affect others."""
    repo = InMemoryRepository()
    service = MemoryService(repo)

    await service.save_message("session-1", "user", "Session 1 data")
    await service.save_message("session-2", "user", "Session 2 data")

    await service.clear_session("session-1")

    history_1 = await service.get_history("session-1")
    history_2 = await service.get_history("session-2")

    assert len(history_1) == 0
    assert len(history_2) == 1
    assert history_2[0].content == "Session 2 data"


# ==============================================================================
# Message Timestamp Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_messages_have_iso_timestamps() -> None:
    """Verify messages have valid ISO format timestamps."""
    repo = InMemoryRepository()
    service = MemoryService(repo)

    await service.save_message("session-1", "user", "Timestamped message")

    history = await service.get_history("session-1")

    assert len(history) == 1
    # Should be valid ISO 8601 format
    timestamp = history[0].timestamp
    assert "T" in timestamp  # ISO format includes T
    assert "+" in timestamp or "Z" in timestamp  # Timezone info


# ==============================================================================
# Special Character Handling Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_preserves_special_characters_and_newlines() -> None:
    """Verify content with special chars, newlines, etc. is preserved."""
    repo = InMemoryRepository()
    service = MemoryService(repo)

    content = '''```python
def hello():
    return "world"
```
Special: @#$%^&*()
Emoji: 🚀 ✨'''

    await service.save_message("session-1", "user", content)

    history = await service.get_history("session-1")

    assert history[0].content == content


@pytest.mark.asyncio
async def test_strips_leading_trailing_whitespace() -> None:
    """Verify leading/trailing whitespace is trimmed."""
    repo = InMemoryRepository()
    service = MemoryService(repo)

    await service.save_message("session-1", "user", "\n\n  Message  \t\n")

    history = await service.get_history("session-1")

    assert history[0].content == "Message"


# ==============================================================================
# Full Conversation Flow Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_full_conversation_remember_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test complete conversation: AI remembers earlier context."""
    repo = InMemoryRepository()
    service = MemoryService(repo)
    monkeypatch.setattr(service, "_max_history_messages", 10)

    session_id = "test-remember"

    # User talks about AWS
    await service.save_message(session_id, "user", "I work in AWS")
    await service.save_message(session_id, "assistant", "AWS is a powerful cloud!")

    # Several exchanges later
    await service.save_message(session_id, "user", "What about databases?")
    await service.save_message(session_id, "assistant", "RDS, DynamoDB, etc.")

    # User asks about something mentioned earlier
    context = await service.build_messages_with_context(
        session_id=session_id,
        system_prompt="You remember context.",
        latest_user_message="What cloud did I mention?",
    )

    content_str = str(context)
    assert "AWS" in content_str
    assert "What cloud did I mention?" in content_str
