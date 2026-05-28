from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.research_paper import ResearchPaper


async def save_research_papers(
    db: AsyncSession,
    user_id: uuid.UUID,
    thread_id: uuid.UUID,
    query: str,
    papers: list[dict[str, Any]],
) -> None:
    """Persist research paper links and summaries for the current digest run."""
    for paper in papers:
        row = ResearchPaper(
            user_id=user_id,
            thread_id=thread_id,
            query=query,
            arxiv_id=str(paper.get("arxiv_id") or ""),
            title=str(paper.get("title") or "Untitled"),
            authors=[str(a) for a in list(paper.get("authors") or [])],
            published=str(paper.get("published") or ""),
            url=str(paper.get("url") or ""),
            summary=str(paper.get("summary") or ""),
        )
        db.add(row)
