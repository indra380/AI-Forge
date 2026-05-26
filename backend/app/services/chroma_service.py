from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings

logger = logging.getLogger(__name__)

# Chroma collection names: 3-63 chars, alphanumeric + hyphens/underscores, starts with letter
_INVALID_CHARS_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _collection_name(session_id: str) -> str:
    safe = _INVALID_CHARS_RE.sub("_", session_id)
    # Prefix with 's' to guarantee starts with a letter; truncate to 63 chars
    return f"s{safe}"[:63]


@dataclass(slots=True)
class RetrievedChunk:
    text: str
    metadata: dict[str, str | int]
    score: float


class ChromaService:
    """Per-session ChromaDB collections.

    Each chat session gets its own collection so that:
    - Semantic search spans ALL PDFs uploaded in the session automatically.
    - No complex `where` filter needed — the collection itself is the scope.
    - Collections are isolated per user-session, preventing cross-session leakage.
    """

    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=settings.CHROMA_DB_PATH,
            settings=ChromaSettings(
                anonymized_telemetry=settings.CHROMA_ANONYMIZED_TELEMETRY,
                chroma_product_telemetry_impl="app.services.chroma_telemetry.NoOpProductTelemetryClient",
            ),
        )

    def _get_collection(self, session_id: str) -> chromadb.Collection:
        return self._client.get_or_create_collection(name=_collection_name(session_id))

    async def add_chunks(
        self,
        *,
        session_id: str,
        chunk_ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str | int]],
    ) -> None:
        coll = self._get_collection(session_id)
        await asyncio.to_thread(
            coll.upsert,
            ids=chunk_ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    async def collection_has_documents(self, session_id: str) -> bool:
        """Fast check — no embedding required."""
        try:
            coll = self._get_collection(session_id)
            count = await asyncio.to_thread(coll.count)
            return count > 0
        except Exception:
            return False

    async def query_chunks(
        self,
        *,
        session_id: str,
        query_embedding: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        try:
            coll = self._get_collection(session_id)
            count = await asyncio.to_thread(coll.count)
            if count == 0:
                return []
            actual_k = min(top_k, count)
            result = await asyncio.to_thread(
                coll.query,
                query_embeddings=[query_embedding],
                n_results=actual_k,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            logger.exception("ChromaDB query failed for session %s", session_id)
            return []

        docs = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        chunks: list[RetrievedChunk] = []
        for index, text in enumerate(docs):
            chunks.append(
                RetrievedChunk(
                    text=text,
                    metadata=metadatas[index] if index < len(metadatas) else {},
                    score=float(distances[index] if index < len(distances) else 0.0),
                )
            )
        return chunks

    async def delete_session(self, session_id: str) -> None:
        """Remove the collection when a session/thread is deleted."""
        try:
            name = _collection_name(session_id)
            await asyncio.to_thread(self._client.delete_collection, name)
        except Exception:
            pass  # Collection may not exist; safe to ignore


_chroma_service_singleton: ChromaService | None = None


def get_chroma_service() -> ChromaService:
    global _chroma_service_singleton
    if _chroma_service_singleton is None:
        _chroma_service_singleton = ChromaService()
    return _chroma_service_singleton
