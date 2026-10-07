from __future__ import annotations

import copy
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.evaluation.inflection_historical import (
    BarPanel,
    FinancialsStore,
    HistoricalData,
    MasterHistory,
    reconstruct_scan,
)
from src.screening.inflection_live import scan_japan_inflection

DATES = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2025-01-06", periods=300)]
FUTURE = [d.strftime("%Y-%m-%d") for d in pd.bdate_range(pd.Timestamp(DATES[-1]) + pd.offsets.BDay(1), periods=20)]
AS_OF = DATES[-1]
CODES = [f"{n}{n}{n}{n}0" for n in range(1, 7)]


def _bar(code: str, close: float, volume: float, adj: float = 1.0, **extra: Any) -> dict[str, Any]:
    return {
        "Code": code, "O": close, "H": close * 1.01, "L": close * 0.99, "C": close,
        "Vo": volume, "Va": close * volume, "AdjFactor": adj, **extra,
    }


def _series(n: int, i: int, length: int = len(DATES)) -> tuple[float, float]:
    close = 100.0 + i * 0.2 * n
    volume = 1_000_000.0 if i < length - 20 else 1_000_000.0 * (1 + 0.3 * n)
    return close, volume


def _bars() -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for i, day in enumerate(DATES):
        day_rows = [_bar(code, *_series(n, i)) for n, code in enumerate(CODES, start=1)]
        day_rows.append(_bar("13060", 2000.0, 5_000_000.0))  # ETF: ordinary code, not in master
        day_rows.append(_bar("25935", 50.0, 1_000.0))  # preferred share: never mapped to NNNN.T
        rows[day] = day_rows
    return rows


def _master(extra: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = [
        {"Code": code, "CoName": f"Co {code}", "Mkt": "0111", "MktNm": "Prime", "S33": "3650", "S33Nm": "電気機器"}
        for code in CODES
    ]
    return rows + (extra or [])


def _fin(code: str, disc_date: str, per: str, fy_end: str, sales: str, op: str, fop: str, **extra: Any) -> dict[str, Any]:
    return {
        "Code": code, "DiscDate": disc_date, "DiscTime": "15:00", "DiscNo": "1", "DocType": "EarnForecast",
        "CurPerType": per, "CurFYEn": fy_end, "Sales": sales, "OP": op, "FOP": fop, "CFO": "5", **extra,
    }


def _fins() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code in CODES:
        rows += [
            _fin(code, "2025-02-01", "Q3", "2025-03-31", "100", "10", "20"),
            _fin(code, "2026-02-01", "Q3", "2026-03-31", "140", "25", "25"),
            _fin(code, "2026-02-10", "Q3", "2026-03-31", "", "", "30", DocType="EarnForecastRevision", DiscNo="2"),
        ]
    return rows


def _data(
    bars: dict[str, list[dict[str, Any]]] | None = None,
    masters: dict[str, list[dict[str, Any]]] | None = None,
    fins: list[dict[str, Any]] | None = None,
) -> HistoricalData:
    return HistoricalData(
        BarPanel.from_rows(bars if bars is not None else _bars()),
        MasterHistory(masters if masters is not None else {DATES[0]: _master()}),
        FinancialsStore(fins if fins is not None else _fins()),
    )


def _strip(report: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(report)
    for key in ("candidates", "control_sample"):
        for row in result[key]:
            row.pop("limitations", None)
    return result


# --- REQ-040 acceptance 1: identical to the live scan --------------------------------------


class LiveFake:
    def is_available(self) -> bool:
        return True

    def listed_issues(self) -> list[dict[str, Any]]:
        return _master()

    def financial_summary(self, code: str) -> list[dict[str, Any]]:
        return [row for row in _fins() if row["Code"] == code]


def test_reconstruct_scan_matches_the_live_scan_for_the_same_inputs() -> None:
    live_prices = {}
    for n, code in enumerate(CODES, start=1):
        closes, volumes = zip(*(_series(n, i) for i in range(len(DATES))), strict=True)
        live_prices[f"{code[:4]}.T"] = pd.DataFrame(
            {
                "Close": closes[-252:],
                "Volume": volumes[-252:],
                "Turnover": [c * v for c, v in zip(closes[-252:], volumes[-252:], strict=True)],
            },
            index=pd.DatetimeIndex(DATES[-252:]),
        )
    with (
        patch("src.screening.inflection_live.fetch_price_data", return_value=live_prices),
        patch("src.screening.inflection_live.expected_tse_session_date", return_value=AS_OF),
    ):
        live = scan_japan_inflection(client=LiveFake(), deep_candidates=2, min_turnover_jpy=0, control_sample_size=3)  # type: ignore[arg-type]

    rebuilt = reconstruct_scan(AS_OF, _data(), lag="disclosure", deep_candidates=2, min_turnover_jpy=0, control_sample_size=3)

    assert len(rebuilt["candidates"]) == 2 and len(rebuilt["control_sample"]) == 3
    for key in ("candidates", "control_sample"):
        assert _strip(rebuilt)[key] == _strip(live)[key]
    assert rebuilt["control_sample_seed"] == live["control_sample_seed"]
    assert rebuilt["liquid_candidate_count"] == live["liquid_candidate_count"]
    assert rebuilt["classification_counts"] == live["classification_counts"]


# --- REQ-040 acceptance 2: no look-ahead ----------------------------------------------------


def test_adding_future_data_does_not_change_the_reconstruction() -> None:
    baseline = reconstruct_scan(AS_OF, _data(), lag="disclosure", deep_candidates=3, min_turnover_jpy=0)

    bars = _bars()
    for i, day in enumerate(FUTURE):
        # 1-for-2 split on the first future day for the first ticker, plus ordinary later bars
        split = i == 0
        rows = [_bar(code, 300.0, 3_000_000.0) for code in CODES[1:]]
        rows.append(_bar(CODES[0], 150.0, 3_000_000.0, adj=0.5 if split else 1.0))
        bars[day] = rows
    masters = {
        DATES[0]: _master(),
        FUTURE[2]: [{**row, "Mkt": "0105"} for row in _master()]
        + [{"Code": "77770", "CoName": "New", "Mkt": "0111", "MktNm": "Prime"}],
    }
    fins = _fins() + [_fin(code, FUTURE[1], "FY", "2026-03-31", "9999", "9999", "9999") for code in CODES]

    changed = reconstruct_scan(AS_OF, _data(bars, masters, fins), lag="disclosure", deep_candidates=3, min_turnover_jpy=0)

    assert changed == baseline  # includes current_price, so later splits cannot rescale the past


def test_free_plan_lag_excludes_disclosures_younger_than_84_days() -> None:
    store = FinancialsStore(
        [
            _fin("11110", "2026-01-05", "Q3", "2026-03-31", "1", "1", "1"),  # +84d == 2026-03-30
            _fin("11110", "2026-01-06", "Q3", "2026-03-31", "2", "2", "2"),  # +84d == 2026-03-31
        ]
    )
    as_of = "2026-03-30"

    assert len(store.view(as_of, "disclosure").financial_summary("11110")) == 2
    free = store.view(as_of, "free_12w").financial_summary("11110")
    assert [row["DiscDate"] for row in free] == ["2026-01-05"]


@pytest.mark.parametrize(
    ("disc_time", "included"),
    [("15:00", True), ("16:40", True), ("16:41", False), ("17:00", False), ("", False), ("not-a-time", False)],
)
def test_disclosure_lag_respects_the_scan_time_of_the_same_day(disc_time: str, included: bool) -> None:
    store = FinancialsStore([_fin("11110", "2026-02-02", "Q3", "2026-03-31", "1", "1", "1", DiscTime=disc_time)])

    rows = store.view("2026-02-02", "disclosure").financial_summary("11110")

    assert bool(rows) is included
    assert store.view("2026-02-03", "disclosure").financial_summary("11110")  # next day always sees it


def test_unparseable_disclosure_dates_are_skipped_and_counted() -> None:
    store = FinancialsStore([_fin("11110", "bad", "Q3", "2026-03-31", "1", "1", "1")])
    assert store.skipped_rows == 1


def test_invalid_lag_is_rejected() -> None:
    with pytest.raises(ValueError, match="lag"):
        FinancialsStore([]).view("2026-02-02", "weekly")


# --- universe: delisting, mid-month listing, attributes ------------------------------------


def test_a_delisted_ticker_is_in_the_universe_only_while_it_trades() -> None:
    bars = _bars()
    last_trading = DATES[200]
    for day in DATES[201:]:
        bars[day] = [row for row in bars[day] if row["Code"] != CODES[0]]
    data = _data(bars)

    before = reconstruct_scan(DATES[150], data, lag="disclosure", min_turnover_jpy=0)
    after = reconstruct_scan(DATES[250], data, lag="disclosure", min_turnover_jpy=0)

    assert before["price_data_count"] == len(CODES) and after["price_data_count"] == len(CODES) - 1
    assert last_trading < DATES[250]


def test_a_mid_month_listing_is_never_picked_up_from_a_later_master() -> None:
    new_code = "88880"
    bars = _bars()
    for i in (150, 151):  # trades on two days before the master that lists it
        bars[DATES[i]].append(_bar(new_code, 100.0, 2_000_000.0))
    masters = {DATES[0]: _master(), DATES[151]: _master([{"Code": new_code, "Mkt": "0113", "MktNm": "Growth"}])}
    data = _data(bars, masters)

    early = reconstruct_scan(DATES[150], data, lag="disclosure", min_turnover_jpy=0)
    listed = reconstruct_scan(DATES[151], data, lag="disclosure", min_turnover_jpy=0)

    assert early["price_data_count"] == len(CODES)  # traded, but its master is still in the future
    assert listed["price_data_count"] == len(CODES) + 1
    assert listed["master_date"] == DATES[151] and early["master_date"] == DATES[0]


def test_etfs_and_non_ordinary_codes_are_not_scanned() -> None:
    data = _data()
    assert "1306.T" in data.panel.tickers()  # kept for the benchmark
    assert "2593.T" not in data.panel.tickers()  # preferred share
    report = reconstruct_scan(AS_OF, data, lag="disclosure", min_turnover_jpy=0, control_sample_size=0)
    assert report["universe_count"] == len(CODES)


def test_reconstruction_needs_a_master_on_or_before_the_day() -> None:
    with pytest.raises(ValueError, match="no master"):
        reconstruct_scan(DATES[0], _data(masters={DATES[5]: _master()}), lag="disclosure")


def test_negative_control_sample_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="control_sample_size"):
        reconstruct_scan(AS_OF, _data(), lag="disclosure", control_sample_size=-1)


# --- price adjustment -------------------------------------------------------------------


def _split_panel() -> BarPanel:
    closes = [200.0, 200.0, 100.0, 100.0, 100.0]
    factors = [1.0, 1.0, 0.5, 1.0, 1.0]  # 1-for-2 split with ex-date on day index 2
    days = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    return BarPanel.from_rows({day: [_bar("11110", c, 1000.0, f)] for day, c, f in zip(days, closes, factors, strict=True)})


def test_evaluation_prices_are_split_adjusted_on_one_basis() -> None:
    history = _split_panel().evaluation_histories()["1111.T"]
    assert history["Close"].round(6).tolist() == [100.0] * 5
    assert history["Open"].round(6).tolist() == [100.0] * 5


def test_scan_prices_only_use_splits_up_to_the_scan_day() -> None:
    panel = _split_panel()
    before_split = panel.frames_as_of("2026-01-06")["1111.T"]["Close"].round(6).tolist()
    after_split = panel.frames_as_of("2026-01-09")["1111.T"]["Close"].round(6).tolist()

    assert before_split == [200.0, 200.0]  # the later split must not rescale a past scan
    assert after_split == [100.0] * 5


def test_scan_and_evaluation_prices_differ_by_one_constant_per_ticker() -> None:
    panel = _split_panel()
    scan = panel.frames_as_of("2026-01-06")["1111.T"]["Close"].to_numpy()
    evaluation = panel.evaluation_histories()["1111.T"]["Close"].to_numpy()[:2]
    assert np.allclose(scan / evaluation, 2.0)


def test_adjustment_ignores_adjc_taken_on_different_dates() -> None:
    """Files fetched before/after a split disagree on AdjC; our own factors must not care."""
    panel = BarPanel.from_rows(
        {
            "2026-01-05": [_bar("11110", 100.0, 1000.0, 1.0, AdjC=100.0)],  # fetched before the split
            "2026-01-06": [_bar("11110", 50.0, 1000.0, 0.5, AdjC=50.0)],  # fetched after it
        }
    )
    assert panel.evaluation_histories()["1111.T"]["Close"].round(6).tolist() == [50.0, 50.0]


def test_bars_without_a_close_are_dropped_but_their_factor_still_counts() -> None:
    days = ["2026-01-05", "2026-01-06", "2026-01-07"]
    panel = BarPanel.from_rows(
        {
            days[0]: [_bar("11110", 100.0, 1000.0)],
            days[1]: [{"Code": "11110", "O": None, "H": None, "L": None, "C": None, "Vo": 0, "Va": 0, "AdjFactor": 0.5}],
            days[2]: [_bar("11110", 50.0, 1000.0)],
        }
    )
    assert panel.evaluation_histories()["1111.T"]["Close"].round(6).tolist() == [50.0, 50.0]
    assert panel.last_date() == days[2]


# --- kill criterion --------------------------------------------------------------------------


def _pairs(values: list[float | None], per_date: int = 4) -> list[dict[str, Any]]:
    return [
        {"signal_date": f"2026-01-{1 + i // per_date:02d}", "excess_return_pct": value} for i, value in enumerate(values)
    ]


def test_kill_criterion_passes_when_the_ci_lower_bound_is_above_zero() -> None:
    from src.evaluation.inflection_historical import kill_criterion

    result = kill_criterion(_pairs([5.0 + (i % 5) * 0.1 for i in range(120)]), min_independent=100)

    assert result["verdict"] == "pass" and result["reason"] is None
    assert result["ci95"][0] > 0 and result["valid_pairs"] == 120 and result["signal_date_clusters"] == 30


def test_kill_criterion_fails_when_the_ci_straddles_zero() -> None:
    from src.evaluation.inflection_historical import kill_criterion

    result = kill_criterion(_pairs([(-1) ** i * 10.0 for i in range(120)]), min_independent=100)

    assert result["verdict"] == "fail"
    assert result["ci95"][0] <= 0 <= result["ci95"][1]


def test_kill_criterion_fails_when_the_whole_ci_is_negative() -> None:
    from src.evaluation.inflection_historical import kill_criterion

    result = kill_criterion(_pairs([-5.0 - (i % 5) * 0.1 for i in range(120)]), min_independent=100)

    assert result["verdict"] == "fail" and result["ci95"][1] < 0


def test_kill_criterion_needs_enough_valid_pairs_not_just_trades() -> None:
    from src.evaluation.inflection_historical import kill_criterion

    short = kill_criterion(_pairs([5.0] * 10), min_independent=100)
    missing_benchmark = kill_criterion(_pairs([None] * 30 + [5.0 + i * 0.01 for i in range(90)]), min_independent=100)

    assert short["verdict"] == "insufficient_sample" and short["reason"] == "below_min_independent"
    assert missing_benchmark["verdict"] == "insufficient_sample"
    assert (missing_benchmark["independent_trades"], missing_benchmark["valid_pairs"]) == (120, 90)


def test_kill_criterion_without_a_computable_ci_is_insufficient_not_fail() -> None:
    from src.evaluation.inflection_historical import kill_criterion

    one_day = [{"signal_date": "2026-01-02", "excess_return_pct": float(i)} for i in range(60)]
    result = kill_criterion(one_day, min_independent=50)

    assert result["verdict"] == "insufficient_sample" and result["reason"] == "ci_unavailable"
    assert result["signal_date_clusters"] == 1 and result["valid_pairs"] == 60 and result["ci95"] is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "3"])
def test_kill_criterion_ignores_non_finite_excess_values(bad: object) -> None:
    from src.evaluation.inflection_historical import kill_criterion

    pairs = _pairs([5.0] * 8)
    pairs[0]["excess_return_pct"] = bad
    assert kill_criterion(pairs, min_independent=1)["valid_pairs"] == 7


# --- lag comparison ---------------------------------------------------------------------------


def test_paired_bootstrap_resamples_dates_jointly_for_both_lags() -> None:
    from src.evaluation.inflection_historical import cluster_paired_bootstrap_diff

    base = {f"d{i}": [float(i * i % 7)] for i in range(12)}
    shifted = {date: [value[0] + 2.0] for date, value in base.items()}

    # Joint resampling keeps each date's two sides together, so a constant gap stays exactly 2.
    assert cluster_paired_bootstrap_diff(shifted, base) == (2.0, 2.0)
    assert cluster_paired_bootstrap_diff(shifted, base) == cluster_paired_bootstrap_diff(shifted, base)


def test_paired_bootstrap_validates_dates_and_needs_two_clusters() -> None:
    from src.evaluation.inflection_historical import cluster_paired_bootstrap_diff

    assert cluster_paired_bootstrap_diff({"d1": [1.0]}, {"d1": [2.0]}) is None
    with pytest.raises(ValueError, match="same non-empty"):
        cluster_paired_bootstrap_diff({"d1": [1.0], "d2": [1.0]}, {"d1": [2.0], "d3": [2.0]})


def test_lag_comparison_uses_common_dates_for_the_difference_and_all_dates_per_lag() -> None:
    from src.evaluation.inflection_historical import lag_comparison

    early = [{"signal_date": f"2026-01-{d:02d}", "excess_return_pct": 3.0} for d in range(1, 11)]
    late = [{"signal_date": f"2026-01-{d:02d}", "excess_return_pct": 1.0} for d in range(3, 13)]

    result = lag_comparison({"disclosure": early, "free_12w": late})

    assert result["lags"]["disclosure"]["valid_pairs"] == 10 and result["lags"]["free_12w"]["valid_pairs"] == 10
    assert result["lags"]["disclosure"]["signal_dates_not_in_both"] == 2
    assert result["difference"]["common_signal_dates"] == 8
    assert result["difference"]["mean_difference_pct"] == 2.0 and result["difference"]["ci95"] == [2.0, 2.0]
    assert "disclosure) - mean(free_12w" in result["difference"]["definition"]


def test_lag_comparison_reports_why_there_is_no_difference() -> None:
    from src.evaluation.inflection_historical import lag_comparison

    one = [{"signal_date": "2026-01-05", "excess_return_pct": 1.0}]
    none_common = lag_comparison({"disclosure": one, "free_12w": [{"signal_date": "2026-01-06", "excess_return_pct": 1.0}]})
    single = lag_comparison({"disclosure": one, "free_12w": one})
    empty_side = lag_comparison({"disclosure": one, "free_12w": [{"signal_date": "2026-01-05", "excess_return_pct": None}]})

    assert none_common["difference"]["reason"] == "no_common_signal_dates"
    assert none_common["difference"]["mean_difference_pct"] is None
    assert single["difference"]["reason"] == "fewer_than_two_common_signal_dates"
    assert single["difference"]["mean_difference_pct"] == 0.0
    assert empty_side["difference"]["reason"] == "no_common_signal_dates"
    assert empty_side["lags"]["free_12w"]["mean_excess_return_pct"] is None


# --- signal window -----------------------------------------------------------------------------


def test_default_signal_start_waits_for_fundamentals_history_of_both_lags() -> None:
    from datetime import date, timedelta

    from src.evaluation.inflection_historical import FINS_WARMUP_DAYS, default_signal_start, signal_days

    assert FINS_WARMUP_DAYS == 494  # 410 + the longest (84-day) lag
    fins = [_fin("11110", "2024-09-01", "Q3", "2024-12-31", "1", "1", "1")]
    data = _data(fins=fins)

    start = default_signal_start(data)

    assert start == max(DATES[251], str(date(2024, 9, 1) + timedelta(days=494)))
    assert start == "2026-01-08"  # the fundamentals warm-up, not the 252-day price history, binds here
    assert signal_days(data)[0] >= "2026-01-08" and signal_days(data, "2026-02-20")[0] == "2026-02-20"


def test_default_signal_start_is_none_without_enough_history() -> None:
    from src.evaluation.inflection_historical import default_signal_start, signal_days

    short = _data(bars={day: rows for day, rows in list(_bars().items())[:100]})
    assert default_signal_start(short) is None and signal_days(short) == []
    assert default_signal_start(_data(fins=[])) is None


# --- adjustment check -------------------------------------------------------------------------


def test_adjustment_check_accepts_a_constant_ratio_and_rejects_a_drifting_one() -> None:
    from src.evaluation.inflection_historical import check_adjustment

    index = pd.DatetimeIndex(["2026-01-05", "2026-01-06", "2026-01-07"])
    ours = pd.Series([100.0, 100.0, 100.0], index=index)
    constant = [{"Date": d, "AdjC": 50.0} for d in ("2026-01-05", "2026-01-06", "2026-01-07")]
    drifting = [{"Date": "2026-01-05", "AdjC": 100.0}, {"Date": "2026-01-06", "AdjC": 100.0}, {"Date": "2026-01-07", "AdjC": 50.0}]

    assert check_adjustment(ours, constant)["constant"] is True
    assert check_adjustment(ours, drifting)["constant"] is False
    assert check_adjustment(ours, constant[:1])["constant"] is None


def test_correct_adjustment_passes_against_a_single_fetch_but_not_against_mixed_cache_files() -> None:
    """The review's example: files fetched before/after a split disagree on AdjC."""
    from src.evaluation.inflection_historical import check_adjustment

    panel = BarPanel.from_rows(
        {
            "2026-01-05": [_bar("11110", 100.0, 1000.0, 1.0, AdjC=100.0)],  # file fetched before the split
            "2026-01-06": [_bar("11110", 50.0, 1000.0, 0.5, AdjC=50.0)],  # file fetched after it
        }
    )
    ours = panel.evaluation_histories()["1111.T"]["Close"]
    single_fetch = [{"Date": "2026-01-05", "AdjC": 50.0}, {"Date": "2026-01-06", "AdjC": 50.0}]
    cached_files = [{"Date": "2026-01-05", "AdjC": 100.0}, {"Date": "2026-01-06", "AdjC": 50.0}]

    assert check_adjustment(ours, single_fetch)["constant"] is True
    assert check_adjustment(ours, cached_files)["constant"] is False  # why the cache files are not the reference


# --- end to end -------------------------------------------------------------------------------


def test_backtest_report_covers_both_lags_and_the_summary_has_no_tickers() -> None:
    import json

    from src.evaluation.inflection_historical import build_backtest_report, summary_report

    data = _data()
    days = DATES[255:262]

    report = build_backtest_report(
        data, days, deep_candidates=2, min_turnover_jpy=0, control_sample_size=3, log=lambda _: None
    )

    assert report["period"]["signal_days"] == 7 and report["period"]["first_signal_date"] == days[0]
    assert set(report["lags"]) == {"disclosure", "free_12w"}
    for lag_report in report["lags"].values():
        assert set(lag_report["groups"]) == {"early_candidate", "watch", "none", "control"}
        assert lag_report["groups"]["control"]["signal_count"] == 7 * 3
        assert lag_report["kill_criterion"]["verdict"] == "insufficient_sample"  # h60 cannot mature in 40 days
        assert {"portfolio_summary", "tracked_pool_explosion_recall", "yoy_coverage_by_month"} <= set(lag_report)
    assert report["lag_comparison"]["difference"]["definition"]
    assert any("parameter" in note for note in report["notes"])

    summary = json.dumps(summary_report(report), ensure_ascii=False)
    assert '"trades"' not in summary
    assert not any(f"{code[:4]}.T" in summary for code in CODES)
    json.dumps(report)  # the full report is serializable too


def test_yoy_coverage_differs_by_lag_when_the_latest_filing_is_recent() -> None:
    from src.evaluation.inflection_historical import collect_signals

    collected = collect_signals(_data(), DATES[-5:], deep_candidates=3, min_turnover_jpy=0, control_sample_size=0, log=lambda _: None)

    assert collected["disclosure"]["yoy"]["2026-02"]["ratio"] == 1.0
    assert collected["free_12w"]["yoy"]["2026-02"]["ratio"] == 0.0  # a Feb-2026 filing is not usable until April


def test_backtest_report_requires_the_benchmark_in_the_cache() -> None:
    from src.evaluation.inflection_historical import build_backtest_report

    bars = {day: [row for row in rows if row["Code"] != "13060"] for day, rows in _bars().items()}
    with pytest.raises(RuntimeError, match="benchmark"):
        build_backtest_report(_data(bars), DATES[255:257], log=lambda _: None)


def test_the_two_lags_classify_the_same_day_differently_when_the_filing_is_recent() -> None:
    """REQ-041 acceptance 2: a Feb-2026 filing is usable at once, but only from April under the 12-week lag."""
    data = _data()

    now = reconstruct_scan(AS_OF, data, lag="disclosure", deep_candidates=6, min_turnover_jpy=0, control_sample_size=0)
    delayed = reconstruct_scan(AS_OF, data, lag="free_12w", deep_candidates=6, min_turnover_jpy=0, control_sample_size=0)

    by_lag = {
        lag: {row["ticker"]: row["classification"] for row in report["candidates"]}
        for lag, report in (("disclosure", now), ("free_12w", delayed))
    }
    assert by_lag["disclosure"]["6666.T"] == "EARLY_CANDIDATE" and by_lag["free_12w"]["6666.T"] == "NONE"
    assert now["classification_counts"] != delayed["classification_counts"]
    for ticker in by_lag["disclosure"]:  # same prices, so only the usable fundamentals explain the gap
        score_now = next(r["score"] for r in now["candidates"] if r["ticker"] == ticker)
        score_delayed = next(r["score"] for r in delayed["candidates"] if r["ticker"] == ticker)
        assert score_now > score_delayed


# --- memory: shared master rows and optional trade rows --------------------------------------------------


def test_master_rows_identical_on_several_days_are_stored_once_without_changing_results() -> None:
    day1, day2, day3 = "2026-02-02", "2026-02-03", "2026-02-04"
    moved = [{**row, "Mkt": "0113", "MktNm": "Growth"} if row["Code"] == CODES[0] else row for row in _master()]
    masters = MasterHistory({day1: _master(), day2: _master(), day3: moved})

    _, first = masters.as_of(day1)
    _, second = masters.as_of(day2)
    _, third = masters.as_of(day3)

    assert all(first[t] is second[t] for t in first)  # identical rows: one shared object
    assert third["1111.T"] is not first["1111.T"] and third["1111.T"]["MktNm"] == "Growth"  # a changed row is its own
    assert third["2222.T"] is first["2222.T"]
    assert first["1111.T"]["MktNm"] == "Prime"  # the change did not leak back into earlier days


def test_master_history_accepts_a_one_pass_iterator_of_days() -> None:
    days = iter([("2026-02-03", _master()), ("2026-02-02", _master())])  # also out of order

    masters = MasterHistory(days)

    assert masters.as_of("2026-02-02")[0] == "2026-02-02" and masters.as_of("2026-02-10")[0] == "2026-02-03"
    with pytest.raises(ValueError, match="no master"):
        masters.as_of("2026-01-01")


def test_dropping_trade_rows_keeps_every_aggregate_identical() -> None:
    import json

    from src.evaluation.inflection_historical import build_backtest_report, summary_report

    days = DATES[255:259]
    kwargs = {"deep_candidates": 2, "min_turnover_jpy": 0, "control_sample_size": 3, "log": lambda _: None}

    full = build_backtest_report(_data(), days, **kwargs)  # type: ignore[arg-type]
    lean = build_backtest_report(_data(), days, include_trades=False, **kwargs)  # type: ignore[arg-type]

    assert '"trades"' in json.dumps(full) and '"trades"' not in json.dumps(lean)
    stable = {key: value for key, value in summary_report(full).items() if key != "generated_at"}
    assert stable == {key: value for key, value in lean.items() if key != "generated_at"}
