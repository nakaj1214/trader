"""Google Sheets I/O for the manual position monitor."""
from __future__ import annotations

import json
import os
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
STATUS_COLUMNS = (
    "ticker",
    "entry_date",
    "entry_price",
    "current_price",
    "high_water_mark",
    "stop_price",
    "trailing_stop_pct",
    "unrealized_pct",
    "distance_to_stop_pct",
    "triggered",
    "exit_reason",
    "as_of_at",
    "quote_source",
    "status",
    "error",
)


def _worksheet(name: str) -> Any:
    raw_credentials = os.getenv("GOOGLE_CREDENTIALS_JSON")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not raw_credentials or not sheet_id:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON and GOOGLE_SHEET_ID are required")
    try:
        info = json.loads(raw_credentials)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_CREDENTIALS_JSON is not valid JSON") from exc
    if not isinstance(info, dict):
        raise TypeError("GOOGLE_CREDENTIALS_JSON must be a JSON object")
    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)  # type: ignore[no-untyped-call]
    return gspread.authorize(credentials).open_by_key(sheet_id).worksheet(name)


def read_holdings(worksheet_name: str = "保有銘柄") -> list[dict[str, Any]]:
    return list(_worksheet(worksheet_name).get_all_records())


def write_status(rows: list[dict[str, Any]], worksheet_name: str = "状況") -> None:
    worksheet = _worksheet(worksheet_name)
    values = [list(STATUS_COLUMNS)]
    values.extend([[row.get(column, "") if row.get(column) is not None else "" for column in STATUS_COLUMNS] for row in rows])
    # ponytail: two-call replacement is enough at this scale; use a staging sheet if atomicity becomes necessary.
    worksheet.clear()
    worksheet.update(values, "A1")
