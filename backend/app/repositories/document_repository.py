from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment


class DocumentRepository:
    async def get_pdf_document(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> Attachment | None:
        stmt = select(Attachment).where(
            Attachment.id == document_id,
            Attachment.user_id == user_id,
            Attachment.session_id == session_id,
            Attachment.attachment_type == "document",
            Attachment.content_type == "application/pdf",
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


_document_repository_singleton: DocumentRepository | None = None


def get_document_repository() -> DocumentRepository:
    global _document_repository_singleton
    if _document_repository_singleton is None:
        _document_repository_singleton = DocumentRepository()
    return _document_repository_singleton
