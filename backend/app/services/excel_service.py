"""File-based spreadsheet loading service.

Loads CSV / XLSX / XLS files into Pandas DataFrames.
For querying, use pandas_agent_service.query_dataframe().
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def load_file_as_frames(
    file_path: str,
    sheet_name: Optional[str] = None,
) -> dict[str, pd.DataFrame]:
    """Load CSV/XLSX/XLS into a dict of DataFrames."""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(file_path, encoding="utf-8", on_bad_lines="skip")
        return {"Sheet1": df}

    if suffix in {".xlsx", ".xls"}:
        xls = pd.ExcelFile(file_path)
        if sheet_name:
            return {sheet_name: pd.read_excel(xls, sheet_name=sheet_name)}
        return {name: pd.read_excel(xls, sheet_name=name) for name in xls.sheet_names}

    raise ValueError(f"Unsupported file type: {suffix!r}. Supported: .csv, .xlsx, .xls")


async def async_load_file_as_frames(
    file_path: str,
    sheet_name: Optional[str] = None,
) -> dict[str, pd.DataFrame]:
    """Async wrapper around load_file_as_frames."""
    return await asyncio.to_thread(load_file_as_frames, file_path, sheet_name)


async def get_sheet_names(file_path: str) -> list[str]:
    """Return worksheet names for an Excel file, or Sheet1 for CSV."""
    def _run() -> list[str]:
        path = Path(file_path)
        if path.suffix.lower() == ".csv":
            return ["Sheet1"]
        xls = pd.ExcelFile(file_path)
        return xls.sheet_names
    try:
        return await asyncio.to_thread(_run)
    except Exception:
        logger.warning("Could not read sheet names from %s", file_path)
        return ["Sheet1"]


# ---------------------------------------------------------------------------
# Legacy shim – used by chat.py until it is updated to call pandas_agent_service
# ---------------------------------------------------------------------------

async def analyze_dataframe(
    file_path: str,
    question: str,
    user_email: str,
    sheet_name: Optional[str] = None,
):
    """Legacy entry point: load file and query with pandas agent."""
    from app.services.pandas_agent_service import query_dataframe, dataframe_info_summary

    frames = load_file_as_frames(file_path, sheet_name)
    if not frames:
        return {"answer": "Could not load any data from the file.", "data_summary": "", "error": "Empty file"}

    target_df = next(iter(frames.values()))
    summary = dataframe_info_summary(frames)
    result = await query_dataframe(target_df, question, user_email)
    result["data_summary"] = summary
    return result
