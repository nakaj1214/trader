"""ステップ2: AI価格予測 (Phase 1: Prophet)

スクリーニングで選出された銘柄について、Prophetで来週の株価を予測する。
上昇予測の銘柄のみをフィルタリングし、信頼区間付きで返す。
"""

import logging
import math
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from prophet import Prophet

from src.utils import load_config

logger = logging.getLogger(__name__)


def compute_prob_up(predicted_change_pct: float, ci_pct: float) -> float:
    """予測上昇率と信頼区間から上昇確率を正規分布近似で算出する。

    モデルの予測値 μ = predicted_change_pct、95% CI 半幅 = ci_pct から
    σ = ci_pct / 1.96 を逆算し、P(X > 0) = Φ(μ / σ) を返す。

    Args:
        predicted_change_pct: 予測上昇率（%）
        ci_pct: 95% 信頼区間の半幅（%）

    Returns:
        上昇確率 [0.0, 1.0]
    """
    if ci_pct <= 0:
        return 1.0 if predicted_change_pct > 0 else 0.0
    sigma = ci_pct / 1.96
    z = predicted_change_pct / sigma
    return round(0.5 * (1 + math.erf(z / math.sqrt(2))), 4)


def fetch_history(ticker: str, days: int) -> pd.DataFrame:
    """yfinance で過去N日の終値データを Prophet 形式 (ds, y) で返す。"""
    end = datetime.now()
    start = end - timedelta(days=days)
    df = yf.download(ticker, start=start, end=end, progress=False)
    if df.empty:
        return pd.DataFrame()

    close = df["Close"].squeeze()
    prophet_df = pd.DataFrame({
        "ds": close.index.tz_localize(None),
        "y": close.values,
    })
    return prophet_df.dropna().reset_index(drop=True)


def predict_stock(ticker: str, history_days: int, forecast_days: int) -> dict | None:
    """1銘柄についてProphetで予測を行う。

    Returns:
        dict with keys: ticker, current_price, predicted_price,
                        predicted_change_pct, ci_lower, ci_upper, ci_pct
        or None if prediction fails.
    """
    df = fetch_history(ticker, history_days)
    if df.empty or len(df) < 30:
        logger.warning("%s: データ不足 (%d行), スキップ", ticker, len(df))
        return None

    current_price = float(df["y"].iloc[-1])

    try:
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=True,
            changepoint_prior_scale=0.05,
        )
        model.fit(df)

        # 将来の営業日を作成 (freq="B" で営業日基準)
        future = model.make_future_dataframe(periods=forecast_days, freq="B")
        forecast = model.predict(future)

        # 予測期間の最終日の値を取得
        last_row = forecast.iloc[-1]
        predicted_price = float(last_row["yhat"])
        ci_lower = float(last_row["yhat_lower"])
        ci_upper = float(last_row["yhat_upper"])

        predicted_change_pct = (predicted_price - current_price) / current_price * 100
        ci_pct = (ci_upper - ci_lower) / 2 / current_price * 100

        return {
            "ticker": ticker,
            "current_price": round(current_price, 2),
            "predicted_price": round(predicted_price, 2),
            "predicted_change_pct": round(predicted_change_pct, 2),
            "ci_lower": round(ci_lower, 2),
            "ci_upper": round(ci_upper, 2),
            "ci_pct": round(ci_pct, 2),
            "prob_up": compute_prob_up(predicted_change_pct, ci_pct),
            "prob_up_calibrated": None,
        }
    except Exception:
        logger.exception("%s: Prophet予測エラー", ticker)
        return None


def predict(screened_df: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    """スクリーニング結果の全銘柄に対して予測を実行し、上昇予測のみ返す。

    Args:
        screened_df: screener.screen() の出力。ticker列が必要。
        config: 設定辞書。Noneなら config.yaml を読み込む。

    Returns:
        DataFrame with columns:
            ticker, current_price, predicted_price, predicted_change_pct,
            ci_lower, ci_upper, ci_pct
        上昇予測 (predicted_change_pct > 0) のみ、上昇率降順。
    """
    if config is None:
        config = load_config()

    pred_cfg = config["prediction"]
    history_days = pred_cfg.get("history_days", 90)
    forecast_days = pred_cfg.get("forecast_days", 5)

    tickers = screened_df["ticker"].tolist()
    logger.info("予測開始: %d 銘柄", len(tickers))

    results = []
    for ticker in tickers:
        logger.info("予測中: %s", ticker)
        result = predict_stock(ticker, history_days, forecast_days)
        if result is not None:
            results.append(result)

    if not results:
        logger.warning("予測結果が空です")
        return pd.DataFrame()

    result_df = pd.DataFrame(results)

    # 上昇予測のみフィルタリング
    bullish_df = result_df[result_df["predicted_change_pct"] > 0].copy()
    bullish_df = bullish_df.sort_values("predicted_change_pct", ascending=False)
    bullish_df = bullish_df.reset_index(drop=True)

    logger.info(
        "予測完了: %d/%d 銘柄が上昇予測",
        len(bullish_df),
        len(result_df),
    )
    return bullish_df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from src.screener import screen

    screened = screen()
    if not screened.empty:
        predictions = predict(screened)
        if not predictions.empty:
            print("\n=== 上昇予測銘柄 ===")
            print(predictions.to_string(index=False))
        else:
            print("上昇予測の銘柄はありません")
