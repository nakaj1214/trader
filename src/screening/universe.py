"""Universe loader: reads stock ticker lists from CSV files.

Supports both new (data/universes/) and legacy (data/) paths
for backward compatibility during migration.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import structlog

from src.core.config import ROOT_DIR

logger = structlog.get_logger(__name__)

UNIVERSES_DIR: Path = ROOT_DIR / "data" / "universes"
LEGACY_DATA_DIR: Path = ROOT_DIR / "data"
SUPPORTED_MARKETS: tuple[str, ...] = ("sp500", "nasdaq100", "nikkei225")


def load_universe(market: str) -> list[str]:
    """Load stock tickers for a single market from a CSV file.

    Looks in data/universes/<market>.csv first, then falls back to
    data/<market>.csv for backward compatibility.

    Args:
        market: Market identifier (e.g. "sp500", "nasdaq100", "nikkei225").

    Returns:
        Deduplicated list of ticker strings. Empty list if file is missing.
    """
    csv_path = _resolve_csv_path(market)
    if csv_path is None:
        logger.warning(
            "ticker_list_not_found",
            market=market,
            searched=[str(UNIVERSES_DIR / f"{market}.csv"), str(LEGACY_DATA_DIR / f"{market}.csv")],
        )
        return []
    return _read_tickers(csv_path)


def load_all_universes(markets: list[str]) -> dict[str, list[str]]:
    """Load ticker lists for multiple markets.

    Returns:
        Mapping of market name to deduplicated ticker list.
    """
    return {market: load_universe(market) for market in markets}


def _resolve_csv_path(market: str) -> Path | None:
    """Return the first existing CSV path for the market, or None."""
    candidates: list[Path] = [
        UNIVERSES_DIR / f"{market}.csv",
        LEGACY_DATA_DIR / f"{market}.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _read_tickers(csv_path: Path) -> list[str]:
    """Read and deduplicate tickers from a CSV file."""
    try:
        df = pd.read_csv(csv_path)
    except Exception as exc:
        logger.warning("csv_read_error", path=str(csv_path), error=str(exc))
        return []

    if "ticker" not in df.columns:
        logger.warning("csv_missing_ticker_column", path=str(csv_path), columns=list(df.columns))
        return []

    raw: list[str] = df["ticker"].dropna().tolist()
    return list(dict.fromkeys(raw))
