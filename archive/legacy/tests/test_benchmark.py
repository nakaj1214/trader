from __future__ import annotations

import pandas as pd

from src.evaluation.benchmark import (
    add_benchmark_excess_returns,
    benchmark_returns_for_dates,
    summarize_excess_returns,
)


def test_benchmark_returns_and_excess() -> None:
    idx = pd.bdate_range("2026-01-01", periods=8)
    history = pd.DataFrame({"Close": [100, 101, 102, 103, 104, 105, 106, 107]}, index=idx)
    benchmark = benchmark_returns_for_dates(["2026-01-01"], history, horizons=(5,))
    assert round(benchmark["2026-01-01"][5], 6) == 5.0

    rows = [{"date": "2026-01-01", "ticker": "A.T", "h5_return_pct": 10.0}]
    enriched = add_benchmark_excess_returns(rows, benchmark, horizons=(5,))
    assert enriched[0]["h5_excess_return_pct"] == 5.0

    summary = summarize_excess_returns(enriched, horizons=(5,))
    assert summary["h5"]["beat_benchmark_rate_pct"] == 100.0
    assert summary["h5"]["mean_excess_return_pct"] == 5.0
