from datetime import datetime
import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)


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

