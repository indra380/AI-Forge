"""Pydantic schemas for research endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ResearchQueryRequest(BaseModel):
    """Request to start a research digest."""

    query: str = Field(..., min_length=1, max_length=500, description="Research topic/question")
    max_papers: int | None = Field(
        12, ge=5, le=30, description="Maximum papers to analyze (default 12)"
    )
    thread_id: UUID | None = Field(
        default=None,
        description="Existing research thread id for continuing the same conversation",
    )


class PaperReference(BaseModel):
    """Reference to a research paper."""

    arxiv_id: str = Field(..., description="ArXiv paper ID (e.g., 2301.12345)")
    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(..., description="List of author names")
    published: str = Field(..., description="Publication date (ISO format)")
    url: str = Field(..., description="URL to paper on ArXiv")
    summary: str = Field(..., description="Paper abstract/summary (truncated)")


class DigestStreamEvent(BaseModel):
    """Event streamed during digest generation."""

    type: str = Field(
        ..., description="Event type: 'searching', 'analyzing', 'complete', 'error'"
    )
    message: str = Field(..., description="Human-readable message")
    papers_found: Optional[int] = Field(None, description="Number of papers found so far")
    current_paper: Optional[PaperReference] = Field(None, description="Paper being analyzed")


class DigestResult(BaseModel):
    """Final research digest."""

    thread_id: UUID = Field(..., description="Research thread id")
    query: str = Field(..., description="Original research query")
    summary: str = Field(..., description="Main digest text")
    summary_display: str | None = Field(
        None,
        description="Clean summary text for UI display",
    )
    papers: list[PaperReference] = Field(..., description="Key papers referenced")
    trends: list[str] = Field(..., description="Identified research trends")
    keywords: list[str] | None = Field(None, description="Extracted key terms")
    key_findings: str | None = Field(None, description="Detailed key findings")
    consensus_view: str | None = Field(None, description="Field consensus narrative")
    open_questions: str | None = Field(None, description="Open questions and challenges")
    confidence: dict | None = Field(None, description="Confidence assessment details")
    synthesis: str = Field(..., description="High-level insights and synthesis")
    total_papers_analyzed: int = Field(..., description="Total papers examined")


class ResearchFollowupRequest(BaseModel):
    """Follow-up question inside a research thread."""

    question: str = Field(..., min_length=1, max_length=6000)


class ResearchFollowupResponse(BaseModel):
    """Assistant reply for a research follow-up question."""

    thread_id: UUID
    answer: str


class ResearchMessageItem(BaseModel):
    """Research chat history item."""

    id: UUID
    role: str
    content: str
    created_at: datetime
