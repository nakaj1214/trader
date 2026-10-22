from __future__ import annotations

from typing import Any

import pandas as pd

from src.evaluation.inflection_event_recall import build_event_recall, extract_events
from src.evaluation.inflection_historical import (
    BarPanel,
    FinancialsStore,
    HistoricalData,
    MasterHistory,
    summary_report,
)


def _data(*, future_price: float = 200.0, market: str = "0111") -> HistoricalData:
    dates = pd.bdate_range("2025-01-06", periods=260)
    prices = [110.0] * 20 + [100.0] * 100 + [149.0, 150.0, 200.0] + [future_price] * 137
    rows = {
        str(day.date()): [
            {"Code": code, "O": price, "H": price * 1.01, "L": price * 0.99, "C": price,
             "Vo": 1e6, "Va": price * 1e6, "AdjFactor": 1.0, "ExRT": None}
            for code in ("11110", "22220")
        ] for day, price in zip(dates, prices, strict=True)
    }
    masters = {str(dates[0].date()): [{"Code": code, "Mkt": market, "CoName": code, "S33": "3650"}
                                      for code in ("11110", "22220")]}
    return HistoricalData(BarPanel.from_rows(rows), MasterHistory(masters), FinancialsStore([]))


def _report(data: HistoricalData, *, financial_start: str | None = None) -> dict[str, Any]:
    dates = data.panel.sessions
    rows = [{"ticker": "1111.T", "classification": "WATCH", "signal_date": dates[120]}]
    return build_event_recall(
        data, data.panel.evaluation_histories(), {"disclosure": rows},
        financial_start=financial_start or dates[0], financial_days=dates,
        deep_candidates=1, focus=("1111.T", "2222.T", "XXXX.T"),
    )


def test_event_definition_ties_long_run_and_missing_market_session() -> None:
    data = _data()
    calendar = pd.DatetimeIndex(pd.to_datetime(data.panel.sessions))
    close = data.panel.evaluation_histories()["1111.T"]["Close"]
    events = extract_events(close, calendar)
    assert len(events) == 1  # Sustained doubling is not a new event every day.
    assert events[0]["trough_date"] == data.panel.sessions[20]
    assert events[0]["confirmation_date"] == data.panel.sessions[122]
    assert events[0]["first_50pct_date"] == data.panel.sessions[121]
    assert extract_events(close.clip(upper=199), calendar) == []
    delayed = extract_events(close.drop(close.index[40]), calendar)
    assert delayed and all(row["confirmation_date"] > data.panel.sessions[160] for row in delayed)


def test_late_watch_keeps_149_multiple_and_unobserved_winner_in_denominator() -> None:
    data = _data()
    report = _report(data)
    assert report["event_count"] == 2
    assert report["price_stages"]["top25"]["evaluated_event_count"] == 2
    finance = report["financial_by_lag"]["disclosure"]
    assert finance["evaluated_event_count"] == 2 and finance["early_detected_event_count"] == 1
    assert finance["early_recall_pct"] == 50.0
    row = report["focus"]["1111.T"][0]
    watch = row["stages"]["early_watch:disclosure"]
    assert watch["price_multiple"] == 1.49 and watch["early"] is True
    assert watch["relative_to_50pct"] == "before" and watch["high_bonus_available"] is False
    assert watch["h60"]["entry_date"] == data.panel.sessions[121]
    assert watch["h60"]["net_return_pct"] is not None
    assert finance["notification_counts_by_session"][data.panel.sessions[120]] == 1
    assert report["focus_status"]["XXXX.T"] == "no_price_history"


def test_threshold_recross_cannot_reuse_a_trough_in_the_previous_event_window() -> None:
    dates = pd.bdate_range("2025-01-06", periods=123)
    closes = pd.Series([100.0] + [160.0] * 49 + [110.0] + [160.0] * 69 + [200.0, 210.0, 220.0], index=dates)
    events = extract_events(closes, dates)
    assert len(events) == 1
    assert events[0]["trough_date"] == str(dates[0].date())


def test_50pct_day_is_detected_but_not_early_and_financial_prestart_is_unknown() -> None:
    data = _data()
    dates = data.panel.sessions
    report = build_event_recall(
        data, data.panel.evaluation_histories(),
        {"lag": [{"ticker": "1111.T", "signal_date": dates[121], "classification": "EARLY_CANDIDATE"}]},
        financial_start=dates[0], financial_days=dates,
    )
    stage = report["event_rows"][0]["stages"]["early_watch:lag"]
    assert stage["status"] == "detected" and stage["early"] is False
    assert stage["relative_to_50pct"] == "on"
    before_start = _report(data, financial_start=dates[21])
    assert before_start["financial_by_lag"]["disclosure"]["unevaluated_event_count"] == 2
    assert before_start["financial_by_lag"]["disclosure"]["evaluated_event_count"] == 0
    assert before_start["financial_by_lag"]["disclosure"]["early_recall_pct"] is None


def test_future_price_changes_do_not_change_existing_stage_arrivals() -> None:
    from src.screening.inflection_live import preselect_candidates

    before = _report(_data())["focus"]["1111.T"][0]
    changed = _data(future_price=400.0)
    raw = changed.panel._tickers["2222.T"].frame
    future = raw.index > pd.Timestamp(changed.panel.sessions[122])
    columns = ["O", "H", "L", "C", "Va"]
    growth = pd.Series([1.005 ** position for position in range(int(future.sum()))], index=raw.index[future])
    raw.loc[future, columns] = raw.loc[future, columns].mul(growth, axis=0)
    last = changed.panel.sessions[-1]
    ranked, _, _ = preselect_candidates(
        changed.panel.frames_as_of(last), changed.masters.as_of(last)[1],
        seed_date=last, min_turnover_jpy=100_000_000,
    )
    assert ranked[0][1] == "2222.T"  # Future competition changes; past ranks must not.
    after = _report(changed)["focus"]["1111.T"][0]
    for name in before["stages"]:
        assert {k: v for k, v in before["stages"][name].items() if k != "h60"} == {
            k: v for k, v in after["stages"][name].items() if k != "h60"
        }


def test_wrong_market_is_excluded_and_default_summary_has_no_event_tickers() -> None:
    assert _report(_data(market="0105"))["event_count"] == 0
    report = _report(_data())
    report["focus"] = {}
    report["focus_status"] = {}
    summary = summary_report({"event_recall": report})
    assert "event_rows" not in summary["event_recall"]
    assert "1111.T" not in str(summary) and "2222.T" not in str(summary)
