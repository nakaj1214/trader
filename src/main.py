"""メインオーケストレーター

全ステップを順番に実行する。
1. 自動スクリーニング (screener)
2. AI価格予測 (predictor)
3. 前週の的中率追跡 (tracker)
4. Googleスプレッドシート記録 (sheets)
5. Slack通知 (notifier)
"""

import logging
import sys

from src.utils import load_config

logger = logging.getLogger(__name__)


def run() -> None:
    """ワークフロー全体を実行する。"""
    config = load_config()

    # ステップ1: 自動スクリーニング
    logger.info("=" * 50)
    logger.info("ステップ1: 自動スクリーニング")
    logger.info("=" * 50)
    from src.screener import screen

    screened = screen(config)
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
