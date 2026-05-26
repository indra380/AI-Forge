"""Research agent endpoints (ArXiv search, digest generation with streaming)."""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.chat_thread import ChatThread
from app.models.user import User
from app.schemas.research import (
    DigestResult,
    DigestStreamEvent,
    ResearchFollowupRequest,
    ResearchFollowupResponse,
    ResearchMessageItem,
    ResearchQueryRequest,
)
from app.services.chat_service import list_chat_messages, save_chat_message
from app.services.research_digest_agent_service import (
    answer_research_followup,
    generate_research_digest,
    search_research_papers,
)
from app.services.thread_service import get_thread, get_thread_type, touch_thread

logger = get_logger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


async def event_stream_generator(
    *,
    db: AsyncSession,
    thread: ChatThread,
    thread_id: UUID,
    user_id: UUID,
    query: str,
    user_email: str,
    max_papers: int,
) -> AsyncGenerator[str, None]:
    """Generate Server-Sent Events for research digest."""
    try:
        logger.info("[RESEARCH_AGENT] stream start thread_id=%s query=%r", thread_id, query)
        # Start event
        start_event = DigestStreamEvent(
            type="searching", message=f"Searching ArXiv for: {query}", papers_found=0
        )
        yield f"data: {json.dumps(start_event.model_dump(mode='json'))}\n\n"

        # Fetch papers first so UI can render them immediately.
        preloaded = await search_research_papers(query, max_papers=max_papers)
        preview_papers = [
            {
                "arxiv_id": p.get("arxiv_id", ""),
                "title": p.get("title", "Untitled"),
                "authors": p.get("authors", []),
                "published": p.get("published", ""),
                "url": p.get("url", ""),
                "summary": str(p.get("summary", ""))[:520],
            }
            for p in list(preloaded.get("papers_payload", []))[:10]
        ]
        papers_event = {
            "type": "papers",
            "message": f"Found {len(preview_papers)} papers",
            "papers_found": len(preview_papers),
            "thread_id": str(thread_id),
            "query": query,
            "papers": preview_papers,
        }
        yield f"data: {json.dumps(papers_event)}\n\n"

        # Generate digest from preloaded search results.
        result = await generate_research_digest(query, user_email, max_papers, preloaded=preloaded)
        logger.info("[RESEARCH_AGENT] stream digest generated thread_id=%s papers=%s", thread_id, len(result.get("papers", [])))

        # Analyzing event
        analyzing_event = DigestStreamEvent(
            type="analyzing",
            message=f"Found {len(result['papers'])} relevant papers. Analyzing...",
            papers_found=len(result["papers"]),
        )
        yield f"data: {json.dumps(analyzing_event.model_dump(mode='json'))}\n\n"

        # Complete event with result
        digest = DigestResult(
            thread_id=thread_id,
            query=result["query"],
            summary=result["summary"],
            summary_display=result.get("summary_display"),
            papers=result["papers"],
            trends=result["trends"],
            keywords=result.get("keywords", []),
            key_findings=result.get("key_findings"),
            consensus_view=result.get("consensus_view"),
            open_questions=result.get("open_questions"),
            confidence=result.get("confidence"),
            synthesis=result["synthesis"],
            total_papers_analyzed=len(result["papers"]),
        )

        # Persist the assistant digest response and research context in thread JSON.
        assistant_text = (
            f"Research Digest for: {result['query']}\n\n"
            f"Summary:\n{result['summary']}\n\n"
            f"Trends: {', '.join(result['trends']) if result['trends'] else 'N/A'}\n\n"
            f"Synthesis:\n{result['synthesis']}"
        )
        await save_chat_message(
            db,
            user_id,
            thread_id,
            "assistant",
            assistant_text,
            commit=False,
            refresh=False,
        )
        logger.info("[RESEARCH_AGENT] stream saved assistant digest message thread_id=%s", thread_id)

        ctx = dict(thread.context or {})
        ctx["research"] = {
            "query": result["query"],
            "summary": result["summary"],
            "summary_display": result.get("summary_display"),
            "papers": result["papers"],
            "trends": result["trends"],
            "keywords": result.get("keywords", []),
            "key_findings": result.get("key_findings"),
            "consensus_view": result.get("consensus_view"),
            "open_questions": result.get("open_questions"),
            "confidence": result.get("confidence"),
            "synthesis": result["synthesis"],
        }
        thread.context = ctx
        await touch_thread(db, thread, commit=False)
        await db.commit()

        complete_event = DigestStreamEvent(type="complete", message="Digest generation complete")
        yield f"data: {json.dumps(complete_event.model_dump(mode='json'))}\n\n"
        yield f"data: {json.dumps(digest.model_dump(mode='json'))}\n\n"
        logger.info("[RESEARCH_AGENT] stream complete thread_id=%s", thread_id)
    except Exception as e:
        logger.exception("Error in research digest stream")
        error_event = DigestStreamEvent(type="error", message=f"Error: {str(e)}")
        yield f"data: {json.dumps(error_event.model_dump(mode='json'))}\n\n"


@router.post("/digest")
async def start_research_digest(
    request: ResearchQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Start research digest generation with streaming results.

    Streams Server-Sent Events containing:
    1. "searching" - Starting search
    2. "analyzing" - Found papers
    3. "complete" - Digest ready
    4. Final DigestResult as JSON
    """
    thread: ChatThread | None = None
    if request.thread_id is not None:
        thread_type = await get_thread_type(db, request.thread_id, current_user.id)
        if thread_type != "research":
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Research thread not found"},
            )
        thread = await get_thread(db, request.thread_id, current_user.id)

    if thread is None:
        thread = ChatThread(user_id=current_user.id, type="research", title=request.query[:120])
        db.add(thread)
        await db.commit()
        await db.refresh(thread)
        logger.info("[RESEARCH_AGENT] created new research thread thread_id=%s user_id=%s", thread.id, current_user.id)

    await save_chat_message(db, current_user.id, thread.id, "user", request.query)
    logger.info("[RESEARCH_AGENT] saved user research query thread_id=%s", thread.id)

    return StreamingResponse(
        event_stream_generator(
            db=db,
            thread=thread,
            thread_id=thread.id,
            user_id=current_user.id,
            query=request.query,
            user_email=current_user.email,
            max_papers=request.max_papers,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/threads/{thread_id}/messages", response_model=list[ResearchMessageItem])
async def get_research_messages(
    thread_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ResearchMessageItem]:
    thread_type = await get_thread_type(db, thread_id, current_user.id)
    if thread_type != "research":
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Research thread not found"},
        )
    messages = await list_chat_messages(db, current_user.id, thread_id)
    return [ResearchMessageItem.model_validate(m, from_attributes=True) for m in messages]


@router.post("/threads/{thread_id}/ask", response_model=ResearchFollowupResponse)
async def ask_research_followup(
    thread_id: UUID,
    body: ResearchFollowupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResearchFollowupResponse:
    thread = await get_thread(db, thread_id, current_user.id)
    if thread is None or thread.type != "research":
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Research thread not found"},
        )

    research_ctx = (thread.context or {}).get("research") or {}
    digest_summary = str(research_ctx.get("summary") or "")
    papers = list(research_ctx.get("papers") or [])
    trends = [str(t) for t in list(research_ctx.get("trends") or [])]
    synthesis = str(research_ctx.get("synthesis") or "")

    await save_chat_message(db, current_user.id, thread_id, "user", body.question)
    logger.info("[RESEARCH_AGENT] followup saved user message thread_id=%s", thread_id)
    history_rows = await list_chat_messages(db, current_user.id, thread_id)
    chat_history = [{"role": m.role, "content": m.content} for m in history_rows]

    answer = await answer_research_followup(
        question=body.question,
        user_email=current_user.email,
        digest_summary=digest_summary,
        key_papers=papers,
        trends=trends,
        synthesis=synthesis,
        chat_history=chat_history,
    )

    await save_chat_message(db, current_user.id, thread_id, "assistant", answer)
    await touch_thread(db, thread)
    logger.info("[RESEARCH_AGENT] followup saved assistant message thread_id=%s", thread_id)

    return ResearchFollowupResponse(thread_id=thread_id, answer=answer)
