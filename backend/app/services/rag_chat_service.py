from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
import uuid

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import llm
from app.core.config import settings
from app.models.attachment import Attachment
from app.models.user import User
from app.schemas.rag import RagCitation
from app.services.chroma_service import ChromaService, RetrievedChunk, get_chroma_service
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.memory_service import MemoryService, get_memory_service
from app.services.pdf_service import PdfService, get_pdf_service
from app.services.retrieval_service import RetrievalService, get_retrieval_service


@dataclass(slots=True)
class RagChatResult:
    response: str
    citations: list[RagCitation]


class _InMemoryRateLimiter:
    def __init__(self, limit_per_minute: int = 30):
        self._limit = limit_per_minute
        self._bucket: dict[str, list[float]] = {}

    def check_or_raise(self, key: str) -> None:
        now = time.time()
        window_start = now - 60
        values = [v for v in self._bucket.get(key, []) if v >= window_start]
        if len(values) >= self._limit:
            raise HTTPException(
                status_code=429,
                detail={"error": "rate_limited", "message": "Rate limit exceeded. Try again shortly."},
            )
        values.append(now)
        self._bucket[key] = values


class RagChatService:
    def __init__(
        self,
        pdf_service: PdfService,
        embedding_service: EmbeddingService,
        chroma_service: ChromaService,
        retrieval_service: RetrievalService,
        memory_service: MemoryService,
    ):
        self._pdf_service = pdf_service
        self._embedding_service = embedding_service
        self._chroma_service = chroma_service
        self._retrieval_service = retrieval_service
        self._memory_service = memory_service
        self._rate_limiter = _InMemoryRateLimiter()

    async def index_pdf_document(
        self,
        *,
        user: User,
        session_id: uuid.UUID,
        document: Attachment,
    ) -> None:
        self._rate_limiter.check_or_raise(f"upload:{user.id}")

        if document.content_type != "application/pdf":
            raise HTTPException(
                status_code=415,
                detail={"error": "invalid_pdf", "message": "Only PDF files are supported by RAG upload."},
            )

        file_path = Path(document.storage_path)
        max_size_bytes = settings.MAX_PDF_SIZE_MB * 1024 * 1024
        if file_path.stat().st_size > max_size_bytes:
            raise HTTPException(
                status_code=413,
                detail={"error": "pdf_too_large", "message": "PDF exceeds configured max size."},
            )

        pages = self._pdf_service.extract_pages(file_path)
        if not pages:
            raise HTTPException(
                status_code=422,
                detail={"error": "empty_extraction", "message": "Could not extract readable text from PDF."},
            )

        chunks = self._pdf_service.chunk_pages(pages)
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail={"error": "empty_chunks", "message": "No indexable chunks produced from PDF."},
            )

        texts = [chunk.text for chunk in chunks]
        vectors = await self._embedding_service.embed_texts(texts)

        metadatas: list[dict[str, str | int]] = []
        chunk_ids: list[str] = []
        for chunk in chunks:
            chunk_ids.append(f"{document.id}:{chunk.chunk_index}")
            metadatas.append(
                {
                    "document_id": str(document.id),
                    "filename": document.original_name,
                    "page": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                }
            )

        try:
            await self._chroma_service.add_chunks(
                session_id=str(session_id),
                chunk_ids=chunk_ids,
                texts=texts,
                embeddings=vectors,
                metadatas=metadatas,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail={"error": "vector_store_failure", "message": "Failed to index chunks in ChromaDB."},
            ) from exc

    async def chat_with_document(
        self,
        *,
        user: User,
        session_id: uuid.UUID,
        document_id: uuid.UUID,
        message: str,
    ) -> RagChatResult:
        self._rate_limiter.check_or_raise(f"chat:{user.id}")

        chunks = await self._retrieval_service.retrieve(
            session_id=session_id,
            query=message,
        )
        if not chunks:
            raise HTTPException(
                status_code=404,
                detail={"error": "no_context", "message": "No relevant document context found for this query."},
            )

        citations = self._build_citations(chunks)
        context_text = self._build_context(chunks)

        memory_key = f"rag:{user.id}:{session_id}:{document_id}"
        history = await self._memory_service.get_history(memory_key)
        history_lines = [f"{item.role.upper()}: {item.content}" for item in history[-10:]]
        history_text = "\n".join(history_lines) if history_lines else "(none)"

        system_prompt = (
            "You are a document QA assistant. Answer only using the provided document context. "
            "If the answer is not in context, say so clearly. Cite page numbers in your answer."
        )

        human_prompt = (
            f"Conversation history (last 5 exchanges):\n{history_text}\n\n"
            f"Document context:\n{context_text}\n\n"
            f"User question:\n{message}\n\n"
            "Return a concise, grounded answer with page citations."
        )

        try:
            response = await llm.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)],
                config={"metadata": {"user_email": user.email}},
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail={"error": "rag_generation_failed", "message": "Failed to generate RAG response."},
            ) from exc

        text = str(getattr(response, "content", "")).strip()
        if not text:
            text = "No answer could be generated from the document context."

        await self._memory_service.save_message(memory_key, "user", message)
        await self._memory_service.save_message(memory_key, "assistant", text)

        return RagChatResult(response=text, citations=citations)

    @staticmethod
    def _build_context(chunks: list[RetrievedChunk]) -> str:
        lines: list[str] = []
        budget = 12000
        used = 0
        for chunk in chunks:
            page = int(chunk.metadata.get("page", 0))
            filename = str(chunk.metadata.get("filename", "document"))
            snippet = chunk.text.strip()
            block = f"[Source: {filename}, page {page}]\n{snippet}"
            if used + len(block) > budget:
                break
            lines.append(block)
            used += len(block)
        return "\n\n".join(lines)

    @staticmethod
    def _build_citations(chunks: list[RetrievedChunk]) -> list[RagCitation]:
        citations: list[RagCitation] = []
        seen: set[tuple[str, int, int]] = set()
        for chunk in chunks:
            filename = str(chunk.metadata.get("filename", "document"))
            page = int(chunk.metadata.get("page", 0))
            chunk_index = int(chunk.metadata.get("chunk_index", 0))
            key = (filename, page, chunk_index)
            if key in seen:
                continue
            seen.add(key)
            citations.append(RagCitation(filename=filename, page=page, chunk_index=chunk_index))
        return citations


_rag_chat_service_singleton: RagChatService | None = None


def get_rag_chat_service() -> RagChatService:
    global _rag_chat_service_singleton
    if _rag_chat_service_singleton is None:
        _rag_chat_service_singleton = RagChatService(
            pdf_service=get_pdf_service(),
            embedding_service=get_embedding_service(),
            chroma_service=get_chroma_service(),
            retrieval_service=get_retrieval_service(),
            memory_service=get_memory_service(),
        )
    return _rag_chat_service_singleton
