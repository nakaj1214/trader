"""ステップ4: 前週比較・的中率追跡

先週の予測と実績を比較し、的中率を計算する。
判定基準: 対象市場の最終営業日終値 (Close)。
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from src.sheets import get_client, get_or_create_worksheet
from src.utils import load_config

logger = logging.getLogger(__name__)


def _evaluation_date(prediction_date: str, forecast_days: int = 5) -> datetime:
    """予測日から評価日を算出する。

    forecast_days 営業日分を予測日から進めた日を評価日とする。
    休場日 (土日) はスキップして営業日のみカウントする。
    """
    pred_dt = datetime.strptime(prediction_date, "%Y-%m-%d")
    current = pred_dt
    bdays_added = 0
    while bdays_added < forecast_days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # 月〜金
            bdays_added += 1
    return current


def fetch_close_at(
    tickers: list[str], target_date: str, forecast_days: int = 5
) -> dict[str, float]:
    """各銘柄の予測日から forecast_days 取引日後の終値を取得する。

    yfinance の実取引日データから N 番目の取引日を直接カウントするため、
    祝日を含む週でも正しく評価される。
    """
    if not tickers:
        return {}

    pred_dt = datetime.strptime(target_date, "%Y-%m-%d")
    # 取得窓: 予測日の翌日〜 forecast_days*2+14 日後 (祝日・連休バッファ)
    start = pred_dt
    end = pred_dt + timedelta(days=forecast_days * 2 + 14)

    prices: dict[str, float] = {}
    batch_str = " ".join(tickers)
    try:
        df = yf.download(batch_str, start=start, end=end, progress=False)
    except Exception:
        logger.exception("終値取得エラー (予測日: %s)", target_date)
        return {}

    for ticker in tickers:
        try:
            if len(tickers) == 1:
                close = df["Close"].squeeze().dropna()
            else:
                close = df[ticker]["Close"].squeeze().dropna()
            if close.empty:
                continue
            # 予測日より後の実取引日を抽出し、forecast_days 番目を取得
            trading_after = close[close.index > pd.Timestamp(pred_dt)]
            if len(trading_after) >= forecast_days:
                prices[ticker] = float(trading_after.iloc[forecast_days - 1])
        except (KeyError, TypeError):
            continue

    logger.info(
        "終値取得 (予測日: %s, %d取引日後): %d/%d 銘柄",
        target_date, forecast_days, len(prices), len(tickers),
    )
    return prices


def get_pending_predictions(config: dict | None = None) -> tuple[list[dict], str]:
    """スプレッドシートから前週分の「予測済み」行を取得する。

    Returns:
        (前週の未確定行リスト, 前週の予測日文字列)
    """
    if config is None:
        config = load_config()

    sheets_cfg = config["google_sheets"]
    client = get_client()
    ws = get_or_create_worksheet(
        client, sheets_cfg["spreadsheet_name"], sheets_cfg["worksheet_name"]
    )

    all_records = ws.get_all_records()
    pending = [r for r in all_records if r.get("ステータス") == "予測済み"]

    if not pending:
        return [], ""

    # 前週 = 未確定行のうち最も古い日付 [#2: 前週限定]
    dates = sorted(set(r["日付"] for r in pending))
    target_date = dates[0]
    last_week_rows = [r for r in pending if r["日付"] == target_date]
    return last_week_rows, target_date


def calculate_accuracy(config: dict | None = None) -> dict:
    """全データから的中率を計算する。

    Returns:
        {
            "hits": 今週の的中数,
            "misses": 今週の外れ数,
            "total": 今週の判定対象数,
            "hit_rate_pct": 今週の的中率(%),
            "cumulative_hits": 累計的中数,
            "cumulative_total": 累計判定対象数,
            "cumulative_hit_rate_pct": 累計的中率(%),
            "cumulative_weeks": 累計の週数,
        }
    """
    if config is None:
        config = load_config()

    sheets_cfg = config["google_sheets"]
    client = get_client()
    ws = get_or_create_worksheet(
        client, sheets_cfg["spreadsheet_name"], sheets_cfg["worksheet_name"]
    )

    all_records = ws.get_all_records()
    # 「的中」「外れ」のみを判定対象とし、「評価不能」は分母から除外する
    evaluable = [
        r for r in all_records
        if r.get("ステータス") == "確定済み" and r.get("的中") in ("的中", "外れ")
    ]

    if not evaluable:
        return {
            "hits": 0, "misses": 0, "total": 0, "hit_rate_pct": 0.0,
            "cumulative_hits": 0, "cumulative_total": 0,
            "cumulative_hit_rate_pct": 0.0, "cumulative_weeks": 0,
        }

    # 累計 (評価不能を除外)
    cumulative_hits = sum(1 for r in evaluable if r["的中"] == "的中")
    cumulative_total = len(evaluable)
    cumulative_hit_rate = cumulative_hits / cumulative_total * 100

    # 直近の日付: 「確定済み」全件ベースで決める (評価不能のみの週も含む)
    all_confirmed = [r for r in all_records if r.get("ステータス") == "確定済み"]
    confirmed_dates = sorted(set(r["日付"] for r in all_confirmed))
    latest_date = confirmed_dates[-1] if confirmed_dates else ""

    # 今週分の評価可能レコード (最新週が全件「評価不能」なら total=0)
    dates = sorted(set(r["日付"] for r in evaluable))
    this_week = [r for r in evaluable if r["日付"] == latest_date]
    hits = sum(1 for r in this_week if r["的中"] == "的中")
    total = len(this_week)
    hit_rate = hits / total * 100 if total > 0 else 0.0

    return {
        "hits": hits,
        "misses": total - hits,
        "total": total,
        "hit_rate_pct": round(hit_rate, 1),
        "cumulative_hits": cumulative_hits,
        "cumulative_total": cumulative_total,
        "cumulative_hit_rate_pct": round(cumulative_hit_rate, 1),
        "cumulative_weeks": len(dates),
    }


def close_unfetched(
    all_tickers: list[str],
    fetched_prices: dict[str, float],
    target_date: str,
    config: dict | None = None,
) -> int:
    """価格未取得の銘柄を「評価不能」でクローズし、未確定週が固定されるのを防ぐ。

    Returns:
        クローズした行数。
    """
    unfetched = set(all_tickers) - set(fetched_prices.keys())
    if not unfetched:
        return 0

    if config is None:
        config = load_config()

    sheets_cfg = config["google_sheets"]
    client = get_client()
    ws = get_or_create_worksheet(
        client, sheets_cfg["spreadsheet_name"], sheets_cfg["worksheet_name"]
    )

    all_records = ws.get_all_records()
    closed = 0

    for i, record in enumerate(all_records):
        row_num = i + 2
        if record["ステータス"] != "予測済み":
            continue
        if record["日付"] != target_date:
            continue
        if record["ティッカー"] not in unfetched:
            continue

        ws.update_cell(row_num, 7, "N/A")          # 翌週実績価格
        ws.update_cell(row_num, 8, "評価不能")       # 的中
        ws.update_cell(row_num, 9, "確定済み")        # ステータス
        closed += 1

    if closed:
        logger.warning("価格未取得のため評価不能としてクローズ: %d 行 (%s)", closed, ", ".join(unfetched))
    return closed


def track(config: dict | None = None) -> dict:
    """前週の予測に対する実績を更新し、的中率を返す。

    1. 「予測済み」の銘柄の最終営業日終値を取得
    2. スプレッドシートの実績列を更新
    3. 的中率を算出して返す
    """
    if config is None:
        config = load_config()

    from src.sheets import update_actuals

    # 前週の未確定予測を取得 [#2: 前週限定]
    pending, target_date = get_pending_predictions(config)
    if not pending:
        logger.info("未確定の予測はありません")
        return calculate_accuracy(config)

    forecast_days = config.get("prediction", {}).get("forecast_days", 5)
    logger.info("対象予測日: %s (%d 行, forecast_days=%d)", target_date, len(pending), forecast_days)

    # 予測日ベースで評価対象日の終値を取得
    tickers = list(set(r["ティッカー"] for r in pending))
    actual_prices = fetch_close_at(tickers, target_date, forecast_days)

    # スプレッドシート更新 (対象日のみ)
    # 価格未取得の銘柄は「評価不能」でクローズして次週に進む
    updated = update_actuals(actual_prices, target_date, config)
    close_unfetched(tickers, actual_prices, target_date, config)
    logger.info("実績更新: %d 行", updated)

    # 的中率計算
    accuracy = calculate_accuracy(config)
    logger.info(
        "的中率: %d/%d (%s%%)",
        accuracy["hits"],
        accuracy["total"],
        accuracy["hit_rate_pct"],
    )
    return accuracy
