"""Google Sheets exporter: backward-compatible Sheets output.

Migrated from src/sheets.py. Provides append_predictions and
update_actuals for the legacy Google Sheets workflow.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "日付",
    "ティッカー",
    "現在価格",
    "予測価格",
    "予測上昇率(%)",
    "信頼区間(%)",
    "翌週実績価格",
    "的中",
    "ステータス",
    "prob_up",
]


def get_client() -> Any:
    """Get Google Sheets API client.

    Returns:
        gspread.Client instance.
    """
    import gspread
    from google.oauth2.service_account import Credentials

    import os
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_path:
        raise ValueError("GOOGLE_CREDENTIALS_JSON environment variable is required")

    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    except (FileNotFoundError, ValueError):
        creds_info = json.loads(creds_path)
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return gspread.authorize(creds)


def get_or_create_worksheet(
    client: Any,
    spreadsheet_name: str,
    worksheet_name: str,
) -> Any:
    """Get or create a worksheet in a spreadsheet.

    Args:
        client: gspread.Client instance.
        spreadsheet_name: Name of the spreadsheet.
        worksheet_name: Name of the worksheet.

    Returns:
        gspread.Worksheet instance.
    """
    import gspread

    try:
        spreadsheet = client.open(spreadsheet_name)
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(spreadsheet_name)
        logger.info("spreadsheet_created", name=spreadsheet_name)

    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=worksheet_name, rows=1000, cols=len(HEADERS)
        )
        worksheet.append_row(HEADERS)
        logger.info("worksheet_created", name=worksheet_name)

    return worksheet


def append_predictions(
    predictions_df: pd.DataFrame,
    config: dict[str, Any],
    market: str | None = None,
) -> int:
    """Append prediction results to Google Sheets.

    Args:
        predictions_df: Prediction DataFrame with ticker, current_price, etc.
        config: Application config with google_sheets settings.
        market: Market name ('us', 'jp'). Appended to worksheet name if set.

    Returns:
        Number of rows appended.
    """
    sheets_cfg = config.get("google_sheets", {})
    if not sheets_cfg:
        logger.warning("google_sheets_config_missing")
        return 0

    base_ws_name = sheets_cfg["worksheet_name"]
    worksheet_name = f"{base_ws_name}_{market}" if market else base_ws_name

    client = get_client()
    ws = get_or_create_worksheet(client, sheets_cfg["spreadsheet_name"], worksheet_name)

    today = datetime.now().strftime("%Y-%m-%d")
    rows: list[list[Any]] = []
    for _, row in predictions_df.iterrows():
        rows.append([
            today,
            row["ticker"],
            row["current_price"],
            row["predicted_price"],
            row["predicted_change_pct"],
            row.get("ci_pct", ""),
            "",
            "",
            "予測済み",
            row.get("prob_up", ""),
        ])

    if rows:
        ws.append_rows(rows)
        logger.info("sheets_predictions_appended", count=len(rows))

    return len(rows)


def update_actuals(
    actual_prices: dict[str, float],
    target_date: str,
    config: dict[str, Any],
) -> int:
    """Update actual prices and hit status in Google Sheets.

    Args:
        actual_prices: Mapping of ticker -> actual closing price.
        target_date: Prediction date to update.
        config: Application config.

    Returns:
        Number of rows updated.
    """
    sheets_cfg = config.get("google_sheets", {})
    if not sheets_cfg:
        return 0

    client = get_client()
    ws = get_or_create_worksheet(
        client, sheets_cfg["spreadsheet_name"], sheets_cfg["worksheet_name"]
    )

    all_records = ws.get_all_records()
    updated = 0

    for i, record in enumerate(all_records):
        row_num = i + 2

        if record["ステータス"] != "予測済み":
            continue
        if record["翌週実績価格"] != "":
            continue
        if record["日付"] != target_date:
            continue

        ticker = record["ティッカー"]
        if ticker not in actual_prices:
            continue

        actual_price = actual_prices[ticker]
        current_price = float(record["現在価格"])

        actual_change = (actual_price - current_price) / current_price * 100
        is_hit = "的中" if actual_change > 0 else "外れ"

        ws.update_cell(row_num, 7, round(actual_price, 2))
        ws.update_cell(row_num, 8, is_hit)
        ws.update_cell(row_num, 9, "確定済み")
        updated += 1

    logger.info("sheets_actuals_updated", count=updated, target_date=target_date)
    return updated
