"""Pandas DataFrame Agent service.

Wraps LangChain's create_pandas_dataframe_agent.  Accepts a pre-loaded
DataFrame so callers can use any data source (file, Google Sheet, etc.).

All LLM calls route exclusively through the Amzur LiteLLM proxy.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import pandas as pd

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def query_dataframe(
    df: pd.DataFrame,
    question: str,
    user_email: str,
    df_name: str = "df",
    history: Optional[list[dict[str, str]]] = None,
) -> dict[str, Any]:
    """Ask a natural-language question about *df*.

    Args:
        df:          The DataFrame to analyse.
        question:    The user's natural-language question.
        user_email:  Authenticated user's email (for LiteLLM cost attribution).
        df_name:     Display name used in the agent's system prompt.
        history:     Optional list of previous {"role": ..., "content": ...}
                     pairs for follow-up context.

    Returns:
        {
            "answer":       str,   # conversational answer
            "code":         str,   # pandas code the agent executed (if any)
            "error":        str | None,
        }
    """
    # Build contextual prefix from history so the agent can handle follow-ups
    context_prefix = ""
    if history:
        recent = history[-6:]           # last 3 turns
        lines = []
        for msg in recent:
            role = "User" if msg.get("role") == "human" else "Assistant"
            lines.append(f"{role}: {msg.get('content', '')}")
        context_prefix = (
            "Previous conversation context:\n"
            + "\n".join(lines)
            + "\n\nNow answer the following question:\n"
        )

    full_question = context_prefix + question

    def _run() -> dict[str, Any]:
        from langchain_experimental.agents import create_pandas_dataframe_agent
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            base_url=settings.LITELLM_PROXY_URL,
            api_key=settings.LITELLM_API_KEY,
            timeout=90,
            max_retries=2,
        )

        agent = create_pandas_dataframe_agent(
            llm,
            df,
            verbose=True,
            allow_dangerous_code=True,
            return_intermediate_steps=True,
            max_iterations=10,
            agent_executor_kwargs={
                "handle_parsing_errors": True,
            },
        )

        result = agent.invoke(
            {"input": full_question},
            config={
                "metadata": {
                    "user_email": user_email,
                    "application": settings.APP_NAME,
                    "environment": settings.ENVIRONMENT,
                }
            },
        )

        answer: str = result.get("output", "").strip()
        code = _extract_code(result.get("intermediate_steps", []))
        return {"answer": answer, "code": code, "error": None}

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        detail = str(exc).strip() or type(exc).__name__
        logger.exception("Pandas agent query failed for user=%s", user_email)
        return {"answer": "", "code": "", "error": detail}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_code(steps: list) -> str:
    """Pull python_repl_ast code from agent intermediate steps."""
    code_blocks: list[str] = []
    for action, _ in steps:
        tool = getattr(action, "tool", "")
        tool_input = getattr(action, "tool_input", "")
        if tool in ("python_repl_ast", "python_repl") and isinstance(tool_input, str):
            code_blocks.append(tool_input.strip())
    return "\n\n".join(code_blocks)


# ---------------------------------------------------------------------------
# Utility: DataFrame → human-readable info
# ---------------------------------------------------------------------------

def dataframe_info_summary(frames: dict[str, pd.DataFrame]) -> str:
    """Return a compact markdown summary of loaded sheets."""
    lines = []
    for name, df in frames.items():
        lines.append(f"**Sheet: {name}**")
        lines.append(f"- Rows: {len(df):,}  |  Columns: {len(df.columns)}")
        lines.append(f"- Column names: {', '.join(df.columns.tolist())}")
        dtype_pairs = [(c, str(t)) for c, t in df.dtypes.items()]
        type_summary = ", ".join(f"{c}: {t}" for c, t in dtype_pairs[:10])
        if len(dtype_pairs) > 10:
            type_summary += f" … (+{len(dtype_pairs) - 10} more)"
        lines.append(f"- Types: {type_summary}")
        lines.append("")
    return "\n".join(lines)


def dataframe_to_markdown(df: pd.DataFrame, max_rows: int = 50) -> str:
    """Convert a DataFrame to a markdown table (truncated to *max_rows*)."""
    if len(df) > max_rows:
        preview = df.head(max_rows)
        note = f"\n\n*Showing first {max_rows} of {len(df):,} rows.*"
    else:
        preview = df
        note = ""
    try:
        return preview.to_markdown(index=False) + note
    except Exception:
        return preview.to_string(index=False) + note
