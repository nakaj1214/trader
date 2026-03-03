"""Stock scoring, top-N selection, and main screen() orchestrator.

Integrates universe loading, filtering, indicator computation,
and weighted scoring into a single pipeline.
"""

from __future__ import annotations

import time

import pandas as pd
import structlog
import yfinance as yf

from src.screening.filters import FilterChain
from src.screening.indicators import (
    calc_52w_high_momentum,
    calc_adx,
    calc_bollinger_position,
    calc_macd_signal,
    calc_price_change_1m,
    calc_rsi,
    calc_volume_trend,
)
from src.screening.universe import load_all_universes

logger = structlog.get_logger(__name__)

DEFAULT_WEIGHTS: dict[str, float] = {
    "price_change_1m": 0.20,
    "volume_trend": 0.15,
    "rsi_score": 0.15,
    "macd_signal": 0.15,
    "fifty2w_score": 0.15,
    "bb_position": 0.10,
    "adx_score": 0.10,
}

BATCH_SIZE = 50
CALENDAR_DAY_FACTOR = 1.5


def score_stocks(indicators: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Compute weighted composite score for each stock."""
    scores = pd.Series(0.0, index=indicators.index)

    if "price_change_1m" in indicators.columns:
        scores += weights.get("price_change_1m", 0.0) * indicators["price_change_1m"].clip(lower=0.0)

    if "volume_trend" in indicators.columns:
        scores += weights.get("volume_trend", 0.0) * indicators["volume_trend"].clip(lower=0.0)

    if "rsi" in indicators.columns:
        scores += weights.get("rsi_score", 0.0) * _rsi_to_score(indicators["rsi"])

    if "macd_bullish" in indicators.columns:
        scores += weights.get("macd_signal", 0.0) * indicators["macd_bullish"]

    if "bb_pos" in indicators.columns:
        scores += weights.get("bb_position", 0.0) * indicators["bb_pos"].clip(lower=0.0, upper=1.0)

    if "adx_score" in indicators.columns:
        scores += weights.get("adx_score", 0.0) * indicators["adx_score"]

    if "fifty2w_score" in indicators.columns:
        scores += weights.get("fifty2w_score", 0.0) * indicators["fifty2w_score"].fillna(0.0)

    return scores


def select_top_n(scores: pd.Series, n: int) -> list[str]:
    """Return top-N ticker symbols by score."""
    if scores.empty:
        return []
    return scores.nlargest(n).index.tolist()


def screen(config: dict, market: str = "us") -> pd.DataFrame:
    """Full screening pipeline: universe -> filter -> indicators -> score -> top-N.

    Args:
        config: Full application config dict.
        market: Market to screen, or "us" for all configured markets.

    Returns:
        DataFrame of top-N stocks with indicator columns and scores.
    """
    screening_cfg = config.get("screening", {})
    markets = _resolve_markets(market, screening_cfg)
    top_n: int = screening_cfg.get("top_n", 10)

    universe_map = load_all_universes(markets)
    all_tickers: list[str] = []
    for ticker_list in universe_map.values():
        all_tickers.extend(ticker_list)
    all_tickers = list(dict.fromkeys(all_tickers))

    if not all_tickers:
        logger.warning("empty_universe", markets=markets)
        return pd.DataFrame()

    logger.info("universe_loaded", count=len(all_tickers), markets=markets)

    lookback_days: int = screening_cfg.get("lookback_days", 252)
    stock_data = _fetch_price_data(all_tickers, lookback_days)

    if not stock_data:
        logger.warning("no_price_data")
        return pd.DataFrame()

    stock_df = _build_filter_dataframe(stock_data)
    filter_chain = FilterChain()
    filtered_df = filter_chain.apply(stock_df, screening_cfg)
    remaining = filtered_df["ticker"].tolist()

    if not remaining:
        logger.warning("all_filtered_out")
        return pd.DataFrame()

    logger.info("filters_applied", remaining=len(remaining))

    rows: list[dict] = []
    for ticker in remaining:
        prices = stock_data.get(ticker)
        if prices is None:
            continue
        row = _compute_indicator_row(ticker, prices)
        if row:
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    indicators_df = pd.DataFrame(rows).set_index("ticker")

    weights = (
        screening_cfg.get("scoring", {}).get("weights")
        or screening_cfg.get("weights")
        or DEFAULT_WEIGHTS
    )
    scores = score_stocks(indicators_df, weights)

    if _golden_cross_enabled(screening_cfg):
        gc_col = indicators_df.get("golden_cross")
        if gc_col is not None:
            death_mask = gc_col.notna() & (gc_col == 0.0)
            scores[death_mask] = 0.0

    top_tickers = select_top_n(scores, top_n)
    result = indicators_df.loc[top_tickers].copy()
    result["score"] = scores[top_tickers]
    result = result.reset_index().sort_values("score", ascending=False).reset_index(drop=True)

    logger.info("screening_complete", top_n=len(result))
    return result


def _resolve_markets(market: str, cfg: dict) -> list[str]:
    if market == "us":
        return cfg.get("markets", ["sp500", "nasdaq100"])
    return [market]


def _fetch_price_data(tickers: list[str], lookback_days: int) -> dict[str, pd.DataFrame]:
    """Fetch OHLCV data in batches via yfinance."""
    period = f"{int(lookback_days * CALENDAR_DAY_FACTOR)}d"
    data: dict[str, pd.DataFrame] = {}

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        batch_str = " ".join(batch)
        logger.info("fetching_batch", progress=f"{min(i + BATCH_SIZE, len(tickers))}/{len(tickers)}")

        try:
            raw = yf.download(batch_str, period=period, group_by="ticker", progress=False)
        except Exception as exc:
            logger.warning("batch_error", start=i, error=str(exc))
            continue

        for ticker in batch:
            try:
                df = raw.copy() if len(batch) == 1 else raw[ticker].copy()
                if df.empty or df["Close"].dropna().empty:
                    continue
                data[ticker] = df.dropna(subset=["Close"])
            except (KeyError, TypeError):
                continue

        if i + BATCH_SIZE < len(tickers):
            time.sleep(1)

    logger.info("fetch_done", fetched=len(data), total=len(tickers))
    return data


def _build_filter_dataframe(stock_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build DataFrame with filter columns for each ticker."""
    rows: list[dict] = []
    for ticker, df in stock_data.items():
        close = df["Close"].squeeze()
        volume = df["Volume"].squeeze() if "Volume" in df.columns else None
        addv = float((volume * close).mean()) if volume is not None and not volume.empty else None

        golden_cross: float | None = None
        if len(close) >= 200:
            sma50 = close.rolling(50).mean().iloc[-1]
            sma200 = close.rolling(200).mean().iloc[-1]
            if not (pd.isna(sma50) or pd.isna(sma200)):
                golden_cross = 1.0 if float(sma50) > float(sma200) else 0.0

        rows.append({
            "ticker": ticker,
            "avg_dollar_volume": addv,
            "golden_cross": golden_cross,
            "market_cap": None,
        })

    return pd.DataFrame(rows)


def _compute_indicator_row(ticker: str, prices: pd.DataFrame) -> dict:
    """Compute all indicators for a single ticker."""
    close = prices["Close"].squeeze()
    if close.dropna().shape[0] < 14:
        return {}

    def _scalar(series: pd.Series) -> float | None:
        return float(series.iloc[-1]) if not series.empty else None

    golden_cross: float | None = None
    if len(close) >= 200:
        sma50 = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        if not (pd.isna(sma50) or pd.isna(sma200)):
            golden_cross = 1.0 if float(sma50) > float(sma200) else 0.0

    row: dict = {
        "ticker": ticker,
        "current_price": float(close.iloc[-1]),
        "price_change_1m": _scalar(calc_price_change_1m(prices)),
        "volume_trend": _scalar(calc_volume_trend(prices)),
        "rsi": _scalar(calc_rsi(prices)),
        "macd_bullish": _scalar(calc_macd_signal(prices)),
        "golden_cross": golden_cross,
        "bb_pos": _scalar(calc_bollinger_position(prices)),
        "adx_score": _scalar(calc_adx(prices)),
        "fifty2w_score": _scalar(calc_52w_high_momentum(prices)),
    }

    if all(row.get(k) is None for k in ("price_change_1m", "rsi", "macd_bullish")):
        return {}

    return row


def _rsi_to_score(rsi: pd.Series) -> pd.Series:
    """Convert RSI to [0, 1] score: 1.0 for 40-60, 0.5 for 30-70, else 0."""
    score = pd.Series(0.0, index=rsi.index)
    score[(rsi >= 30) & (rsi <= 70)] = 0.5
    score[(rsi >= 40) & (rsi <= 60)] = 1.0
    return score


def _golden_cross_enabled(cfg: dict) -> bool:
    filters = cfg.get("filters", {})
    gc = filters.get("golden_cross", {})
    if isinstance(gc, dict) and "enabled" in gc:
        return bool(gc["enabled"])
    return bool(cfg.get("use_golden_cross_filter", True))
