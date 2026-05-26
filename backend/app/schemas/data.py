"""Pydantic schemas for the /api/data endpoints."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class DatasetUploadResponse(BaseModel):
    dataset_id: str
    filename: str
    rows: int
    columns: int
    sheets: list[str]


# ---------------------------------------------------------------------------
# Google Sheet connection
# ---------------------------------------------------------------------------

class GoogleSheetRequest(BaseModel):
    google_sheet_url: str
    worksheet_name: Optional[str] = None

    @field_validator("google_sheet_url")
    @classmethod
    def must_be_sheets_url(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("google_sheet_url must not be empty")
        return v.strip()


class GoogleSheetResponse(BaseModel):
    dataset_id: str
    sheet_title: str
    rows: int
    columns: int
    sheets: list[str]


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

class DataQueryRequest(BaseModel):
    dataset_id: str
    question: str
    sheet_name: Optional[str] = None
    history: Optional[list[dict]] = None   # [{"role": "human"|"ai", "content": "..."}]

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be empty")
        return v.strip()


class DataQueryResponse(BaseModel):
    answer: str
    code: str = ""
    data_summary: str = ""
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Dataset list / info
# ---------------------------------------------------------------------------

class DatasetInfo(BaseModel):
    dataset_id: str
    filename: str
    rows: int
    columns: int
    sheets: list[str]
    created_at: str
    source_url: Optional[str] = None


class DatasetListResponse(BaseModel):
    datasets: list[DatasetInfo]
