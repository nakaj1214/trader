"""Deterministic market-data validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    detail: str


def is_finite_number(value: Any) -> bool:
    """True for a real, finite int/float; bool is excluded even though it subclasses int."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def validate_ohlcv(df: pd.DataFrame, *, require_volume: bool = True) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if df.empty:
        return [ValidationIssue("EMPTY", "No rows")]

    if not df.index.is_monotonic_increasing:
        issues.append(ValidationIssue("UNSORTED_INDEX", "Index is not sorted ascending"))
    try:
        dates = pd.DatetimeIndex(pd.to_datetime(df.index, format="mixed")).tz_localize(None).normalize()
        if dates.hasnans:
            issues.append(ValidationIssue("INVALID_INDEX", "Missing trading date"))
    except (TypeError, ValueError):
        issues.append(ValidationIssue("INVALID_INDEX", "Invalid trading date"))
        dates = df.index
    if dates.has_duplicates:
        issues.append(ValidationIssue("DUPLICATE_INDEX", "Duplicate trading dates detected"))

    required = ["Open", "High", "Low", "Close"]
    if require_volume or "Volume" in df.columns:
        required.append("Volume")
    missing = [col for col in required if col not in df.columns]
    if missing:
        issues.append(ValidationIssue("MISSING_COLUMNS", ",".join(missing)))
        return issues

    numeric = df[required].apply(pd.to_numeric, errors="coerce")
    if numeric[["Open", "High", "Low", "Close"]].isna().any().any():
        issues.append(ValidationIssue("PRICE_NAN", "OHLC contains non-numeric or missing values"))
    if numeric[["Open", "High", "Low", "Close"]].isin([float("inf"), float("-inf")]).any().any():
        issues.append(ValidationIssue("PRICE_NONFINITE", "OHLC contains infinite values"))
    if "Volume" in numeric and numeric["Volume"].isna().any():
        issues.append(ValidationIssue("VOLUME_NAN", "Volume contains non-numeric or missing values"))
    if "Volume" in numeric and numeric["Volume"].isin([float("inf"), float("-inf")]).any():
        issues.append(ValidationIssue("VOLUME_NONFINITE", "Volume contains infinite values"))
    if "Adj Close" in df:
        adjusted = pd.to_numeric(df["Adj Close"], errors="coerce")
        if adjusted.isna().any() or not adjusted.dropna().map(isfinite).all() or (adjusted <= 0).any():
            issues.append(ValidationIssue("ADJUSTED_PRICE_INVALID", "Adjusted close must be finite and positive"))
    if "Turnover" in df:
        turnover = pd.to_numeric(df["Turnover"], errors="coerce")
        if turnover.isna().any() or not turnover.dropna().map(isfinite).all() or (turnover < 0).any():
            issues.append(ValidationIssue("TURNOVER_INVALID", "Turnover must be finite and nonnegative"))

    valid = numeric.dropna(subset=["Open", "High", "Low", "Close"])
    if not valid.empty:
        # Adjustment multiplication can differ from Adj Close by a few floating-point bits.
        bad_high = (valid["High"] < valid[["Open", "Close", "Low"]].max(axis=1) * (1 - 1e-12)).sum()
        bad_low = (valid["Low"] > valid[["Open", "Close", "High"]].min(axis=1) * (1 + 1e-12)).sum()
        nonpositive = (valid[["Open", "High", "Low", "Close"]] <= 0).any(axis=1).sum()
        if bad_high:
            issues.append(ValidationIssue("HIGH_INCONSISTENT", f"{int(bad_high)} rows"))
        if bad_low:
            issues.append(ValidationIssue("LOW_INCONSISTENT", f"{int(bad_low)} rows"))
        if nonpositive:
            issues.append(ValidationIssue("NONPOSITIVE_PRICE", f"{int(nonpositive)} rows"))

    negative_volume = (numeric["Volume"].dropna() < 0).sum() if "Volume" in numeric else 0
    if negative_volume:
        issues.append(ValidationIssue("NEGATIVE_VOLUME", f"{int(negative_volume)} rows"))

    return issues
