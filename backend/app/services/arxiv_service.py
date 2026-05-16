"""ArXiv search and paper retrieval tools for research agent."""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Optional

import arxiv
from app.core.logging import get_logger

logger = get_logger(__name__)

_SEARCH_CACHE_TTL_SECONDS = 300
_SEARCH_CACHE: dict[tuple[str, int, str], tuple[float, list["PaperInfo"]]] = {}


def _build_client(*, page_size: int) -> arxiv.Client:
    # Faster defaults with bounded retries. Combined with fallback sizes below,
    # this keeps end-to-end latency lower while still handling transient throttling.
    return arxiv.Client(page_size=page_size, delay_seconds=1.0, num_retries=2)


def _looks_like_rate_limit(exc: Exception) -> bool:
    return "HTTP 429" in str(exc)


def _result_to_paper(result: arxiv.Result) -> PaperInfo:
    short_id = result.get_short_id()
    source_url = getattr(result, "entry_id", None) or getattr(result, "source_url", "")
    arxiv_url = source_url.replace("http://", "https://") if source_url else ""
    return PaperInfo(
        arxiv_id=short_id,
        title=result.title,
        authors=[author.name for author in result.authors],
        published=result.published.isoformat(),
        summary=result.summary.replace("\n", " ").strip(),
        url=arxiv_url,
        pdf_url=result.pdf_url,
        categories=result.categories,
    )


@dataclass
class PaperInfo:
    """Structured paper metadata."""

    arxiv_id: str
    title: str
    authors: list[str]
    published: str
    summary: str
    url: str
    pdf_url: str
    categories: list[str]


def search_papers(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
) -> list[PaperInfo]:
    """Search ArXiv for papers matching the query.

    Args:
        query: Search query (e.g. "machine learning", "neural networks")
        max_results: Max papers to return
        sort_by: "relevance", "lastUpdatedDate", or "submittedDate"

    Returns:
        List of PaperInfo objects
    """
    normalized_max = max(1, int(max_results))
    cache_key = (query.strip().lower(), normalized_max, sort_by)
    cached = _SEARCH_CACHE.get(cache_key)
    now = time.monotonic()
    if cached is not None:
        cached_at, cached_papers = cached
        if now - cached_at <= _SEARCH_CACHE_TTL_SECONDS:
            logger.info(
                "[RESEARCH_AGENT] arxiv.search cache_hit query=%r max_results=%s sort_by=%s returned=%s",
                query,
                normalized_max,
                sort_by,
                len(cached_papers),
            )
            return list(cached_papers)

    page_size = min(max(5, normalized_max), 25)
    client = _build_client(page_size=page_size)
    logger.info("[RESEARCH_AGENT] arxiv.search start query=%r max_results=%s sort_by=%s", query, max_results, sort_by)

    # Map string sort_by to arxiv.SortCriterion enum
    sort_map = {
        "relevance": arxiv.SortCriterion.Relevance,
        "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
        "submittedDate": arxiv.SortCriterion.SubmittedDate,
    }
    sort_criterion = sort_map.get(sort_by, arxiv.SortCriterion.Relevance)

    # If ArXiv throttles, progressively lower result count only (never increase).
    attempted_sizes = [normalized_max]
    for candidate in (15, 10, 5):
        if candidate < normalized_max:
            attempted_sizes.append(candidate)
    for size in attempted_sizes:
        try:
            results = client.results(
                arxiv.Search(
                    query=query,
                    max_results=size,
                    sort_by=sort_criterion,
                )
            )

            papers: list[PaperInfo] = []
            for paper in results:
                papers.append(_result_to_paper(paper))

            logger.info(
                "[RESEARCH_AGENT] arxiv.search success query=%r fetched=%s requested=%s",
                query,
                len(papers),
                size,
            )
            _SEARCH_CACHE[cache_key] = (time.monotonic(), list(papers))
            if papers:
                logger.info(
                    "[RESEARCH_AGENT] arxiv.search sample_titles=%s",
                    [p.title for p in papers[:3]],
                )
            return papers
        except Exception as exc:
            if _looks_like_rate_limit(exc):
                logger.warning(
                    "[RESEARCH_AGENT] arxiv.search rate_limited query=%r requested=%s; trying smaller batch",
                    query,
                    size,
                )
                continue
            logger.exception("ArXiv search failed for query=%s requested=%s", query, size)
            return []

    logger.error("[RESEARCH_AGENT] arxiv.search exhausted retries query=%r", query)
    return []


def get_paper_details(arxiv_id: str) -> Optional[PaperInfo]:
    """Retrieve full details for a single paper by ArXiv ID."""
    client = _build_client()
    logger.info("[RESEARCH_AGENT] arxiv.details start id=%s", arxiv_id)
    try:
        results = list(
            client.results(
                arxiv.Search(
                    id_list=[arxiv_id.replace("arXiv:", "").strip()],
                    max_results=1,
                )
            )
        )
        if not results:
            return None
        paper = results[0]
        details = _result_to_paper(paper)
        logger.info("[RESEARCH_AGENT] arxiv.details success id=%s title=%r", details.arxiv_id, details.title)
        return details
    except Exception as exc:
        logger.exception("Failed to fetch paper details for id=%s", arxiv_id)
        return None
