"""ステップ5: Slack Incoming Webhook 通知

Webhook-only 方式で #stock-alerts チャンネルにレポートを投稿する。
beginner_mode 有効時は用語解説を自動付与する。
"""

import logging
from datetime import datetime

import pandas as pd
import requests

from src.glossary import generate_beginner_notes
from src.utils import get_env, load_config

logger = logging.getLogger(__name__)


def build_report(
    predictions_df: pd.DataFrame,
    accuracy: dict | None = None,
    config: dict | None = None,
) -> str:
    """Slack通知用のレポートテキストを生成する。

    Args:
        predictions_df: predictor.predict() の出力 (上昇予測銘柄)。
        accuracy: tracker.calculate_accuracy() の出力。None なら的中率セクション省略。
        config: 設定辞書。

    Returns:
        Slack投稿用のテキスト。
    """
    if config is None:
        config = load_config()

    today = datetime.now().strftime("%Y-%m-%d")
    beginner_mode = config.get("display", {}).get("beginner_mode", False)

    lines = [
        f"*週間AI株式予測レポート ({today})*",
        "",
    ]

    # 今週の上昇予測銘柄
    if predictions_df.empty:
        lines.append("今週は上昇予測の銘柄がありませんでした。")
    else:
        lines.append("*【今週の上昇予測銘柄】*")
        for i, row in predictions_df.iterrows():
            lines.append(
                f"  {i + 1}. *{row['ticker']}*: "
                f"${row['current_price']:.2f} → ${row['predicted_price']:.2f} "
                f"(予測 +{row['predicted_change_pct']:.1f}%, "
                f"信頼区間 ±{row['ci_pct']:.1f}%)"
            )

    # 先週の的中率
    if accuracy:
        lines.append("")
        lines.append("*【先週の的中率】* (判定: 最終営業日終値基準)")
        lines.append(
            f"  的中: {accuracy['hits']}/{accuracy['total']}銘柄 "
            f"({accuracy['hit_rate_pct']:.1f}%)"
        )
        if accuracy.get("cumulative_total", 0) > 0:
            lines.append(
                f"  累計的中率: {accuracy['cumulative_hit_rate_pct']:.1f}% "
                f"(過去{accuracy['cumulative_weeks']}週)"
            )

    # スプレッドシートリンク
    sheets_cfg = config.get("google_sheets", {})
    sheet_name = sheets_cfg.get("spreadsheet_name", "")
    if sheet_name:
        lines.append("")
        lines.append(f"詳細: Google Sheets「{sheet_name}」を参照")

    # beginner_mode: 用語解説
    if beginner_mode:
        notes = generate_beginner_notes()
        if notes:
            lines.append("")
            lines.append(f"_{notes}_")

    return "\n".join(lines)


def send_to_slack(text: str) -> bool:
    """Slack Incoming Webhook にテキストを送信する。

    Returns:
        成功時 True、失敗時 False。
    """
    webhook_url = get_env("SLACK_WEBHOOK_URL")
    payload = {"text": text}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=30)
        if resp.status_code == 200 and resp.text == "ok":
            logger.info("Slack通知送信成功")
            return True
        else:
            logger.error("Slack通知失敗: status=%d, body=%s", resp.status_code, resp.text)
            return False
    except requests.RequestException:
        logger.exception("Slack通知送信エラー")
        return False


def notify(
    predictions_df: pd.DataFrame,
    accuracy: dict | None = None,
    config: dict | None = None,
) -> bool:
    """レポートを生成してSlackに送信し、LINE でチェックを促す。"""
    if config is None:
        config = load_config()

    report = build_report(predictions_df, accuracy, config)
    logger.info("レポート生成完了 (%d文字)", len(report))

    slack_ok = send_to_slack(report)

    # LINE 通知 (有効時のみ: Slack 通知後にチェックを促す)
    line_ok = True
    if config.get("line", {}).get("enabled", False):
        try:
            from src.line_notifier import send_to_line

            line_ok = send_to_line(report)
        except Exception:
            logger.exception("LINE通知でエラーが発生しました")
            line_ok = False

    return slack_ok and line_ok
