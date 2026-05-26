from __future__ import annotations

import uuid

from app.core.config import settings
from app.services.chroma_service import ChromaService, RetrievedChunk, get_chroma_service
from app.services.embedding_service import EmbeddingService, get_embedding_service


class RetrievalService:
    def __init__(self, embedding_service: EmbeddingService, chroma_service: ChromaService):
        self._embedding_service = embedding_service
        self._chroma_service = chroma_service

    async def retrieve(
        self,
        *,
        session_id: uuid.UUID,
        query: str,
    ) -> list[RetrievedChunk]:
        """Retrieve top-k chunks across ALL PDFs in the session."""
        query_vector = await self._embedding_service.embed_query(query)
        return await self._chroma_service.query_chunks(
            session_id=str(session_id),
            query_embedding=query_vector,
            top_k=settings.TOP_K_RESULTS,
        )


_retrieval_service_singleton: RetrievalService | None = None


def get_retrieval_service() -> RetrievalService:
    global _retrieval_service_singleton
    if _retrieval_service_singleton is None:
        _retrieval_service_singleton = RetrievalService(get_embedding_service(), get_chroma_service())
    return _retrieval_service_singleton
