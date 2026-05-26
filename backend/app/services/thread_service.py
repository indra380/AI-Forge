from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_thread import ChatThread


async def create_thread(db: AsyncSession, user_id: uuid.UUID, title: str = "New Chat") -> ChatThread:
    thread = ChatThread(user_id=user_id, title=title, type="chat")
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


async def list_threads(db: AsyncSession, user_id: uuid.UUID) -> list[ChatThread]:
    stmt = (
        select(ChatThread)
        .where(ChatThread.user_id == user_id)
        .order_by(ChatThread.updated_at.desc())
        .limit(5)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_thread(db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID) -> ChatThread | None:
    stmt = select(ChatThread).where(
        ChatThread.id == thread_id, ChatThread.user_id == user_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_thread_type(
    db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> str | None:
    stmt = select(ChatThread.type).where(
        ChatThread.id == thread_id, ChatThread.user_id == user_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def rename_thread(
    db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID, title: str
) -> ChatThread | None:
    thread = await get_thread(db, thread_id, user_id)
    if thread is None:
        return None
    thread.title = title
    thread.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(thread)
    return thread


async def delete_thread(
    db: AsyncSession, thread_id: uuid.UUID, user_id: uuid.UUID
) -> bool:
    thread = await get_thread(db, thread_id, user_id)
    if thread is None:
        return False
    await db.delete(thread)
    await db.commit()
    return True


async def touch_thread(db: AsyncSession, thread: ChatThread, *, commit: bool = True) -> None:
    thread.updated_at = datetime.now(timezone.utc)
    if commit:
        await db.commit()
