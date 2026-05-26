from datetime import datetime
import uuid

from pydantic import BaseModel, Field


class RagUploadResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    status: str


class RagCitation(BaseModel):
    page: int
    filename: str
    chunk_index: int


class RagChatRequest(BaseModel):
    session_id: uuid.UUID
    document_id: uuid.UUID
    message: str = Field(min_length=1, max_length=8000)


class RagChatResponse(BaseModel):
    response: str
    citations: list[RagCitation] = Field(default_factory=list)


class DocumentCard(BaseModel):
    document_id: uuid.UUID
    filename: str
    uploaded_at: datetime
