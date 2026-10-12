from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from scripts.rebuild_inflection_forward_validation import _changed_price_rows, _history_row_hashes
from src.data.forward_prices import (
    PRIOR_HISTORY_DAYS,
    PriceHistories,
    fetch_price_histories,
    legacy_hash_window,
    shared_price_window,
    snapshot_dates,
)
from src.data.jquants_history import tse_sessions


def test_foreign_provider_logger_is_also_private(capsys, caplog) -> None:
    def fail(*args, **kwargs):
        logging.getLogger("fake.credentials").error("9999.T purchase=2026-08-04 private-token")
        raise RuntimeError("9999.T private-token")
    with patch("src.data.forward_prices.yf.download", side_effect=fail), pytest.raises(RuntimeError):
        fetch_price_histories(["9999.T"], START, END, max_retries=0, sleep=lambda _: None)
    public = capsys.readouterr().out + caplog.text
    assert "9999.T" not in public and "2026-08-04" not in public and "private-token" not in public

START, END = date(2026, 1, 1), date(2026, 2, 1)
# The success fixture covers the requested window, excluding weekends and Japanese holidays.
INDEX = pd.DatetimeIndex(tse_sessions(START, END - timedelta(days=1)))


def _raw(base: float = 100.0, adj: float = 0.9) -> pd.DataFrame:
    close = pd.Series([base + i for i in range(len(INDEX))], index=INDEX, dtype=float)
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Adj Close": close * adj,
            "Volume": 1000.0,
            "Dividends": 0.0,
            "Stock Splits": 0.0,
        }
    )


class FakeDownload:
    def __init__(self, frames: dict[str, pd.DataFrame], missing: set[str] | None = None) -> None:
        self.frames = frames
        self.missing = missing or set()
        self.calls: list[list[str]] = []
        self.kwargs: list[dict[str, Any]] = []

    def __call__(self, tickers: str, **kwargs: Any) -> pd.DataFrame:
        names = tickers.split()
        self.calls.append(names)
        self.kwargs.append(kwargs)
        present = [name for name in names if name in self.frames and name not in self.missing]
        if not present:
            return pd.DataFrame()
        parts = {(name, column): self.frames[name][column] for name in present for column in self.frames[name].columns}
        result = pd.DataFrame(parts)
        result.columns = pd.MultiIndex.from_tuples(result.columns)
        return result


def _fetch(frames: dict[str, pd.DataFrame], tickers: list[str] | None = None, **kwargs: Any) -> tuple[PriceHistories, FakeDownload]:
    fake = FakeDownload(frames, kwargs.pop("missing", None))
    defaults: dict[str, Any] = {"batch_interval_seconds": 0.0, "retry_backoff_seconds": 0.0, "sleep": lambda _: None}
    with patch("yfinance.download", fake):
        result = fetch_price_histories(tickers or sorted(frames), START, END, **(defaults | kwargs))
    return result, fake


def test_hundred_tickers_take_two_batches_and_never_one_request_per_ticker() -> None:
    frames = {f"{n:04d}.T": _raw(100.0 + n) for n in range(100)}

    with patch("yfinance.Ticker", side_effect=AssertionError("per-ticker history() must not be used")):
        result, fake = _fetch(frames)

    assert [len(batch) for batch in fake.calls] == [50, 50]
    assert len(result.raw) == 100 and result.unavailable == 0
    assert fake.kwargs[0]["auto_adjust"] is False and fake.kwargs[0]["actions"] is True


def test_both_bases_derive_from_one_raw_download() -> None:
    raw = _raw(adj=0.5)
    result, _ = _fetch({"1111.T": raw})

    split_only = result.split_only()["1111.T"]
    total_return = result.total_return()["1111.T"]

    assert split_only["Close"].tolist() == raw["Close"].tolist()  # split-only: Yahoo's OHLC as returned
    assert total_return["Close"].tolist() == pytest.approx((raw["Close"] * 0.5).tolist())
    assert total_return["Open"].tolist() == pytest.approx((raw["Open"] * 0.5).tolist())  # ratio Adj/Close on every column
    assert total_return["High"].tolist() == pytest.approx((raw["High"] * 0.5).tolist())
    assert "Adj Close" not in total_return.columns


def test_derived_total_return_hashes_match_the_old_history_path() -> None:
    """The old path returned tz-aware, auto-adjusted OHLC from Ticker.history; hashes are keyed by date."""
    raw = _raw(adj=0.93)
    result, _ = _fetch({"1111.T": raw})
    old_style = pd.DataFrame(
        {
            column: raw[column] * (raw["Adj Close"] / raw["Close"])
            for column in ("Open", "High", "Low", "Close")
        }
    )
    old_style.index = old_style.index.tz_localize("Asia/Tokyo")

    assert _history_row_hashes(result.total_return()["1111.T"]) == _history_row_hashes(old_style)
    assert _history_row_hashes(result.split_only()["1111.T"]) == _history_row_hashes(raw)


def test_a_wider_fetch_window_does_not_look_like_a_price_revision() -> None:
    full = _raw()
    old_fetch = full.iloc[6:]  # the old per-ticker window started later
    saved = {"hashes": {"1111.T": {"total_return_adjusted": _history_row_hashes(old_fetch)}}}
    start_of_old_window = date.fromisoformat(str(old_fetch.index[0].date()))

    sliced = {"1111.T": {"total_return_adjusted": _history_row_hashes(legacy_hash_window(full, start_of_old_window))}}
    unsliced = {"1111.T": {"total_return_adjusted": _history_row_hashes(full)}}

    assert _changed_price_rows(saved, sliced) == []
    # Without slicing, the old first day is now normalised by the previous close: a false revision.
    assert [row["date"] for row in _changed_price_rows(saved, unsliced)] == [str(old_fetch.index[0].date())]


def test_cache_lets_the_second_consumer_skip_fetched_tickers(tmp_path: Path) -> None:
    cache = tmp_path / "price_cache.pkl"
    frames = {f"{n:04d}.T": _raw(100.0 + n) for n in range(4)}
    _, first = _fetch(frames, cache_path=cache)
    assert sum(len(batch) for batch in first.calls) == 4

    again, second = _fetch(frames, cache_path=cache)
    assert second.calls == [] and set(again.raw) == set(frames)

    wider, third = _fetch({**frames, "9999.T": _raw(200.0)}, cache_path=cache)
    assert third.calls == [["9999.T"]] and set(wider.raw) == {*frames, "9999.T"}


@pytest.mark.parametrize("gap", ["prefix", "tail", "interior"])
def test_partial_history_cache_is_refetched_for_actual_missing_sessions(tmp_path: Path, gap: str) -> None:
    complete = _raw()
    partial = {"prefix": complete.iloc[5:], "tail": complete.iloc[:-2],
               "interior": complete.drop(INDEX[8])}[gap]
    cache = tmp_path / "cache.pkl"
    first, _ = _fetch({"1111.T": partial}, cache_path=cache)
    assert first.unavailable == 0  # Short/gapped ordinary histories are usable, not a retrieval failure.

    second, download = _fetch({"1111.T": complete}, cache_path=cache)
    assert download.calls == [["1111.T"]]
    pd.testing.assert_frame_equal(second.raw["1111.T"], complete)
    _, reused = _fetch({"1111.T": complete}, cache_path=cache)
    assert reused.calls == []


@pytest.mark.parametrize("reason", ["new_listing", "suspension"])
def test_legitimate_short_history_remains_available_without_claiming_full_cache(tmp_path: Path, reason: str) -> None:
    frame = _raw().iloc[8:] if reason == "new_listing" else _raw().drop(INDEX[8:11])
    cache = tmp_path / "cache.pkl"
    for _ in range(2):
        result, download = _fetch({"1111.T": frame}, cache_path=cache)
        assert download.calls == [["1111.T"]]
        assert result.unavailable == 0
        pd.testing.assert_frame_equal(result.raw["1111.T"], frame)
    if reason == "new_listing":
        # No rows are required before listing when the requested window starts on its first bar.
        fake = FakeDownload({})
        with patch("yfinance.download", fake):
            narrower = fetch_price_histories(["1111.T"], frame.index[0].date(), END, cache_path=cache,
                                            max_retries=0, sleep=lambda _: None)
        assert fake.calls == [] and narrower.unavailable == 0


@pytest.mark.parametrize("gap", ["prefix", "tail", "interior"])
def test_incomplete_required_benchmark_retries_and_is_never_saved_as_complete(tmp_path: Path, gap: str) -> None:
    complete = _raw()
    partial = {"prefix": complete.iloc[1:], "tail": complete.iloc[:-1],
               "interior": complete.drop(INDEX[8])}[gap]
    fake = FakeDownload({"1306.T": partial})
    cache = tmp_path / "cache.pkl"
    with patch("yfinance.download", fake), pytest.raises(RuntimeError, match="Required price history"):
        fetch_price_histories(["1306.T"], START, END, required={"1306.T"}, cache_path=cache,
                              max_retries=1, sleep=lambda _: None)
    assert fake.calls == [["1306.T"], ["1306.T"]]
    assert not cache.exists()


def test_partial_required_benchmark_recovers_during_retry() -> None:
    complete = _raw()
    with patch("yfinance.download", side_effect=[complete.drop(INDEX[8]), complete]) as download:
        result = fetch_price_histories(["1306.T"], START, END, required={"1306.T"},
                                      max_retries=1, sleep=lambda _: None)
    assert download.call_count == 2 and result.unavailable == 0
    pd.testing.assert_frame_equal(result.raw["1306.T"], complete)


def test_partial_legacy_cache_cannot_satisfy_required_benchmark(tmp_path: Path) -> None:
    cache = tmp_path / "cache.pkl"
    _fetch({"1306.T": _raw().iloc[:1]}, cache_path=cache)
    result, fake = _fetch({"1306.T": _raw()}, cache_path=cache, required={"1306.T"})
    assert fake.calls == [["1306.T"]]
    assert len(result.raw["1306.T"]) == len(INDEX)


def test_required_benchmark_needs_only_sessions_before_exclusive_end() -> None:
    # 01/01, 01/02 and 01/12 are holidays; 01/13 is the exclusive end, not a missing bar.
    end = date(2026, 1, 13)
    frame = _raw().loc[_raw().index < pd.Timestamp(end)]
    with patch("yfinance.download", return_value=frame):
        result = fetch_price_histories(["1306.T"], START, end, required={"1306.T"}, max_retries=0)
    assert len(result.raw["1306.T"]) == 5


def test_wider_cache_returns_only_the_requested_price_window(tmp_path: Path) -> None:
    cache = tmp_path / "cache.pkl"
    _fetch({"1111.T": _raw()}, cache_path=cache)
    fake = FakeDownload({})
    with patch("yfinance.download", fake):
        result = fetch_price_histories(["1111.T"], INDEX[5].date(), INDEX[9].date(), cache_path=cache,
                                      max_retries=0, sleep=lambda _: None)
    assert fake.calls == []
    pd.testing.assert_frame_equal(result.raw["1111.T"], _raw().iloc[5:9])


def test_no_quote_suspension_row_is_a_gap_not_an_invalid_quoted_price(tmp_path: Path) -> None:
    frame = _raw()
    frame.loc[INDEX[8], ["Open", "High", "Low", "Close", "Adj Close"]] = float("nan")
    frame.loc[INDEX[8], "Volume"] = 0.0
    for _ in range(2):
        result, fake = _fetch({"1111.T": frame}, cache_path=tmp_path / "cache.pkl", max_retries=0)
        assert fake.calls == [["1111.T"]] and result.unavailable == 0
        pd.testing.assert_frame_equal(result.raw["1111.T"], _raw().drop(INDEX[8]))


def test_cache_is_not_reused_when_it_covers_a_shorter_window(tmp_path: Path) -> None:
    cache = tmp_path / "price_cache.pkl"
    frames = {"1111.T": _raw()}
    with patch("yfinance.download", FakeDownload(frames)):
        fetch_price_histories(["1111.T"], date(2026, 1, 20), END, cache_path=cache, sleep=lambda _: None)

    _, refetch = _fetch(frames, cache_path=cache)  # needs data from 2026-01-01

    assert refetch.calls == [["1111.T"]]


def test_an_unreadable_cache_is_ignored(tmp_path: Path) -> None:
    cache = tmp_path / "price_cache.pkl"
    cache.write_bytes(b"not a pickle")

    result, fake = _fetch({"1111.T": _raw()}, cache_path=cache)

    assert fake.calls == [["1111.T"]] and "1111.T" in result.raw


def test_a_few_missing_tickers_are_tolerated_and_counted() -> None:
    frames = {f"{n:04d}.T": _raw() for n in range(20)}

    result, _ = _fetch(frames, missing={"0000.T"}, max_retries=0)

    assert result.unavailable == 1 and len(result.raw) == 19


def test_many_missing_tickers_fail_closed_without_naming_them() -> None:
    frames = {f"{n:04d}.T": _raw() for n in range(20)}

    with pytest.raises(RuntimeError, match=r"failed for 2 ticker\(s\)") as caught:
        _fetch(frames, missing={"0000.T", "0001.T"}, max_retries=0)

    assert "0000.T" not in str(caught.value)


def test_a_missing_required_ticker_fails_even_within_the_tolerance() -> None:
    frames = {f"{n:04d}.T": _raw() for n in range(20)} | {"1306.T": _raw()}

    with pytest.raises(RuntimeError, match="Required price history") as caught:
        _fetch(frames, missing={"1306.T"}, required={"1306.T"}, max_retries=0)

    assert "1306.T" not in str(caught.value)


def test_transient_failures_are_retried_with_backoff() -> None:
    fake = FakeDownload({"1111.T": _raw()})
    sleeps: list[float] = []
    real_call = fake.__call__
    attempts = {"count": 0}

    def flaky(tickers: str, **kwargs: Any) -> pd.DataFrame:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary")
        return real_call(tickers, **kwargs)

    with patch("yfinance.download", flaky):
        result = fetch_price_histories(
            ["1111.T"], START, END, max_retries=2, retry_backoff_seconds=2.0, batch_interval_seconds=0.0,
            sleep=sleeps.append,
        )

    assert "1111.T" in result.raw and sleeps == [2.0]


def test_programmer_errors_are_not_converted_to_missing_prices() -> None:
    with patch("yfinance.download", side_effect=TypeError("bug")), pytest.raises(TypeError):
        fetch_price_histories(["1111.T"], START, END, max_retries=0, batch_interval_seconds=0.0)


def test_provider_output_and_logs_never_reach_the_console(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    secret = "SECRET.T provider detail"

    def noisy(*args: object, **kwargs: object) -> pd.DataFrame:
        del args, kwargs
        print(secret)
        print(secret, file=sys.stderr)
        logging.getLogger("yfinance").error(secret)
        raise RuntimeError(secret)

    with patch("yfinance.download", noisy), pytest.raises(RuntimeError, match=r"failed for 1 ticker\(s\)") as caught:
        fetch_price_histories(
            ["SECRET.T"], START, END, max_retries=0, batch_interval_seconds=0.0, sleep=lambda _: None
        )

    captured = capsys.readouterr()
    for hidden in ("SECRET.T", "provider detail"):
        assert hidden not in str(caught.value) and hidden not in captured.out
        assert hidden not in captured.err and hidden not in caplog.text
    assert logging.getLogger("yfinance").disabled is False  # the logger is restored


def test_frames_without_adj_close_count_as_missing() -> None:
    frames = {f"{n:04d}.T": _raw() for n in range(20)}
    frames["0003.T"] = frames["0003.T"].drop(columns=["Adj Close"])

    result, _ = _fetch(frames, max_retries=0)

    assert "0003.T" not in result.raw and result.unavailable == 1


@pytest.mark.parametrize(("column", "value"), [
    ("Adj Close", float("nan")), ("Adj Close", float("inf")), ("Adj Close", float("-inf")),
    ("Adj Close", 0.0), ("Adj Close", -1.0), ("High", float("inf")), ("High", 1.0),
    ("Volume", float("nan")), ("Volume", float("inf")), ("Volume", -1.0), ("Close", 0.0),
])
def test_invalid_forward_prices_are_not_returned_or_cached(tmp_path: Path, column: str, value: float) -> None:
    frame = _raw()
    frame.loc[frame.index[0], column] = value
    cache = tmp_path / "cache.pkl"
    with pytest.raises(RuntimeError, match="Price retrieval failed"):
        _fetch({"1111.T": frame}, max_retries=0, cache_path=cache)
    assert not cache.exists()


def test_duplicate_forward_dates_are_rejected() -> None:
    frame = pd.concat([_raw().iloc[:1], _raw()])
    with pytest.raises(RuntimeError, match="Price retrieval failed"):
        _fetch({"1111.T": frame}, max_retries=0)


def test_total_return_revalidates_the_values_used_after_adjustment() -> None:
    frame = _raw()
    frame["Close"] = frame["Low"] = 1e-300
    frame["Adj Close"] = 1e300
    with pytest.raises(ValueError, match="Invalid adjusted price history"):
        PriceHistories({"1111.T": frame}, START, END).total_return()


@pytest.mark.parametrize("kwargs", [{"batch_size": 0}, {"max_retries": -1}, {"retry_backoff_seconds": -1.0}])
def test_invalid_timing_parameters_are_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="invalid"):
        fetch_price_histories(["1111.T"], START, END, **kwargs)


# --- shared window ------------------------------------------------------------------------------


def _touch(directory: Path, *names: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text("x", encoding="utf-8")
    return directory


def test_window_starts_460_days_before_the_earliest_snapshot_of_any_given_directory(tmp_path: Path) -> None:
    v3 = _touch(tmp_path / "v3", "2026-09-14.enc", "2026-09-15.enc")
    legacy = _touch(tmp_path / "legacy", "2026-09-09.enc", "notes.txt", "2026-09-10.json", "2026-13-45.enc")

    assert PRIOR_HISTORY_DAYS == 460  # 273 prior benchmark closes for the regime, with slack (see forward_prices)
    assert shared_price_window([v3, legacy], date(2026, 10, 1)) == (date(2025, 6, 6), date(2026, 10, 2))
    assert shared_price_window([v3], date(2026, 10, 1)) == (date(2025, 6, 11), date(2026, 10, 2))
    assert snapshot_dates([legacy]) == [date(2026, 9, 9)]


def test_window_follows_cli_given_directories_even_when_the_defaults_are_empty(tmp_path: Path) -> None:
    default_v3 = tmp_path / "dashboard" / "data" / "inflection" / "v3"
    default_v3.mkdir(parents=True)  # exists but is empty, as in a fixture run
    custom_legacy = _touch(tmp_path / "fixtures" / "legacy", "2025-01-06.enc")
    custom_v3 = _touch(tmp_path / "fixtures" / "v3", "2025-03-03.enc")

    window = shared_price_window([custom_v3, custom_legacy], date(2026, 10, 1))

    assert window is not None and window[0] == date(2025, 1, 6) - timedelta(days=PRIOR_HISTORY_DAYS)


def test_window_is_none_without_snapshots_and_ignores_missing_directories(tmp_path: Path) -> None:
    assert shared_price_window([tmp_path / "missing", _touch(tmp_path / "empty")], date(2026, 10, 1)) is None


def test_legacy_hash_window_handles_tz_aware_and_naive_indexes() -> None:
    frame = _raw()
    aware = frame.copy()
    aware.index = aware.index.tz_localize("Asia/Tokyo")

    assert len(legacy_hash_window(frame, date(2026, 1, 12))) == len(INDEX[INDEX >= pd.Timestamp("2026-01-12")])
    assert len(legacy_hash_window(aware, date(2026, 1, 12))) == len(legacy_hash_window(frame, date(2026, 1, 12)))


def test_a_ticker_list_with_duplicates_is_fetched_once() -> None:
    fake = FakeDownload({"1111.T": _raw()})
    pick: Callable[..., Any] = fake
    with patch("yfinance.download", pick):
        fetch_price_histories(["1111.T", "1111.T"], START, END, batch_interval_seconds=0.0, sleep=lambda _: None)

    assert fake.calls == [["1111.T"]]


def _raw_between(start: date, end: date, base: float = 100.0) -> pd.DataFrame:
    index = pd.bdate_range(start, end)
    close = pd.Series([base + i * 0.1 for i in range(len(index))], index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Adj Close": close,
            "Volume": 1000.0, "Dividends": 0.0, "Stock Splits": 0.0,
        }
    )


def test_learning_reuses_forwards_cache_and_both_have_prior_history_for_legacy_snapshots(tmp_path: Path) -> None:
    """Forward (v3 only) runs first; learning (legacy + v3) must fetch only what forward did not."""
    v3 = _touch(tmp_path / "v3", "2026-09-14.enc")
    legacy = _touch(tmp_path / "legacy", "2026-09-09.enc")
    today = date(2026, 10, 1)
    window = shared_price_window([v3, legacy], today)
    assert window is not None and window[0] == date(2026, 9, 9) - timedelta(days=PRIOR_HISTORY_DAYS)
    frames = {name: _raw_between(window[0], window[1], 100.0 + n) for n, name in enumerate(("1111.T", "2222.T", "1306.T", "3333.T"))}
    cache = tmp_path / "artifacts" / "price_cache.pkl"

    with patch("yfinance.download", FakeDownload(frames)):
        fetch_price_histories(["1111.T", "2222.T", "1306.T"], *window, cache_path=cache, required={"1306.T"},
                              batch_interval_seconds=0.0, sleep=lambda _: None)
    learning_fake = FakeDownload(frames)
    with patch("yfinance.download", learning_fake):
        learned = fetch_price_histories(["1111.T", "2222.T", "3333.T", "1306.T"], *window, cache_path=cache,
                                        required={"1306.T"}, batch_interval_seconds=0.0, sleep=lambda _: None)

    assert learning_fake.calls == [["3333.T"]]  # only the legacy-only ticker is fetched
    earliest_observation = pd.Timestamp("2026-09-09")
    for ticker, frame in learned.total_return().items():
        # enough prior closes for the 273-close regime reading as well as the 61-close volatility
        assert (frame.index < earliest_observation).sum() >= 273, ticker
