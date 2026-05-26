import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.repositories.document_repository import DocumentRepository, get_document_repository
from app.schemas.rag import RagChatRequest, RagChatResponse, RagUploadResponse
from app.services.attachment_service import AttachmentService, get_attachment_service
from app.services.auth_service import get_current_user
from app.services.rag_chat_service import RagChatService, get_rag_chat_service

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/upload", response_model=RagUploadResponse, status_code=201)
async def rag_upload_pdf(
    session_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    attachment_service: AttachmentService = Depends(get_attachment_service),
    rag_chat_service: RagChatService = Depends(get_rag_chat_service),
) -> RagUploadResponse:
    suffix = Path(file.filename or "").suffix.lower()
    content_type = (file.content_type or "").lower()
    if suffix != ".pdf" or content_type != "application/pdf":
        raise HTTPException(
            status_code=415,
            detail={"error": "invalid_pdf", "message": "Only .pdf files are accepted for RAG upload."},
        )

    attachment = await attachment_service.upload_attachment(
        db,
        user_id=current_user.id,
        session_id=session_id,
        upload=file,
    )

    await rag_chat_service.index_pdf_document(
        user=current_user,
        session_id=session_id,
        document=attachment,
    )

    return RagUploadResponse(
        document_id=attachment.id,
        filename=attachment.original_name,
        status="indexed",
    )


@router.post("/chat", response_model=RagChatResponse)
async def rag_chat(
    body: RagChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    document_repository: DocumentRepository = Depends(get_document_repository),
    rag_chat_service: RagChatService = Depends(get_rag_chat_service),
) -> RagChatResponse:
    document = await document_repository.get_pdf_document(
        db,
        user_id=current_user.id,
        session_id=body.session_id,
        document_id=body.document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "document_not_found", "message": "PDF document not found in this session."},
        )

    result = await rag_chat_service.chat_with_document(
        user=current_user,
        session_id=body.session_id,
        document_id=body.document_id,
        message=body.message,
    )
    return RagChatResponse(response=result.response, citations=result.citations)
