from collections.abc import AsyncIterator
from pathlib import Path
import uuid

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.chains.chat_chain import build_chat_chain
from app.ai.llm import llm
from app.models.chat_message import ChatMessage
from app.models.chat_thread import ChatThread

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "ai" / "prompts"


def load_chat_system_prompt() -> str:
    return (_PROMPTS_DIR / "chat_system.txt").read_text(encoding="utf-8").strip()


def _build_title_chain() -> StrOutputParser:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", (_PROMPTS_DIR / "thread_title_system.txt").read_text(encoding="utf-8").strip()),
            ("human", (_PROMPTS_DIR / "thread_title_human.txt").read_text(encoding="utf-8").strip()),
        ]
    )
    return prompt | llm | StrOutputParser()


async def generate_thread_title(first_message: str, user_email: str) -> str:
    chain = _build_title_chain()
    config = {"metadata": {"user_email": user_email}}
    title = await chain.ainvoke({"first_message": first_message}, config=config)
    return title.strip()[:255] or "New Chat"


async def stream_chat_response(message: str, user_email: str) -> AsyncIterator[str]:
    chain = build_chat_chain()
    config = {"metadata": {"user_email": user_email}}

    async for chunk in chain.astream({"human_input": message}, config=config):
        if chunk:
            yield chunk


async def complete_chat_response(message: str, user_email: str) -> str:
    chain = build_chat_chain()
    config = {"metadata": {"user_email": user_email}}
    return await chain.ainvoke({"human_input": message}, config=config)


async def save_chat_message(
    db: AsyncSession,
    user_id: uuid.UUID,
    thread_id: uuid.UUID,
    role: str,
    content: str,
) -> ChatMessage:
    message = ChatMessage(user_id=user_id, thread_id=thread_id, role=role, content=content)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def list_chat_messages(
    db: AsyncSession, user_id: uuid.UUID, thread_id: uuid.UUID
) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id, ChatMessage.thread_id == thread_id)
        .order_by(ChatMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

