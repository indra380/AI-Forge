from datetime import datetime
import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    session_id: uuid.UUID | None = None
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)


class UnifiedChatMessageRequest(ChatRequest):
    thread_id: uuid.UUID


class ChatResponse(BaseModel):
    answer: str


class ChatHistoryItem(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class ThreadCreate(BaseModel):
    title: str = Field(default="New Chat", max_length=255)


class ThreadUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ThreadResponse(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size: int
    is_indexed: bool
    file_url: str | None = None
    attachment_type: str | None = None


class TicTacToeMoveRequest(BaseModel):
    position: int = Field(ge=1, le=9)


class TicTacToeStateResponse(BaseModel):
    active: bool
    board: list[str]
    winner: str | None = None
    move_count: int = 0
    message: str | None = None

