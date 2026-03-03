"""Chart builder: generate stock charts as PNG bytes.

Migrated from src/chart_builder.py. Produces Close + SMA + Bollinger Band
+ volume charts for Slack Bot Token uploads.
"""

from __future__ import annotations

import io
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

CALENDAR_DAY_FACTOR = 1.5


def build_stock_chart(
    ticker: str,
    lookback_days: int,
    config: dict[str, Any],
) -> bytes | None:
    """Generate a stock chart as PNG bytes.

    Creates a two-panel chart with price (Close + SMA + BB) on top
    and volume on bottom.

    Args:
        ticker: Stock ticker symbol.
        lookback_days: Config lookback_days (kept for compatibility).
        config: App config. Uses notification.chart_lookback_days.

    Returns:
        PNG bytes, or None if data is insufficient (< 20 bars).
    """
    import pandas as pd
    import ta
    import yfinance as yf

    chart_display_days = config.get("notification", {}).get("chart_lookback_days", 60)

    chart_fetch_days = max(chart_display_days, 252)
    chart_fetch_period = f"{int(chart_fetch_days * CALENDAR_DAY_FACTOR)}d"

    try:
        df = yf.download(ticker, period=chart_fetch_period, progress=False, auto_adjust=True)
    except Exception:
        logger.exception("chart_data_fetch_error", ticker=ticker)
        return None

    if df.empty or len(df) < 20:
        logger.warning("chart_data_insufficient", ticker=ticker, bars=len(df))
        return None

    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()

    sma20 = close.rolling(20).mean().tail(chart_display_days)
    sma50 = close.rolling(50).mean().tail(chart_display_days)
    sma200 = close.rolling(200).mean().tail(chart_display_days) if len(close) >= 200 else None

    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().tail(chart_display_days)
    bb_lower = bb.bollinger_lband().tail(chart_display_days)

    display_close = close.tail(chart_display_days)
    display_volume = volume.tail(chart_display_days)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]}
    )
    fig.suptitle(f"{ticker} — Last {chart_display_days} days", fontsize=14)

    ax1.plot(display_close.index, display_close.values, label="Close", color="black", linewidth=1.5)
    ax1.plot(sma20.index, sma20.values, label="SMA20", color="blue", linewidth=1.0, alpha=0.8)
    ax1.plot(sma50.index, sma50.values, label="SMA50", color="orange", linewidth=1.0, alpha=0.8)
    if sma200 is not None:
        ax1.plot(sma200.index, sma200.values, label="SMA200", color="red", linewidth=1.0, alpha=0.8)
    ax1.fill_between(
        bb_upper.index, bb_upper.values, bb_lower.values, alpha=0.1, color="gray", label="BB"
    )
    ax1.plot(bb_upper.index, bb_upper.values, color="gray", linewidth=0.5, linestyle="--")
    ax1.plot(bb_lower.index, bb_lower.values, color="gray", linewidth=0.5, linestyle="--")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylabel("Price", fontsize=8)

    ax2.bar(display_volume.index, display_volume.values, color="steelblue", alpha=0.7)
    ax2.set_ylabel("Volume", fontsize=8)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()
