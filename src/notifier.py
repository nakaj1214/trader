"""ステップ5: Slack Incoming Webhook 通知

Webhook-only 方式で #stock-alerts チャンネルにレポートを投稿する。
beginner_mode 有効時は用語解説を自動付与する。
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import requests

from src.glossary import generate_beginner_notes
from src.utils import get_env, load_config

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    """通知送信の結果を構造化して保持する。"""

    channel: str
    success: bool
    status_code: int | None = None
    error_message: str | None = None


def _log_notification_result(result: NotificationResult) -> None:
    """通知結果を構造化ログとして出力する。"""
    if result.success:
        logger.info(
            "notification_sent channel=%s status_code=%s",
            result.channel,
            result.status_code,
        )
    else:
        logger.error(
            "notification_failed channel=%s status_code=%s error=%s",
            result.channel,
            result.status_code,
            result.error_message,
        )


def _resolve_notification_config(config: dict) -> dict:
    """新旧config形式を統一的に解決する。

    新形式 (notifications.slack.enabled / notifications.line.enabled) を優先し、
    存在しなければ旧形式 (line.enabled) にフォールバックする。
    """
    notif = config.get("notifications", {})

    slack_enabled = notif.get("slack", {}).get("enabled", True)
    line_enabled = notif.get("line", {}).get(
        "enabled", config.get("line", {}).get("enabled", False)
    )

    return {
        "slack": {"enabled": slack_enabled},
        "line": {"enabled": line_enabled},
    }


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


def send_to_slack(text: str) -> NotificationResult:
    """Slack Incoming Webhook にテキストを送信する。

    Returns:
        NotificationResult: 送信結果。
    """
    webhook_url = get_env("SLACK_WEBHOOK_URL")
    payload = {"text": text}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=30)
        success = resp.status_code == 200 and resp.text == "ok"
        result = NotificationResult(
            channel="slack",
            success=success,
            status_code=resp.status_code,
            error_message=None if success else resp.text,
        )
    except requests.RequestException as e:
        result = NotificationResult(
            channel="slack",
            success=False,
            status_code=None,
            error_message=str(e),
        )

    _log_notification_result(result)
    return result


def notify(
    predictions_df: pd.DataFrame,
    accuracy: dict | None = None,
    config: dict | None = None,
) -> bool:
    """レポートを生成してSlackに送信し、LINE でチェックを促す。"""
    if config is None:
        config = load_config()

    notif_config = _resolve_notification_config(config)
    report = build_report(predictions_df, accuracy, config)
    logger.info("レポート生成完了 (%d文字)", len(report))

    slack_ok = True  # 無効時は「意図的スキップ＝成功」扱い
    if notif_config["slack"]["enabled"]:
        slack_result = send_to_slack(report)
        slack_ok = slack_result.success
    else:
        logger.info("Slack通知はconfig無効のためスキップ")

    # LINE 通知 (有効時のみ: Slack 通知後にチェックを促す)
    # LINE はあくまで補助的な通知のため、失敗しても全体の結果には影響させない
    if notif_config["line"]["enabled"]:
        try:
            from src.line_notifier import send_to_line

            slack_channel = config.get("slack", {}).get("channel", "#stock-alerts")
            send_to_line(report, slack_channel=slack_channel)
        except Exception:
            logger.exception("LINE通知でエラーが発生しました")

    return slack_ok
