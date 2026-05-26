"""FastAPI router: /api/data

Endpoints:
  POST /api/data/upload          – upload CSV / XLSX file
  POST /api/data/google-sheet    – connect a Google Sheet by URL
  POST /api/data/query           – ask a NL question about a stored dataset
  GET  /api/data/datasets        – list datasets owned by the current user
  DELETE /api/data/{dataset_id}  – delete a stored dataset
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.models.user import User
from app.schemas.data import (
    DataQueryRequest,
    DataQueryResponse,
    DatasetInfo,
    DatasetListResponse,
    DatasetUploadResponse,
    GoogleSheetRequest,
    GoogleSheetResponse,
)
from app.services.auth_service import get_current_user
from app.services.dataset_store_service import dataset_store
from app.services.excel_service import load_file_as_frames
from app.services.pandas_agent_service import dataframe_info_summary, query_dataframe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])

# MIME types accepted for spreadsheet upload
_ALLOWED_MIME: frozenset[str] = frozenset(
    settings.ATTACHMENT_TABLE_MIME_TYPES
)
_ALLOWED_SUFFIXES: frozenset[str] = frozenset({".csv", ".xlsx", ".xls"})


# ---------------------------------------------------------------------------
# POST /api/data/upload
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=DatasetUploadResponse, status_code=201)
async def upload_spreadsheet(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> DatasetUploadResponse:
    """Upload a CSV or XLSX file and store it as a dataset."""

    # --- Validate MIME type (server-side; never trust extension alone) ------
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    suffix = Path(file.filename or "").suffix.lower()

    if content_type not in _ALLOWED_MIME and suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail={
                "error": "unsupported_file_type",
                "message": f"Only CSV / XLSX files are accepted. Got: {content_type}",
            },
        )

    # --- Enforce upload size limit ------------------------------------------
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "file_too_large",
                "message": f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB limit.",
            },
        )

    # --- Save to upload directory so load_file_as_frames can read it --------
    upload_dir = Path(settings.UPLOAD_PATH) / "tables"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4()}{suffix}"
    dest = upload_dir / safe_name
    dest.write_bytes(data)

    # --- Load into DataFrames -----------------------------------------------
    try:
        frames = load_file_as_frames(str(dest))
    except Exception as exc:
        dest.unlink(missing_ok=True)
        logger.exception("Failed to load uploaded file %s", file.filename)
        raise HTTPException(
            status_code=422,
            detail={"error": "load_failed", "message": str(exc)},
        ) from exc

    # --- Persist in session store -------------------------------------------
    entry = dataset_store.save(
        user_id=str(current_user.id),
        filename=file.filename or safe_name,
        frames=frames,
    )

    first_df = next(iter(frames.values()))
    return DatasetUploadResponse(
        dataset_id=entry.dataset_id,
        filename=entry.filename,
        rows=len(first_df),
        columns=len(first_df.columns),
        sheets=list(frames.keys()),
    )


# ---------------------------------------------------------------------------
# POST /api/data/google-sheet
# ---------------------------------------------------------------------------

@router.post("/google-sheet", response_model=GoogleSheetResponse, status_code=201)
async def connect_google_sheet(
    payload: GoogleSheetRequest,
    current_user: User = Depends(get_current_user),
) -> GoogleSheetResponse:
    """Connect a Google Sheet and store it as a dataset."""
    if not (settings.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "gsheets_not_configured",
                "message": (
                    "Google Sheets integration is not enabled on this server. "
                    "Set GOOGLE_SERVICE_ACCOUNT_JSON in the environment."
                ),
            },
        )

    try:
        from app.services.gsheet_service import load_gsheet_as_dataframe  # noqa: F401

        frames = await _load_gsheet(payload)
    except PermissionError as exc:
        # gspread wraps APIError (403 / 404) as PermissionError; surface the
        # original cause so the frontend can show an actionable message.
        cause = exc.__cause__
        raw = str(cause) if cause else str(exc)
        # Pull out the human-readable part after the status bracket, e.g.
        # "APIError: [403]: Google Sheets API has not been used ..."
        message = raw.split("]:", 1)[-1].strip() if "]:" in raw else raw
        logger.error("Google Sheets permission error for %s: %s", payload.google_sheet_url, raw)
        raise HTTPException(
            status_code=403,
            detail={"error": "gsheet_permission_denied", "message": message or raw},
        ) from exc
    except Exception as exc:
        logger.exception("Failed to load Google Sheet: %s", payload.google_sheet_url)
        raise HTTPException(
            status_code=422,
            detail={"error": "gsheet_load_failed", "message": str(exc)},
        ) from exc

    # Use sheet title as filename
    title = payload.google_sheet_url.split("/")[-1] or "google_sheet"
    entry = dataset_store.save(
        user_id=str(current_user.id),
        filename=title,
        frames=frames,
        source_url=payload.google_sheet_url,
    )

    first_df = next(iter(frames.values()))
    return GoogleSheetResponse(
        dataset_id=entry.dataset_id,
        sheet_title=title,
        rows=len(first_df),
        columns=len(first_df.columns),
        sheets=list(frames.keys()),
    )


async def _load_gsheet(payload: GoogleSheetRequest) -> dict:
    """Load Google Sheet frames (isolated for testability)."""
    import asyncio
    from app.services.gsheet_service import load_gsheet_as_dataframe

    return await asyncio.to_thread(
        load_gsheet_as_dataframe,
        payload.google_sheet_url,
        payload.worksheet_name,
    )


# ---------------------------------------------------------------------------
# POST /api/data/query
# ---------------------------------------------------------------------------

@router.post("/query", response_model=DataQueryResponse)
async def query_dataset(
    payload: DataQueryRequest,
    current_user: User = Depends(get_current_user),
) -> DataQueryResponse:
    """Ask a natural-language question about a previously uploaded dataset."""
    entry = dataset_store.get(payload.dataset_id, str(current_user.id))
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "dataset_not_found",
                "message": (
                    "Dataset not found or has expired. "
                    "Please re-upload the file and try again."
                ),
            },
        )

    # Choose the target sheet
    if payload.sheet_name and payload.sheet_name in entry.frames:
        df = entry.frames[payload.sheet_name]
    else:
        df = next(iter(entry.frames.values()))

    summary = dataframe_info_summary(entry.frames)

    result = await query_dataframe(
        df=df,
        question=payload.question,
        user_email=current_user.email,
        df_name=entry.filename,
        history=payload.history,
    )

    if result.get("error"):
        logger.error(
            "Pandas agent error for user=%s dataset=%s: %s",
            current_user.email,
            payload.dataset_id,
            result["error"],
        )
        raise HTTPException(
            status_code=502,
            detail={"error": "agent_error", "message": result["error"]},
        )

    return DataQueryResponse(
        answer=result["answer"],
        code=result.get("code", ""),
        data_summary=summary,
    )


# ---------------------------------------------------------------------------
# GET /api/data/datasets
# ---------------------------------------------------------------------------

@router.get("/datasets", response_model=DatasetListResponse)
async def list_datasets(
    current_user: User = Depends(get_current_user),
) -> DatasetListResponse:
    """List all datasets stored for the current user."""
    entries = dataset_store.list_for_user(str(current_user.id))
    items: list[DatasetInfo] = []
    for e in entries:
        first_df = next(iter(e.frames.values()))
        items.append(
            DatasetInfo(
                dataset_id=e.dataset_id,
                filename=e.filename,
                rows=len(first_df),
                columns=len(first_df.columns),
                sheets=list(e.frames.keys()),
                created_at=e.created_at.isoformat(),
                source_url=e.source_url,
            )
        )
    return DatasetListResponse(datasets=items)


# ---------------------------------------------------------------------------
# DELETE /api/data/{dataset_id}
# ---------------------------------------------------------------------------

@router.delete("/{dataset_id}", status_code=200)
async def delete_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a stored dataset."""
    deleted = dataset_store.delete(dataset_id, str(current_user.id))
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": "dataset_not_found", "message": "Dataset not found."},
        )
    return {"status": "deleted"}