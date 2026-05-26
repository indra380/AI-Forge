"""In-chat RAG service.

Handles automatic PDF indexing and retrieval directly inside the normal chat flow.
- index_pdf()       : called after a PDF is uploaded as a chat attachment
- retrieve_context(): called before the LLM to inject relevant document context
- has_documents()   : fast check, no embedding required

One ChromaDB collection per chat session → semantic search spans ALL uploaded PDFs
automatically without the user selecting a document.
"""
from __future__ import annotations

import logging
from pathlib import Path
import uuid

from app.core.config import settings
from app.services.chroma_service import ChromaService, get_chroma_service
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.pdf_service import PdfService, get_pdf_service

logger = logging.getLogger(__name__)


class InChatRagService:
    def __init__(
        self,
        pdf_service: PdfService,
        embedding_service: EmbeddingService,
        chroma_service: ChromaService,
    ) -> None:
        self._pdf = pdf_service
        self._embed = embedding_service
        self._chroma = chroma_service

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def index_pdf(
        self,
        *,
        session_id: uuid.UUID,
        document_id: uuid.UUID,
        file_path: Path,
        filename: str,
    ) -> None:
        """Extract, chunk, embed, and upsert a PDF into the session collection.

        Safe to call from a FastAPI BackgroundTask — no DB session required.
        Re-indexing the same document is idempotent (uses upsert).
        """
        try:
            pages = self._pdf.extract_pages(file_path)
        except Exception:
            logger.exception("PDF extraction failed: %s", filename)
            return

        if not pages:
            logger.warning("Empty extraction for %s — skipping index", filename)
            return

        chunks = self._pdf.chunk_pages(pages)
        if not chunks:
            logger.warning("No chunks produced from %s — skipping index", filename)
            return

        texts = [chunk.text for chunk in chunks]

        try:
            vectors = await self._embed.embed_texts(texts)
        except Exception:
            logger.exception("Embedding failed for %s", filename)
            return

        metadatas: list[dict[str, str | int]] = []
        chunk_ids: list[str] = []
        for chunk in chunks:
            chunk_ids.append(f"{document_id}:{chunk.chunk_index}")
            metadatas.append(
                {
                    "document_id": str(document_id),
                    "filename": filename,
                    "page": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
            )

        try:
            await self._chroma.add_chunks(
                session_id=str(session_id),
                chunk_ids=chunk_ids,
                texts=texts,
                embeddings=vectors,
                metadatas=metadatas,
            )
            logger.info(
                "Indexed %d chunks from '%s' into session %s",
                len(chunks),
                filename,
                session_id,
            )
        except Exception:
            logger.exception("ChromaDB upsert failed for %s", filename)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def has_documents(self, session_id: uuid.UUID) -> bool:
        """True if the session has any indexed PDF chunks — no embedding call."""
        return await self._chroma.collection_has_documents(str(session_id))

    async def retrieve_context(
        self,
        *,
        session_id: uuid.UUID,
        query: str,
    ) -> tuple[str, list[dict[str, str | int]]]:
        """Return (context_text, citations) to inject into the LLM prompt.

        context_text is empty string when no relevant chunks are found.
        Automatically searches across ALL PDFs uploaded in the session.
        """
        if not await self._chroma.collection_has_documents(str(session_id)):
            return "", []

        try:
            query_vector = await self._embed.embed_query(query)
        except Exception:
            logger.exception("Query embedding failed; skipping RAG for this turn")
            return "", []

        chunks = await self._chroma.query_chunks(
            session_id=str(session_id),
            query_embedding=query_vector,
            top_k=settings.TOP_K_RESULTS,
        )

        if not chunks:
            return "", []

        lines: list[str] = []
        budget = 12_000
        used = 0
        citations: list[dict[str, str | int]] = []
        seen: set[tuple[str, int]] = set()

        for chunk in chunks:
            filename = str(chunk.metadata.get("filename", "document"))
            page = int(chunk.metadata.get("page", 0))
            snippet = chunk.text.strip()
            block = f"[Source: {filename}, page {page}]\n{snippet}"
            if used + len(block) > budget:
                break
            lines.append(block)
            used += len(block)
            key = (filename, page)
            if key not in seen:
                seen.add(key)
                citations.append({"filename": filename, "page": page})

        return "\n\n".join(lines), citations

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def delete_session(self, session_id: uuid.UUID) -> None:
        """Drop the ChromaDB collection when a thread/session is deleted."""
        await self._chroma.delete_session(str(session_id))


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_singleton: InChatRagService | None = None


def get_in_chat_rag_service() -> InChatRagService:
    global _singleton
    if _singleton is None:
        _singleton = InChatRagService(
            pdf_service=get_pdf_service(),
            embedding_service=get_embedding_service(),
            chroma_service=get_chroma_service(),
        )
    return _singleton
