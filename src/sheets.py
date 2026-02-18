"""ステップ3: Googleスプレッドシート自動記録

予測結果をGoogleスプレッドシートに自動記録する。
前週の実績更新・的中判定もここで行う。
"""

import json
import logging
from datetime import datetime

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from src.utils import get_env, load_config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# スプレッドシートのヘッダー
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
]


def get_client() -> gspread.Client:
    """Google Sheets API クライアントを取得する。"""
    creds_path = get_env("GOOGLE_CREDENTIALS_JSON")
    # JSONファイルパスまたはJSON文字列に対応
    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    except (FileNotFoundError, ValueError):
        creds_info = json.loads(creds_path)
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return gspread.authorize(creds)


def get_or_create_worksheet(
    client: gspread.Client, spreadsheet_name: str, worksheet_name: str
) -> gspread.Worksheet:
    """スプレッドシートとワークシートを取得。なければ作成する。"""
    try:
        spreadsheet = client.open(spreadsheet_name)
    except gspread.SpreadsheetNotFound:
        spreadsheet = client.create(spreadsheet_name)
        logger.info("スプレッドシート作成: %s", spreadsheet_name)

    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=worksheet_name, rows=1000, cols=len(HEADERS)
        )
        worksheet.append_row(HEADERS)
        logger.info("ワークシート作成: %s", worksheet_name)

    return worksheet


def append_predictions(predictions_df: pd.DataFrame, config: dict | None = None) -> int:
    """予測結果をスプレッドシートに追記する。

    Args:
        predictions_df: predictor.predict() の出力。
        config: 設定辞書。

    Returns:
        追記した行数。
    """
    if config is None:
        config = load_config()

    sheets_cfg = config["google_sheets"]
    client = get_client()
    ws = get_or_create_worksheet(
        client, sheets_cfg["spreadsheet_name"], sheets_cfg["worksheet_name"]
    )

    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for _, row in predictions_df.iterrows():
        rows.append([
            today,
            row["ticker"],
            row["current_price"],
            row["predicted_price"],
            row["predicted_change_pct"],
            row["ci_pct"],
            "",       # 翌週実績価格 (翌週に記入)
            "",       # 的中 (翌週に判定)
            "予測済み",
        ])

    if rows:
        ws.append_rows(rows)
        logger.info("スプレッドシートに %d 行追記", len(rows))

    return len(rows)


def update_actuals(
    actual_prices: dict[str, float],
    target_date: str,
    config: dict | None = None,
) -> int:
    """指定日の予測に対して実績価格を記入し、的中判定を行う。

    Args:
        actual_prices: {ticker: 最終営業日終値} の辞書。
        target_date: 更新対象の予測日 (例: "2026-02-15")。この日付の行のみ更新。
        config: 設定辞書。

    Returns:
        更新した行数。
    """
    if config is None:
        config = load_config()

    sheets_cfg = config["google_sheets"]
    client = get_client()
    ws = get_or_create_worksheet(
        client, sheets_cfg["spreadsheet_name"], sheets_cfg["worksheet_name"]
    )

    all_records = ws.get_all_records()
    updated = 0

    for i, record in enumerate(all_records):
        # ヘッダー行は get_all_records で除外されるので +2 (1-indexed + header)
        row_num = i + 2

        if record["ステータス"] != "予測済み":
            continue
        if record["翌週実績価格"] != "":
            continue
        # 対象日の行のみ更新 [#2: 前週限定]
        if record["日付"] != target_date:
            continue

        ticker = record["ティッカー"]
        if ticker not in actual_prices:
            continue

        actual_price = actual_prices[ticker]
        current_price = float(record["現在価格"])

        # 的中判定: 上昇予測 → 実際に上昇 → 的中
        actual_change = (actual_price - current_price) / current_price * 100
        is_hit = "的中" if actual_change > 0 else "外れ"

        # 実績価格、的中、ステータスを更新
        ws.update_cell(row_num, 7, round(actual_price, 2))   # 翌週実績価格
        ws.update_cell(row_num, 8, is_hit)                    # 的中
        ws.update_cell(row_num, 9, "確定済み")                 # ステータス
        updated += 1

    logger.info("実績更新: %d 行 (対象日: %s)", updated, target_date)
    return updated
