from datetime import datetime
import uuid

from pydantic import BaseModel


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    file_name: str
    original_name: str
    file_url: str
    content_type: str
    file_size: int
    attachment_type: str
    extracted_text: str | None = None
    uploaded_at: datetime


class AttachmentUploadResponse(BaseModel):
    file_id: uuid.UUID
    file_name: str
    original_name: str
    file_url: str
    content_type: str
    file_size: int
    attachment_type: str
    extracted_text: str | None = None
