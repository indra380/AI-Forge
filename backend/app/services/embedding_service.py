from __future__ import annotations

import asyncio

from app.ai.llm import embeddings
from app.core.config import settings


class EmbeddingService:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        batch_size = 32
        out: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors = await self._embed_batch_with_retry(batch)
            out.extend(vectors)
        return out

    async def embed_query(self, query: str) -> list[float]:
        vectors = await self._embed_batch_with_retry([query])
        return vectors[0]

    async def _embed_batch_with_retry(self, batch: list[str], retries: int = 2) -> list[list[float]]:
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return await asyncio.to_thread(embeddings.embed_documents, batch)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= retries:
                    break
                await asyncio.sleep(0.4 * (attempt + 1))
        assert last_exc is not None
        raise RuntimeError("Embedding generation failed") from last_exc


_embedding_service_singleton: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service_singleton
    if _embedding_service_singleton is None:
        _embedding_service_singleton = EmbeddingService()
    return _embedding_service_singleton
