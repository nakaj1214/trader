"""Google Sheets I/O for the manual position monitor."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from numbers import Real
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_shared_spreadsheet: ContextVar[dict[str, Any] | None] = ContextVar("shared_spreadsheet", default=None)
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
    "triggered_at",
    "last_notified_at",
    "last_warned_at",
)


@contextmanager
def shared_spreadsheet() -> Iterator[None]:
    """Reuse one lazily opened spreadsheet within a monitor run; discard it on exit."""
    token = _shared_spreadsheet.set({})
    try:
        yield
    finally:
        _shared_spreadsheet.reset(token)


def _worksheet(name: str) -> Any:
    shared = _shared_spreadsheet.get()
    if shared is not None and "spreadsheet" in shared:
        return shared["spreadsheet"].worksheet(name)
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
    spreadsheet = gspread.authorize(credentials).open_by_key(sheet_id)
    if shared is not None:
        shared["spreadsheet"] = spreadsheet
    return spreadsheet.worksheet(name)


def read_holdings(worksheet_name: str = "保有銘柄") -> list[dict[str, Any]]:
    return list(_worksheet(worksheet_name).get_all_records())


def read_status(worksheet_name: str = "状況") -> list[dict[str, Any]]:
    return list(_worksheet(worksheet_name).get_all_records())


def assert_production_writer() -> None:
    """Actions owns the shared-state lock; local and other-branch writers are denied."""
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("GITHUB_REF") != "refs/heads/main":
        raise RuntimeError("production writer requires the serialized main-branch GitHub Actions job")


def _cell_data(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, Real) and math.isfinite(float(value)):
        return {"userEnteredValue": {"numberValue": float(value)}}
    return {"userEnteredValue": {"stringValue": str(value)}}


def write_status(rows: list[dict[str, Any]], worksheet_name: str = "状況") -> None:
    assert_production_writer()
    worksheet = _worksheet(worksheet_name)
    values = [list(STATUS_COLUMNS)]
    values.extend(
        [row.get(column, "") if row.get(column) is not None else "" for column in STATUS_COLUMNS] for row in rows
    )
    requests: list[dict[str, Any]] = []
    required_rows, required_columns = len(values), len(STATUS_COLUMNS)
    if worksheet.row_count < required_rows or worksheet.col_count < required_columns:
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": worksheet.id,
                        "gridProperties": {
                            "rowCount": max(worksheet.row_count, required_rows),
                            "columnCount": max(worksheet.col_count, required_columns),
                        },
                    },
                    "fields": "gridProperties.rowCount,gridProperties.columnCount",
                }
            }
        )
    requests.extend(
        [
            {
                "repeatCell": {
                    "range": {"sheetId": worksheet.id},
                    "cell": {},
                    "fields": "userEnteredValue",
                }
            },
            {
                "updateCells": {
                    "start": {"sheetId": worksheet.id, "rowIndex": 0, "columnIndex": 0},
                    "rows": [{"values": [_cell_data(value) for value in row]} for row in values],
                    "fields": "userEnteredValue",
                }
            },
        ]
    )
    worksheet.spreadsheet.batch_update({"requests": requests})
