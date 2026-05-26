"""MCP-backed arXiv search and paper retrieval tools for research agent."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
import shlex
import time
from typing import Any, Optional

import arxiv
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_SEARCH_CACHE_TTL_SECONDS = 300
_SEARCH_CACHE: dict[tuple[str, int, str], tuple[float, list["PaperInfo"]]] = {}
_MCP_TOOL_CACHE: dict[str, str] = {}
_MCP_TOOL_CACHE_LOCK = asyncio.Lock()
_LAST_SEARCH_DIAGNOSTIC: str = ""
_RATE_LIMIT_COOLDOWN_SECONDS = 60
_ARXIV_RATE_LIMITED_UNTIL: float = 0.0
_MCP_HTTP_FAILURE_COOLDOWN_SECONDS = 30
_MCP_HTTP_UNAVAILABLE_UNTIL: float = 0.0
_DIRECT_ARXIV_FAILURE_COOLDOWN_SECONDS = 30
_ARXIV_DIRECT_UNAVAILABLE_UNTIL: float = 0.0


def _set_last_search_diagnostic(message: str) -> None:
    global _LAST_SEARCH_DIAGNOSTIC
    _LAST_SEARCH_DIAGNOSTIC = message.strip()


def get_last_search_diagnostic() -> str:
    return _LAST_SEARCH_DIAGNOSTIC


def _is_rate_limit_error(value: Any) -> bool:
    lowered = str(value).lower()
    markers = (
        "429",
        "rate limit",
        "rate-limit",
        "rate limiting",
        "too many requests",
    )
    return any(marker in lowered for marker in markers)


def _mark_rate_limited(*, reason: str) -> None:
    global _ARXIV_RATE_LIMITED_UNTIL
    _ARXIV_RATE_LIMITED_UNTIL = time.monotonic() + _RATE_LIMIT_COOLDOWN_SECONDS
    _set_last_search_diagnostic(reason)


def _mark_mcp_http_unavailable(*, reason: str) -> None:
    global _MCP_HTTP_UNAVAILABLE_UNTIL
    _MCP_HTTP_UNAVAILABLE_UNTIL = time.monotonic() + _MCP_HTTP_FAILURE_COOLDOWN_SECONDS
    logger.info("[RESEARCH_AGENT] mcp_http.search cooldown_start reason=%s", reason)


def _mark_direct_arxiv_unavailable(*, reason: str) -> None:
    global _ARXIV_DIRECT_UNAVAILABLE_UNTIL
    _ARXIV_DIRECT_UNAVAILABLE_UNTIL = time.monotonic() + _DIRECT_ARXIV_FAILURE_COOLDOWN_SECONDS
    logger.info("[RESEARCH_AGENT] direct_arxiv.search cooldown_start reason=%s", reason)

def _rate_limit_fallback_results(query: str, max_results: int) -> list[PaperInfo]:
    if settings.ARXIV_USE_MOCK_ON_RATE_LIMIT:
        return _mock_papers_for_query(query, max_results)
    return []

def _tool_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        return _to_text_payload(payload.get("content"))
    return _to_text_payload(getattr(payload, "content", None))


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


def _build_stdio_params() -> StdioServerParameters:
    command = settings.ARXIV_MCP_COMMAND
    if os.name == "nt" and command.lower() == "npx":
        command = "npx.cmd"
    args = shlex.split(settings.ARXIV_MCP_ARGS)
    return StdioServerParameters(command=command, args=args)


def _to_text_payload(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
                    continue
            text_attr = getattr(item, "text", None)
            if isinstance(text_attr, str):
                parts.append(text_attr)
        return "\n".join(parts)
    return str(content)


def _decode_tool_result(result: Any) -> Any:
    """Decode MCP tool results from structured or text payloads."""
    if isinstance(result, dict):
        # isError means the tool reported a failure; return empty so fallback triggers
        if result.get("isError"):
            logger.warning("[RESEARCH_AGENT] mcp_tool returned isError: %s", result.get("content"))
            return {}
        if "structuredContent" in result and result["structuredContent"] is not None:
            return result["structuredContent"]
        if "content" in result:
            return _parse_payload(_to_text_payload(result["content"]))
        return result

    # Pydantic MCP result object
    is_err = getattr(result, "isError", False)
    if is_err:
        logger.warning("[RESEARCH_AGENT] mcp_tool returned isError: %s", getattr(result, "content", None))
        return {}

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured

    content = getattr(result, "content", None)
    if content is not None:
        return _parse_payload(_to_text_payload(content))

    return _parse_payload(_to_text_payload(result))


def _parse_payload(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {"papers": []}


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _as_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _as_categories(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _paper_from_entry(entry: dict[str, Any]) -> PaperInfo:
    arxiv_id = _as_str(
        entry.get("arxiv_id")
        or entry.get("id")
        or entry.get("paper_id")
    )
    title = _as_str(entry.get("title") or "Untitled")
    authors = _as_authors(entry.get("authors"))
    published = _as_str(entry.get("published") or entry.get("published_date") or entry.get("updated"))
    summary = _as_str(entry.get("summary") or entry.get("abstract"))
    url = _as_str(entry.get("url") or entry.get("entry_id") or entry.get("link"))
    pdf_url = _as_str(entry.get("pdf_url") or entry.get("pdf"))
    categories = _as_categories(entry.get("categories") or entry.get("tags"))
    return PaperInfo(
        arxiv_id=arxiv_id,
        title=title,
        authors=authors,
        published=published,
        summary=summary,
        url=url,
        pdf_url=pdf_url,
        categories=categories,
    )


def _papers_from_payload(payload: Any) -> list[PaperInfo]:
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        payload = payload["result"]

    if isinstance(payload, list):
        raw_list = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("papers"), list):
            raw_list = payload["papers"]
        elif isinstance(payload.get("results"), list):
            raw_list = payload["results"]
        elif isinstance(payload.get("search_results"), list):
            raw_list = payload["search_results"]
        elif isinstance(payload.get("items"), list):
            raw_list = payload["items"]
        elif isinstance(payload.get("data"), list):
            raw_list = payload["data"]
        elif isinstance(payload.get("data"), dict):
            nested = payload["data"]
            if isinstance(nested.get("papers"), list):
                raw_list = nested["papers"]
            elif isinstance(nested.get("results"), list):
                raw_list = nested["results"]
            else:
                raw_list = []
        else:
            raw_list = []
    else:
        raw_list = []

    papers: list[PaperInfo] = []
    for item in raw_list:
        if isinstance(item, dict):
            papers.append(_paper_from_entry(item))
    return papers


def _sort_criterion(sort_by: str) -> arxiv.SortCriterion:
    lowered = sort_by.lower().strip()
    if lowered in {"submitteddate", "submitted_date", "date"}:
        return arxiv.SortCriterion.SubmittedDate
    if lowered in {"lastupdateddate", "last_updated", "updated"}:
        return arxiv.SortCriterion.LastUpdatedDate
    return arxiv.SortCriterion.Relevance


def _paper_from_result(result: arxiv.Result) -> PaperInfo:
    categories: list[str] = []
    if isinstance(result.categories, list):
        categories = [str(cat) for cat in result.categories]
    return PaperInfo(
        arxiv_id=result.get_short_id(),
        title=_as_str(result.title),
        authors=[_as_str(author) for author in result.authors],
        published=result.published.isoformat() if result.published else "",
        summary=_as_str(result.summary),
        url=_as_str(result.entry_id),
        pdf_url=_as_str(result.pdf_url),
        categories=categories,
    )


def _fallback_search_sync(query: str, max_results: int, sort_by: str) -> list[PaperInfo]:
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=_sort_criterion(sort_by),
    )
    client = arxiv.Client(page_size=min(max_results, 100), delay_seconds=0.0)
    papers: list[PaperInfo] = []
    for result in client.results(search):
        papers.append(_paper_from_result(result))
    return papers


def _mock_papers_for_query(query: str, max_results: int) -> list[PaperInfo]:
    """Return mock papers for development when ArXiv is unavailable."""
    mock_data = {
        "bilstm": [
            PaperInfo(
                arxiv_id="2310.12345",
                title="Bidirectional LSTM for Sentiment Analysis in Social Media",
                authors=["Alice Chen", "Bob Smith", "Carol Johnson"],
                published="2023-10-15",
                summary="This paper presents a novel application of BiLSTM networks to sentiment analysis tasks on social media platforms, achieving state-of-the-art results on benchmark datasets.",
                url="https://arxiv.org/abs/2310.12345",
                pdf_url="https://arxiv.org/pdf/2310.12345.pdf",
                categories=["cs.CL", "cs.LG"],
            ),
            PaperInfo(
                arxiv_id="2309.54321",
                title="Improving BiLSTM Performance with Attention Mechanisms",
                authors=["David Lee", "Emma Davis"],
                published="2023-09-20",
                summary="We propose an attention-based enhancement to traditional BiLSTM architectures, demonstrating significant improvements on sequence labeling tasks.",
                url="https://arxiv.org/abs/2309.54321",
                pdf_url="https://arxiv.org/pdf/2309.54321.pdf",
                categories=["cs.LG", "cs.NE"],
            ),
            PaperInfo(
                arxiv_id="2308.98765",
                title="BiLSTM-CRF for Named Entity Recognition in Biomedical Texts",
                authors=["Frank Wilson", "Grace Lee", "Henry Zhang"],
                published="2023-08-10",
                summary="A comprehensive study on using BiLSTM combined with CRF layers for named entity recognition in biomedical literature, outperforming baseline methods.",
                url="https://arxiv.org/abs/2308.98765",
                pdf_url="https://arxiv.org/pdf/2308.98765.pdf",
                categories=["cs.CL", "q-bio.QM"],
            ),
        ],
        "transformer": [
            PaperInfo(
                arxiv_id="2306.11111",
                title="Efficient Transformers: A Survey",
                authors=["Ivan Brown", "Iris Martinez"],
                published="2023-06-05",
                summary="A comprehensive survey of efficient transformer architectures and techniques to reduce computational complexity while maintaining model performance.",
                url="https://arxiv.org/abs/2306.11111",
                pdf_url="https://arxiv.org/pdf/2306.11111.pdf",
                categories=["cs.LG", "cs.CL"],
            ),
        ],
        "attention": [
            PaperInfo(
                arxiv_id="2305.22222",
                title="Multi-Head Attention Variants and Their Applications",
                authors=["Jack Robinson", "Julie Anderson"],
                published="2023-05-12",
                summary="Exploration of different multi-head attention variants and their effectiveness across various NLP and computer vision tasks.",
                url="https://arxiv.org/abs/2305.22222",
                pdf_url="https://arxiv.org/pdf/2305.22222.pdf",
                categories=["cs.LG", "cs.CV"],
            ),
        ],
        "5g": [
            PaperInfo(
                arxiv_id="2403.10001",
                title="Resource Allocation for 5G V2V Communications: A Survey",
                authors=["Nikhil Rao", "Priya Menon"],
                published="2024-03-10",
                summary="This survey reviews spectrum sharing, latency constraints, and reliability targets for 5G V2V communication systems with emphasis on safety-critical traffic.",
                url="https://arxiv.org/abs/2403.10001",
                pdf_url="https://arxiv.org/pdf/2403.10001.pdf",
                categories=["cs.NI", "eess.SP"],
            ),
            PaperInfo(
                arxiv_id="2402.20002",
                title="Low-Latency Scheduling in 5G NR for Vehicle-to-Vehicle Links",
                authors=["Arjun Patel", "Mina Hassan", "Luis Ortega"],
                published="2024-02-22",
                summary="The paper studies low-latency MAC scheduling policies for 5G NR sidelink and analyzes trade-offs between throughput, reliability, and packet deadline miss ratio.",
                url="https://arxiv.org/abs/2402.20002",
                pdf_url="https://arxiv.org/pdf/2402.20002.pdf",
                categories=["cs.NI", "cs.IT"],
            ),
            PaperInfo(
                arxiv_id="2312.30003",
                title="Joint Power Control and Mode Selection for 5G V2V Networks",
                authors=["Yuna Kim", "Rahul Singh"],
                published="2023-12-05",
                summary="A joint optimization framework for cellular and sidelink mode selection with adaptive power control in dense urban 5G V2V scenarios.",
                url="https://arxiv.org/abs/2312.30003",
                pdf_url="https://arxiv.org/pdf/2312.30003.pdf",
                categories=["cs.NI", "math.OC"],
            ),
        ],
    }

    # Try to match query to mock data; do not force unrelated defaults.
    query_lower = query.lower()
    matching_category = None
    for key in mock_data:
        if key in query_lower:
            matching_category = key
            break

    if matching_category is None:
        return []

    papers = mock_data.get(matching_category, [])
    return papers[:max_results]


async def _fallback_search(query: str, max_results: int, sort_by: str) -> list[PaperInfo]:
    logger.warning("[RESEARCH_AGENT] mcp.arxiv.search fallback=python-arxiv query=%r", query)
    try:
        papers = await asyncio.wait_for(
            asyncio.to_thread(_fallback_search_sync, query, max_results, sort_by),
            timeout=max(1, settings.ARXIV_DIRECT_TIMEOUT_SECONDS),
        )
        _set_last_search_diagnostic("")
        return papers
    except TimeoutError:
        _mark_direct_arxiv_unavailable(reason="timeout")
        _set_last_search_diagnostic("Direct ArXiv API timed out. Try again shortly.")
        logger.warning("[RESEARCH_AGENT] fallback arxiv search timeout query=%r", query)
        return []
    except arxiv.HTTPError as exc:
        status_hint = ""
        if "HTTP 429" in str(exc):
            status_hint = (
                "ArXiv API is rate-limiting this environment (HTTP 429). "
                "No synthetic papers will be shown. Try again in ~1 minute for live results."
            )
            logger.warning("[RESEARCH_AGENT] fallback arxiv search rate_limited query=%r", query)
            _mark_rate_limited(reason=status_hint)
            return _rate_limit_fallback_results(query, max_results)
        _mark_direct_arxiv_unavailable(reason="http_error")
        _set_last_search_diagnostic(status_hint or f"ArXiv request failed: {exc}")
        logger.exception("[RESEARCH_AGENT] fallback arxiv search http_error query=%r", query)
        return []
    except Exception as exc:
        if _is_rate_limit_error(exc):
            status_hint = (
                "ArXiv API is rate-limiting this environment (HTTP 429). "
                "No synthetic papers will be shown. Try again in ~1 minute for live results."
            )
            logger.warning("[RESEARCH_AGENT] fallback arxiv search rate_limited query=%r", query)
            _mark_rate_limited(reason=status_hint)
            return _rate_limit_fallback_results(query, max_results)
        _mark_direct_arxiv_unavailable(reason="exception")
        _set_last_search_diagnostic("ArXiv search failed due to a temporary backend error.")
        logger.exception("[RESEARCH_AGENT] fallback arxiv search failed query=%r", query)
        return []


async def _fallback_details(arxiv_id: str) -> Optional[PaperInfo]:
    papers = await _fallback_search(f"id:{arxiv_id}", 1, "relevance")
    if papers:
        return papers[0]
    return None


async def _mcp_http_search(query: str, max_results: int, sort_by: str) -> list[PaperInfo]:
    """Search via HTTP Streamable MCP server."""
    url = settings.ARXIV_MCP_HTTP_URL
    if not url:
        return []
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_name = await _resolve_tool_name(session, role="search")
            if not tool_name:
                logger.error("[RESEARCH_AGENT] mcp_http missing_search_tool")
                return []
            for arguments in [
                {"query": query, "max_results": max_results, "sort_by": sort_by},
                {"query": query, "maxResults": max_results, "sortBy": sort_by},
            ]:
                payload = await session.call_tool(tool_name, arguments)
                is_error = payload.get("isError") if isinstance(payload, dict) else getattr(payload, "isError", False)
                if is_error:
                    error_text = _tool_error_message(payload)
                    if _is_rate_limit_error(error_text):
                        raise RuntimeError(error_text or "arXiv rate limited")
                decoded = _decode_tool_result(payload)
                papers = _papers_from_payload(decoded)
                if papers:
                    return papers
    return []


async def _mcp_http_details(arxiv_id: str) -> Optional[PaperInfo]:
    """Fetch paper details via HTTP Streamable MCP server."""
    url = settings.ARXIV_MCP_HTTP_URL
    if not url:
        return None
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_name = await _resolve_tool_name(session, role="details") or await _resolve_tool_name(session, role="search")
            if not tool_name:
                return None
            payload = await session.call_tool(tool_name, {"arxiv_id": arxiv_id, "paper_id": arxiv_id, "query": f"id:{arxiv_id}", "max_results": 1})
            decoded = _decode_tool_result(payload)
            papers = _papers_from_payload(decoded)
            return papers[0] if papers else None


async def _mcp_sse_search(query: str, max_results: int, sort_by: str) -> list[PaperInfo]:
    """Search via SSE MCP server."""
    url = settings.ARXIV_MCP_SSE_URL
    if not url:
        return []
    async with sse_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_name = await _resolve_tool_name(session, role="search")
            if not tool_name:
                logger.error("[RESEARCH_AGENT] mcp_sse missing_search_tool")
                return []
            for arguments in [
                {"query": query, "max_results": max_results, "sort_by": sort_by},
                {"query": query, "maxResults": max_results, "sortBy": sort_by},
            ]:
                payload = await session.call_tool(tool_name, arguments)
                is_error = payload.get("isError") if isinstance(payload, dict) else getattr(payload, "isError", False)
                if is_error:
                    error_text = _tool_error_message(payload)
                    if _is_rate_limit_error(error_text):
                        raise RuntimeError(error_text or "arXiv rate limited")
                decoded = _decode_tool_result(payload)
                papers = _papers_from_payload(decoded)
                if papers:
                    return papers
    return []


async def _mcp_sse_details(arxiv_id: str) -> Optional[PaperInfo]:
    """Fetch paper details via SSE MCP server."""
    url = settings.ARXIV_MCP_SSE_URL
    if not url:
        return None
    async with sse_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tool_name = await _resolve_tool_name(session, role="details") or await _resolve_tool_name(session, role="search")
            if not tool_name:
                return None
            payload = await session.call_tool(tool_name, {
                "arxiv_id": arxiv_id,
                "paper_id": arxiv_id,
                "query": f"id:{arxiv_id}",
                "max_results": 1,
                "maxResults": 1,
            })
            decoded = _decode_tool_result(payload)
            papers = _papers_from_payload(decoded)
            return papers[0] if papers else None


async def _resolve_tool_name(session: ClientSession, *, role: str) -> str | None:
    async with _MCP_TOOL_CACHE_LOCK:
        cached = _MCP_TOOL_CACHE.get(role)
        if cached:
            return cached

    listed = await session.list_tools()
    tools = getattr(listed, "tools", []) or []
    names = [getattr(t, "name", "") for t in tools if getattr(t, "name", "")]

    configured = settings.ARXIV_MCP_SEARCH_TOOL if role == "search" else settings.ARXIV_MCP_DETAILS_TOOL
    if configured and configured in names:
        selected = configured
    else:
        selected = None
        preferred_exact = ["search_papers"] if role == "search" else ["get_paper_details", "get_paper", "paper_details"]
        for candidate in preferred_exact:
            if candidate in names:
                selected = candidate
                break
        for candidate in names:
            if selected is not None:
                break
            lowered = candidate.lower()
            if role == "search" and "search" in lowered and "arxiv" in lowered:
                selected = candidate
                break
            if role == "details" and ("detail" in lowered or "paper" in lowered) and "arxiv" in lowered:
                selected = candidate
                break
        if selected is None and role == "search" and names:
            selected = names[0]

    if selected:
        async with _MCP_TOOL_CACHE_LOCK:
            _MCP_TOOL_CACHE[role] = selected
    return selected


async def _call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    params = _build_stdio_params()
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            text = _to_text_payload(getattr(result, "content", result))
            return _parse_payload(text)


async def search_papers(
    query: str,
    max_results: int = 10,
    sort_by: str = "relevance",
) -> list[PaperInfo]:
    """Search arXiv papers through MCP server tools."""
    normalized_max = max(1, int(max_results))
    cache_key = (query.strip().lower(), normalized_max, sort_by)
    cached = _SEARCH_CACHE.get(cache_key)
    now = time.monotonic()
    if cached is not None:
        cached_at, cached_papers = cached
        if now - cached_at <= _SEARCH_CACHE_TTL_SECONDS:
            logger.info(
                "[RESEARCH_AGENT] mcp.arxiv.search cache_hit query=%r max_results=%s sort_by=%s returned=%s",
                query,
                normalized_max,
                sort_by,
                len(cached_papers),
            )
            return list(cached_papers)

    if now < _ARXIV_RATE_LIMITED_UNTIL:
        logger.info(
            "[RESEARCH_AGENT] mcp.arxiv.search cooldown_skip query=%r remaining_s=%.1f",
            query,
            _ARXIV_RATE_LIMITED_UNTIL - now,
        )
        return []

    logger.info(
        "[RESEARCH_AGENT] mcp.arxiv.search start query=%r max_results=%s sort_by=%s",
        query,
        normalized_max,
        sort_by,
    )
    _set_last_search_diagnostic("")

    papers: list[PaperInfo] = []
    rate_limited_response = False
    skip_stdio_fallback = bool(settings.ARXIV_MCP_HTTP_URL) and os.name == "nt"

    # --- 1. Try HTTP MCP server (preferred, avoids Windows subprocess issue) ---
    if settings.ARXIV_MCP_HTTP_URL and now >= _MCP_HTTP_UNAVAILABLE_UNTIL:
        try:
            papers = await asyncio.wait_for(
                _mcp_http_search(query, normalized_max, sort_by),
                timeout=max(1, settings.ARXIV_MCP_TIMEOUT_SECONDS),
            )
            if papers:
                logger.info(
                    "[RESEARCH_AGENT] mcp_http.search success query=%r fetched=%s",
                    query, len(papers),
                )
        except TimeoutError:
            logger.warning("[RESEARCH_AGENT] mcp_http.search timeout query=%r", query)
            _mark_mcp_http_unavailable(reason="timeout")
        except Exception as exc:
            if _is_rate_limit_error(exc):
                _mark_rate_limited(
                    reason=(
                        "ArXiv API is rate-limiting this environment (HTTP 429). "
                        "MCP retry will be available shortly."
                    )
                )
                return []
            _mark_mcp_http_unavailable(reason="unavailable")
            logger.warning("[RESEARCH_AGENT] mcp_http.search unavailable (server not running?) query=%r", query)
    elif settings.ARXIV_MCP_HTTP_URL and now < _MCP_HTTP_UNAVAILABLE_UNTIL:
        logger.info(
            "[RESEARCH_AGENT] mcp_http.search cooldown_skip query=%r remaining_s=%.1f",
            query,
            _MCP_HTTP_UNAVAILABLE_UNTIL - now,
        )

    # --- 1b. Try SSE MCP server (common endpoint for standalone arxiv-mcp-server) ---
    if not papers and settings.ARXIV_MCP_SSE_URL:
        try:
            papers = await asyncio.wait_for(
                _mcp_sse_search(query, normalized_max, sort_by),
                timeout=max(1, settings.ARXIV_MCP_TIMEOUT_SECONDS),
            )
            if papers:
                logger.info(
                    "[RESEARCH_AGENT] mcp_sse.search success query=%r fetched=%s",
                    query,
                    len(papers),
                )
        except TimeoutError:
            logger.warning("[RESEARCH_AGENT] mcp_sse.search timeout query=%r", query)
        except Exception as exc:
            if _is_rate_limit_error(exc):
                _mark_rate_limited(
                    reason=(
                        "ArXiv API is rate-limiting this environment (HTTP 429). "
                        "MCP retry will be available shortly."
                    )
                )
                return []
            logger.warning("[RESEARCH_AGENT] mcp_sse.search unavailable query=%r error=%s", query, exc)

    # --- 2. Try stdio MCP server (skip on Windows when HTTP MCP is configured) ---
    if not papers and not skip_stdio_fallback:
        try:
            async def _mcp_search() -> list[PaperInfo]:
                params = _build_stdio_params()
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tool_name = await _resolve_tool_name(session, role="search")
                        if not tool_name:
                            logger.error("[RESEARCH_AGENT] mcp.arxiv.search missing_search_tool")
                            return []
                        argument_variants: list[dict[str, Any]] = [
                            {"query": query, "max_results": normalized_max, "sort_by": sort_by},
                            {"query": query, "maxResults": normalized_max, "sortBy": sort_by},
                            {"q": query, "limit": normalized_max, "sort": sort_by},
                        ]
                        for arguments in argument_variants:
                            payload = await session.call_tool(tool_name, arguments)
                            decoded = _decode_tool_result(payload)
                            parsed = _papers_from_payload(decoded)
                            if parsed:
                                return parsed
                return []

            papers = await asyncio.wait_for(_mcp_search(), timeout=max(1, settings.ARXIV_MCP_TIMEOUT_SECONDS))
        except TimeoutError:
            _set_last_search_diagnostic("MCP arXiv server timed out.")
            logger.warning("[RESEARCH_AGENT] mcp.arxiv.search timeout query=%r", query)
        except NotImplementedError:
            logger.info("[RESEARCH_AGENT] mcp.arxiv.search skipped (Windows subprocess not supported)")
        except Exception as exc:
            if _is_rate_limit_error(exc):
                _mark_rate_limited(
                    reason=(
                        "ArXiv API is rate-limiting this environment (HTTP 429). "
                        "MCP retry will be available shortly."
                    )
                )
                return []
            _set_last_search_diagnostic("MCP arXiv server failed.")
            logger.warning("[RESEARCH_AGENT] mcp.arxiv.search failed query=%r error=%s", query, exc)
    elif not papers and skip_stdio_fallback:
        logger.info("[RESEARCH_AGENT] mcp.arxiv.search skip_stdio_fallback query=%r", query)

    # --- 3. MCP-only mode: no direct arXiv fallback ---
    if not papers:
        _set_last_search_diagnostic("MCP search returned no papers.")
        logger.info("[RESEARCH_AGENT] mcp_only.search no_fallback query=%r", query)

    logger.info(
        "[RESEARCH_AGENT] mcp.arxiv.search success query=%r fetched=%s",
        query,
        len(papers),
    )
    if papers and not rate_limited_response:
        _SEARCH_CACHE[cache_key] = (time.monotonic(), list(papers))
    if papers:
        _set_last_search_diagnostic("")
    return papers[:normalized_max]


async def get_paper_details(arxiv_id: str) -> Optional[PaperInfo]:
    """Retrieve full details for one paper through MCP tools."""
    logger.info("[RESEARCH_AGENT] mcp.arxiv.details start id=%s", arxiv_id)
    details: Optional[PaperInfo] = None
    skip_stdio_fallback = bool(settings.ARXIV_MCP_HTTP_URL) and os.name == "nt"

    # --- 1. HTTP MCP server ---
    if settings.ARXIV_MCP_HTTP_URL:
        try:
            details = await asyncio.wait_for(
                _mcp_http_details(arxiv_id),
                timeout=max(1, settings.ARXIV_MCP_TIMEOUT_SECONDS),
            )
            if details:
                logger.info("[RESEARCH_AGENT] mcp_http.details success id=%s", arxiv_id)
        except TimeoutError:
            logger.warning("[RESEARCH_AGENT] mcp_http.details timeout id=%s", arxiv_id)
        except Exception:
            logger.warning("[RESEARCH_AGENT] mcp_http.details unavailable id=%s", arxiv_id)

    # --- 1b. SSE MCP server ---
    if details is None and settings.ARXIV_MCP_SSE_URL:
        try:
            details = await asyncio.wait_for(
                _mcp_sse_details(arxiv_id),
                timeout=max(1, settings.ARXIV_MCP_TIMEOUT_SECONDS),
            )
            if details:
                logger.info("[RESEARCH_AGENT] mcp_sse.details success id=%s", arxiv_id)
        except TimeoutError:
            logger.warning("[RESEARCH_AGENT] mcp_sse.details timeout id=%s", arxiv_id)
        except Exception as exc:
            logger.warning("[RESEARCH_AGENT] mcp_sse.details unavailable id=%s error=%s", arxiv_id, exc)

    # --- 2. stdio MCP fallback (skip on Windows when HTTP MCP is configured) ---
    if details is None and not skip_stdio_fallback:
        try:
            async def _mcp_details() -> Optional[PaperInfo]:
                params = _build_stdio_params()
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tool_name = await _resolve_tool_name(session, role="details") or await _resolve_tool_name(session, role="search")
                        if not tool_name:
                            return None
                        payload = await session.call_tool(tool_name, {
                            "arxiv_id": arxiv_id, "id": arxiv_id, "paper_id": arxiv_id,
                            "query": f"id:{arxiv_id}", "max_results": 1, "maxResults": 1,
                        })
                        decoded = _decode_tool_result(payload)
                        papers = _papers_from_payload(decoded)
                        return papers[0] if papers else None

            details = await asyncio.wait_for(_mcp_details(), timeout=max(1, settings.ARXIV_MCP_TIMEOUT_SECONDS))
        except (TimeoutError, NotImplementedError):
            pass
        except Exception as exc:
            logger.warning("[RESEARCH_AGENT] mcp.arxiv.details failed id=%s error=%s", arxiv_id, exc)
    elif details is None and skip_stdio_fallback:
        logger.info("[RESEARCH_AGENT] mcp.arxiv.details skip_stdio_fallback id=%s", arxiv_id)

    # --- 3. MCP-only mode: no direct arXiv fallback ---
    if details is None:
        logger.info("[RESEARCH_AGENT] mcp_only.details no_fallback id=%s", arxiv_id)
        return None

    logger.info("[RESEARCH_AGENT] mcp.arxiv.details success id=%s title=%r", details.arxiv_id, details.title)
    return details
