from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.data.live_quote import TodayQuote
from src.monitoring.position_exit import StaleQuoteError, evaluate_position

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 9, 8, 12, 35, tzinfo=JST)


def _quote(**changes: object) -> TodayQuote:
    quote = TodayQuote(110.0, 115.0, 109.0, 112.0, (NOW - timedelta(minutes=1)).isoformat())
    return replace(quote, **changes)


def _evaluate(quote: TodayQuote, highs: list[float] | None = None):
    index = pd.to_datetime(["2026-09-04", "2026-09-07", "2026-09-08"][: len(highs or [])])
    return evaluate_position(
        100.0,
        "2026-09-01",
        pd.Series(highs or [], index=index, dtype=float),
        pd.Series([105.0, 110.0], index=pd.to_datetime(["2026-09-04", "2026-09-07"])),
        quote,
        10.0,
        NOW,
        "1111.T",
    )


def test_evaluate_position_matches_gap_and_low_touch_ordering() -> None:
    gap = _evaluate(_quote(open=100.0, low_so_far=99.0), [120.0])
    touch = _evaluate(_quote(open=110.0, low_so_far=107.0), [120.0])

    assert gap.exit_reason == "trailing_gap"
    assert touch.exit_reason == "trailing_stop"
    assert gap.stop_price == 108.0


def test_evaluate_position_uses_entry_for_empty_high_water_mark() -> None:
    status = _evaluate(_quote(open=95.0, low_so_far=94.0), [])

    assert status.high_water_mark == 100.0
    assert status.triggered is False
    assert status.unrealized_pct == 12.0


def test_quote_exactly_at_stale_boundary_is_accepted() -> None:
    status = _evaluate(_quote(as_of_at=(NOW - timedelta(minutes=60)).isoformat()), [110.0])

    assert status.triggered is False


@pytest.mark.parametrize(
    "quote,evaluated_at",
    [
        (_quote(as_of_at=(NOW - timedelta(minutes=61)).isoformat()), NOW),
        (_quote(as_of_at=(NOW + timedelta(minutes=1)).isoformat()), NOW),
        (_quote(as_of_at="2026-09-08T12:34:00"), NOW),
    ],
)
def test_evaluate_position_rejects_unusable_quote_time(quote: TodayQuote, evaluated_at: datetime) -> None:
    with pytest.raises(StaleQuoteError):
        evaluate_position(
            100.0,
            "2026-09-01",
            pd.Series(dtype=float),
            pd.Series(dtype=float),
            quote,
            10.0,
            evaluated_at,
            "1111.T",
        )


def test_evaluate_position_requires_aware_evaluation_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        evaluate_position(
            100.0,
            "2026-09-01",
            pd.Series(dtype=float),
            pd.Series(dtype=float),
            _quote(),
            10.0,
            NOW.replace(tzinfo=None),
            "1111.T",
        )


@pytest.mark.parametrize("entry_price", [0.0, float("nan"), float("inf")])
def test_evaluate_position_rejects_invalid_entry_price(entry_price: float) -> None:
    with pytest.raises(ValueError, match="entry_price"):
        evaluate_position(
            entry_price,
            "2026-09-01",
            pd.Series(dtype=float),
            pd.Series(dtype=float),
            _quote(),
            10.0,
            NOW,
            "1111.T",
        )


def test_evaluate_position_rejects_current_day_in_prior_history() -> None:
    with pytest.raises(ValueError, match="current quote date"):
        evaluate_position(
            100.0,
            "2026-09-01",
            pd.Series([120.0], index=pd.to_datetime(["2026-09-08"])),
            pd.Series(dtype=float),
            _quote(),
            10.0,
            NOW,
            "1111.T",
        )
