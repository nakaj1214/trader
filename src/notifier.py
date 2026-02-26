"""ステップ5: Slack Incoming Webhook 通知

Webhook-only 方式で #stock-alerts チャンネルにレポートを投稿する。
beginner_mode 有効時は用語解説を自動付与する。
"""

import logging
import os
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


def _resolve_channel_id(channel_name: str, bot_token: str) -> str | None:
    """チャンネル名（例: "#stock-alerts"）から Slack チャンネル ID を解決する。

    解決失敗時は None を返す（例外を起こさない）。
    """
    name = channel_name.lstrip("#")
    try:
        resp = requests.get(
            "https://slack.com/api/conversations.list",
            headers={"Authorization": f"Bearer {bot_token}"},
            params={"types": "public_channel,private_channel", "limit": 1000},
            timeout=30,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("conversations.list 失敗: %s", data.get("error"))
            return None
        for ch in data.get("channels", []):
            if ch.get("name") == name:
                return ch["id"]
        logger.warning("チャンネル '%s' が見つかりません", channel_name)
    except Exception:
        logger.exception("チャンネル ID 解決エラー: %s", channel_name)
    return None


def _upload_chart_to_slack(
    ticker: str, chart_bytes: bytes, channel_id: str, bot_token: str
) -> bool:
    """Slack の新 API（files.getUploadURLExternal + completeUploadExternal）でチャートを upload する。

    Returns:
        True: upload 成功。False: upload 失敗（5xx 等）。
    """
    filename = f"{ticker}_chart.png"
    headers = {"Authorization": f"Bearer {bot_token}"}

    # Step 1: upload URL を取得
    try:
        url_resp = requests.post(
            "https://slack.com/api/files.getUploadURLExternal",
            headers=headers,
            json={"filename": filename, "length": len(chart_bytes)},
            timeout=30,
        )
        url_data = url_resp.json()
    except Exception:
        logger.exception("files.getUploadURLExternal エラー: %s", ticker)
        return False

    if not url_data.get("ok"):
        logger.error("files.getUploadURLExternal 失敗: %s — %s", ticker, url_data.get("error"))
        return False

    upload_url = url_data["upload_url"]
    file_id = url_data["file_id"]

    # Step 2: ファイルを upload URL に PUT
    try:
        put_resp = requests.put(
            upload_url,
            data=chart_bytes,
            headers={"Content-Type": "image/png"},
            timeout=60,
        )
        if put_resp.status_code >= 500:
            logger.error("チャート PUT 失敗: %s — HTTP %d", ticker, put_resp.status_code)
            return False
    except Exception:
        logger.exception("チャート PUT エラー: %s", ticker)
        return False

    # Step 3: upload を完了させてチャンネルに投稿
    try:
        complete_resp = requests.post(
            "https://slack.com/api/files.completeUploadExternal",
            headers=headers,
            json={"files": [{"id": file_id}], "channel_id": channel_id, "initial_comment": ticker},
            timeout=30,
        )
        complete_data = complete_resp.json()
        if complete_resp.status_code >= 500:
            logger.error("files.completeUploadExternal HTTP %d: %s", complete_resp.status_code, ticker)
            return False
        if not complete_data.get("ok"):
            logger.error("files.completeUploadExternal 失敗: %s — %s", ticker, complete_data.get("error"))
            return False
    except Exception:
        logger.exception("files.completeUploadExternal エラー: %s", ticker)
        return False

    logger.info("チャートアップロード完了: %s (file_id=%s)", ticker, file_id)
    return True


def notify(
    predictions_df: pd.DataFrame,
    accuracy: dict | None = None,
    config: dict | None = None,
    tickers_for_chart: list[str] | None = None,
) -> bool:
    """レポートを生成してSlackに送信し、LINE でチェックを促す。

    Args:
        predictions_df: predictor.predict() の出力。
        accuracy: tracker.calculate_accuracy() の出力。
        config: 設定辞書。
        tickers_for_chart: チャートを生成・送信する銘柄リスト。None の場合はチャート送信しない。
    """
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

    # チャート添付（Bot Token 方式）
    notif_cfg = config.get("notifications", {})
    slack_chart_enabled = notif_cfg.get("slack_chart", False)
    chart_ok = True

    if tickers_for_chart and slack_chart_enabled:
        bot_token = os.environ.get("SLACK_BOT_TOKEN")
        if not bot_token:
            logger.info("SLACK_BOT_TOKEN 未設定のためチャートアップロードをスキップ")
        else:
            # チャンネル ID 解決
            channel_id = notif_cfg.get("slack_channel_id", "")
            if not channel_id:
                channel_id = _resolve_channel_id(
                    config.get("slack", {}).get("channel", "#stock-alerts"),
                    bot_token,
                )
            if not channel_id:
                logger.warning("チャンネル ID を解決できません。チャートアップロードをスキップ")
            else:
                from src import chart_builder

                lookback_days = config.get("screening", {}).get("lookback_days", 252)
                for ticker in tickers_for_chart:
                    try:
                        chart_bytes = chart_builder.build_stock_chart(ticker, lookback_days, config)
                    except Exception:
                        logger.exception("チャート生成エラー: %s", ticker)
                        chart_bytes = None

                    if chart_bytes is None:
                        logger.info("チャートデータなし: %s — スキップ", ticker)
                        continue

                    success = _upload_chart_to_slack(ticker, chart_bytes, channel_id, bot_token)
                    if not success:
                        chart_ok = False

    return slack_ok and chart_ok
