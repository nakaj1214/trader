"""Deterministic market-data validation helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    detail: str


def validate_ohlcv(df: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if df.empty:
        return [ValidationIssue("EMPTY", "No rows")]

    if not df.index.is_monotonic_increasing:
        issues.append(ValidationIssue("UNSORTED_INDEX", "Index is not sorted ascending"))
    if df.index.has_duplicates:
        issues.append(ValidationIssue("DUPLICATE_INDEX", "Duplicate trading dates detected"))

    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        issues.append(ValidationIssue("MISSING_COLUMNS", ",".join(missing)))
        return issues

    numeric = df[required].apply(pd.to_numeric, errors="coerce")
    if numeric[["Open", "High", "Low", "Close"]].isna().any().any():
        issues.append(ValidationIssue("PRICE_NAN", "OHLC contains non-numeric or missing values"))
    if numeric["Volume"].isna().any():
        issues.append(ValidationIssue("VOLUME_NAN", "Volume contains non-numeric or missing values"))

    valid = numeric.dropna(subset=["Open", "High", "Low", "Close"])
    if not valid.empty:
        bad_high = (valid["High"] < valid[["Open", "Close", "Low"]].max(axis=1)).sum()
        bad_low = (valid["Low"] > valid[["Open", "Close", "High"]].min(axis=1)).sum()
        nonpositive = (valid[["Open", "High", "Low", "Close"]] <= 0).any(axis=1).sum()
        if bad_high:
            issues.append(ValidationIssue("HIGH_INCONSISTENT", f"{int(bad_high)} rows"))
        if bad_low:
            issues.append(ValidationIssue("LOW_INCONSISTENT", f"{int(bad_low)} rows"))
        if nonpositive:
            issues.append(ValidationIssue("NONPOSITIVE_PRICE", f"{int(nonpositive)} rows"))

    negative_volume = (numeric["Volume"].dropna() < 0).sum()
    if negative_volume:
        issues.append(ValidationIssue("NEGATIVE_VOLUME", f"{int(negative_volume)} rows"))

    return issues


def compare_close_series(
    primary: pd.DataFrame,
    reference: pd.DataFrame,
    tolerance_pct: float = 0.5,
) -> dict[str, float | int | None]:
    """Compare overlapping close prices from two providers."""
    if "Close" not in primary.columns or "Close" not in reference.columns:
        return {"overlap": 0, "match_rate_pct": None, "median_abs_diff_pct": None, "max_abs_diff_pct": None}

    a = pd.to_numeric(primary["Close"], errors="coerce")
    b = pd.to_numeric(reference["Close"], errors="coerce")
    a.index = pd.to_datetime(a.index).tz_localize(None)
    b.index = pd.to_datetime(b.index).tz_localize(None)
    joined = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
    joined = joined[(joined["a"] > 0) & (joined["b"] > 0)]
    if joined.empty:
        return {"overlap": 0, "match_rate_pct": None, "median_abs_diff_pct": None, "max_abs_diff_pct": None}

    diff = ((joined["a"] / joined["b"]) - 1.0).abs() * 100.0
    return {
        "overlap": int(len(diff)),
        "match_rate_pct": round(float((diff <= tolerance_pct).mean() * 100.0), 3),
        "median_abs_diff_pct": round(float(diff.median()), 6),
        "max_abs_diff_pct": round(float(diff.max()), 6),
    }
