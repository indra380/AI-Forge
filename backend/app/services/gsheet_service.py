"""Google Sheets integration service.

Uses gspread with service account credentials. Loads sheet data as pandas DataFrames
for use with the Excel analysis agent.
"""
import io
import json
import re
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

from app.core.config import settings


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def _get_gspread_client():
    """Create an authenticated gspread client from the service account JSON.

    ``GOOGLE_SERVICE_ACCOUNT_JSON`` may contain either:
    - The raw JSON string (inline), or
    - A file-system path to the service-account JSON file.
    """
    import gspread
    from google.oauth2.service_account import Credentials

    raw = (settings.GOOGLE_SERVICE_ACCOUNT_JSON or "").strip()
    if not raw:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not configured. "
            "Set this environment variable to the service-account JSON content "
            "or a path to the JSON file."
        )

    # Determine whether the value is a file path or inline JSON
    if raw.startswith("{"):
        # Inline JSON string
        try:
            creds_data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"GOOGLE_SERVICE_ACCOUNT_JSON contains invalid JSON: {exc}"
            ) from exc
    else:
        # Treat as a file path
        creds_path = Path(raw)
        if not creds_path.is_file():
            raise ValueError(
                f"GOOGLE_SERVICE_ACCOUNT_JSON looks like a file path but "
                f"the file was not found: {creds_path}"
            )
        try:
            creds_data = json.loads(creds_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Service account file {creds_path} contains invalid JSON: {exc}"
            ) from exc

    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
    return gspread.authorize(creds)


# ---------------------------------------------------------------------------
# Sheet URL / ID parsing
# ---------------------------------------------------------------------------

def extract_sheet_id(url_or_id: str) -> str:
    """Extract spreadsheet ID from a full URL or return the ID directly."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    if match:
        return match.group(1)
    return url_or_id.strip()


# ---------------------------------------------------------------------------
# Load sheet as DataFrame
# ---------------------------------------------------------------------------

def load_gsheet_as_dataframe(
    url_or_id: str,
    worksheet_name: Optional[str] = None,
) -> dict[str, pd.DataFrame]:
    """Load a Google Sheet into a dict of {worksheet_name: DataFrame}.

    Requires GOOGLE_SERVICE_ACCOUNT_JSON to be set.
    The service account must have view access to the spreadsheet.
    """
    client = _get_gspread_client()
    sheet_id = extract_sheet_id(url_or_id)
    spreadsheet = client.open_by_key(sheet_id)

    if worksheet_name:
        ws = spreadsheet.worksheet(worksheet_name)
        data = ws.get_all_values()
        df = _records_to_df(data)
        return {worksheet_name: df}

    result = {}
    for ws in spreadsheet.worksheets():
        data = ws.get_all_values()
        result[ws.title] = _records_to_df(data)
    return result


def _records_to_df(rows: list[list]) -> pd.DataFrame:
    """Convert raw sheet rows to a DataFrame using the first row as headers."""
    if not rows:
        return pd.DataFrame()
    headers = rows[0]
    data_rows = rows[1:]
    return pd.DataFrame(data_rows, columns=headers)


def save_gsheet_to_temp_csv(url_or_id: str, worksheet_name: Optional[str] = None) -> str:
    """Download a Google Sheet and save it as a temp CSV file.

    Returns the temp file path for use with the Excel analysis agent.
    """
    frames = load_gsheet_as_dataframe(url_or_id, worksheet_name)
    if not frames:
        raise ValueError("No worksheets found in the spreadsheet.")

    df = next(iter(frames.values()))
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8")
    df.to_csv(tmp.name, index=False)
    tmp.close()
    return tmp.name


def list_worksheet_names(url_or_id: str) -> list[str]:
    """Return worksheet names for a spreadsheet."""
    client = _get_gspread_client()
    sheet_id = extract_sheet_id(url_or_id)
    spreadsheet = client.open_by_key(sheet_id)
    return [ws.title for ws in spreadsheet.worksheets()]
