from __future__ import annotations

from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.llm import llm


class LlmService:
    async def stream_response(
        self,
        *,
        messages: list[SystemMessage | HumanMessage | AIMessage],
        user_email: str,
    ) -> AsyncGenerator[str, None]:
        config = {"metadata": {"user_email": user_email}}
        async for chunk in llm.astream(messages, config=config):
            content = getattr(chunk, "content", "")
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            if content:
                yield str(content)


_singleton: LlmService | None = None


def get_llm_service() -> LlmService:
    global _singleton
    if _singleton is None:
        _singleton = LlmService()
    return _singleton
