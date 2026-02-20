"""メインオーケストレーター

全ステップを順番に実行する。
1. 自動スクリーニング (screener)
2. AI価格予測 (predictor)
3. 前週の的中率追跡 (tracker)
4. Googleスプレッドシート記録 (sheets)
5. Slack通知 (notifier)
6. ダッシュボードデータエクスポート (exporter)
"""

import logging
import sys

from src.utils import load_config

logger = logging.getLogger(__name__)


def run() -> None:
    """ワークフロー全体を実行する。"""
    config = load_config()

    # ステップ1: 自動スクリーニング（米国株）
    logger.info("=" * 50)
    logger.info("ステップ1: 自動スクリーニング（米国株）")
    logger.info("=" * 50)
    from src.screener import screen

    # 米国株: sp500 / nasdaq100 のみ対象
    us_markets = [m for m in config["screening"]["markets"] if m != "nikkei225"]
    screened = screen(config, market=None)  # 後続ステップ(predict/sheets/notify)は米国株のみ

    # Phase 15: 日本株スクリーニングを独立フローで実行（失敗しても米国株フローに影響しない）
    if "nikkei225" in config["screening"]["markets"]:
        logger.info("=" * 50)
        logger.info("ステップ1-JP: 自動スクリーニング（日本株）")
        logger.info("=" * 50)
        try:
            jp_screened = screen(config, market="nikkei225")
            if jp_screened.empty:
                logger.warning("日本株スクリーニング結果が空です")
            else:
                logger.info("日本株トップ%d:", len(jp_screened))
                for _, row in jp_screened.iterrows():
                    logger.info(
                        "  %s: ¥%.0f (スコア: %.4f)",
                        row["ticker"], row["current_price"], row["score"],
                    )
        except Exception:
            logger.exception("日本株スクリーニングでエラーが発生しましたが、米国株フローを続行します")

    if screened.empty:
        logger.error("スクリーニング結果が空のため、処理を中断します")
        return

    logger.info("成長株トップ%d:", len(screened))
    for _, row in screened.iterrows():
        logger.info("  %s: $%.2f (スコア: %.4f)", row["ticker"], row["current_price"], row["score"])

    # ステップ2: AI価格予測
    logger.info("=" * 50)
    logger.info("ステップ2: AI価格予測 (Prophet)")
    logger.info("=" * 50)
    from src.predictor import predict

    predictions = predict(screened, config)
    if predictions.empty:
        logger.warning("上昇予測の銘柄がありません")

    for _, row in predictions.iterrows():
        logger.info(
            "  %s: $%.2f → $%.2f (+%.1f%%)",
            row["ticker"],
            row["current_price"],
            row["predicted_price"],
            row["predicted_change_pct"],
        )

    # ステップ4: 前週の的中率追跡
    logger.info("=" * 50)
    logger.info("ステップ4: 前週比較・的中率追跡")
    logger.info("=" * 50)
    accuracy = None
    try:
        from src.tracker import track

        accuracy = track(config)
        if accuracy["total"] > 0:
            logger.info(
                "先週の的中率: %d/%d (%.1f%%)",
                accuracy["hits"],
                accuracy["total"],
                accuracy["hit_rate_pct"],
            )
        else:
            logger.info("前週の予測データなし（初回実行）")
    except Exception:
        logger.exception("的中率追跡でエラーが発生しましたが、処理を続行します")

    # ステップ3: Googleスプレッドシート記録
    logger.info("=" * 50)
    logger.info("ステップ3: Googleスプレッドシート記録")
    logger.info("=" * 50)
    try:
        from src.sheets import append_predictions

        if not predictions.empty:
            rows_added = append_predictions(predictions, config)
            logger.info("スプレッドシートに %d 行追記", rows_added)
        else:
            logger.info("記録する予測データなし")
    except Exception:
        logger.exception("スプレッドシート記録でエラーが発生しましたが、処理を続行します")

    # ステップ5: Slack通知
    logger.info("=" * 50)
    logger.info("ステップ5: Slack通知")
    logger.info("=" * 50)
    try:
        from src.notifier import notify

        success = notify(predictions, accuracy, config)
        if success:
            logger.info("Slack通知完了")
        else:
            logger.error("Slack通知失敗")
    except Exception:
        logger.exception("Slack通知でエラーが発生しました")

    # ステップ6: ダッシュボードデータエクスポート
    logger.info("=" * 50)
    logger.info("ステップ6: ダッシュボードデータエクスポート")
    logger.info("=" * 50)
    try:
        from src.exporter import export

        export_ok = export(config)
        if export_ok:
            logger.info("ダッシュボードデータエクスポート完了")
        else:
            logger.warning("ダッシュボードデータエクスポートに問題が発生しました")
    except Exception:
        logger.exception("エクスポートでエラーが発生しましたが、処理を続行します")

    # ステップ7: アルファサーベイ（アノマリー統計検証）
    logger.info("=" * 50)
    logger.info("ステップ7: アルファサーベイ")
    logger.info("=" * 50)
    try:
        from src.alpha_survey import run_and_export as run_alpha_survey

        run_alpha_survey()
        logger.info("アルファサーベイ完了")
    except Exception:
        logger.exception("アルファサーベイでエラーが発生しましたが、処理を続行します")

    logger.info("=" * 50)
    logger.info("全ステップ完了")
    logger.info("=" * 50)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    run()
