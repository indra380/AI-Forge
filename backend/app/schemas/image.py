from datetime import datetime
import uuid

from pydantic import BaseModel, Field


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)
    size: str = Field(default="1024x1024")
    style: str = Field(default="realistic")
    thread_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    negative_prompt: str | None = Field(default=None, max_length=1000)
    seed: int | None = None
    image_count: int = Field(default=1, ge=1, le=4)


class GeneratedImageResponse(BaseModel):
    image_id: uuid.UUID
    session_id: uuid.UUID
    prompt: str
    provider: str
    style: str
    size: str
    image_url: str
    created_at: datetime


class ImageGenerateResponse(BaseModel):
    image_url: str
    prompt: str
    images: list[GeneratedImageResponse] = Field(default_factory=list)
    assistant_message: str | None = None
