"""Market-wide, retrospectively labelled events measured with point-in-time selection."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING, Any

import pandas as pd

from src.evaluation.inflection_backtest import _series, simulate_signals, summarize_trades
from src.evaluation.inflection_report import ROUND_TRIP_COST_PCT
from src.screening.inflection_live import preselect_candidates

if TYPE_CHECKING:
    from src.evaluation.inflection_historical import HistoricalData

EVENT_WINDOW = 120
EVENT_MULTIPLE = 2.0
EARLY_MULTIPLE = 1.5
PRICE_STAGES = ("price_usable", "liquid", "top25")


def extract_events(closes: pd.Series, calendar: pd.DatetimeIndex) -> list[dict[str, Any]]:
    """Confirm a doubling against the previous 120 complete market sessions."""
    values = _series(pd.DataFrame({"Close": closes}), "Close").reindex(calendar)
    floors = values.shift(1).rolling(EVENT_WINDOW, min_periods=EVENT_WINDOW).min()
    above = values.ge(floors * EVENT_MULTIPLE)
    hits = above & ~above.shift(1, fill_value=False)
    events: list[dict[str, Any]] = []
    blocked_until = -1
    for position in range(EVENT_WINDOW, len(calendar)):
        if position <= blocked_until or not hits.iloc[position]:
            continue
        window = values.iloc[position - EVENT_WINDOW:position]
        trough = window.idxmin()  # idxmin keeps the earliest equal low.
        trough_position = int(calendar.get_loc(trough))
        if trough_position <= blocked_until:
            continue
        first50 = values.iloc[trough_position:position + 1]
        first50 = first50[first50 >= float(values.loc[trough]) * EARLY_MULTIPLE].index[0]
        end = calendar[min(trough_position + EVENT_WINDOW, len(calendar) - 1)]
        events.append({
            "trough_date": str(trough.date()),
            "confirmation_date": str(calendar[position].date()),
            "first_50pct_date": str(first50.date()),
            "measurement_end": str(end.date()),
        })
        blocked_until = trough_position + EVENT_WINDOW
    return events


def _arrival(
    event: dict[str, Any], day: str, close: pd.Series, high_bonus_available: bool,
) -> dict[str, Any]:
    return {
        "status": "detected", "signal_date": day,
        "price_multiple": round(float(close.loc[day]) / float(close.loc[event["trough_date"]]), 6),
        "early": day < event["first_50pct_date"],
        "relative_to_50pct": ("before" if day < event["first_50pct_date"] else
                              "on" if day == event["first_50pct_date"] else "after"),
        "high_bonus_available": high_bonus_available,
    }


def _summarize_stage(
    events: list[dict[str, Any]], name: str, histories: dict[str, pd.DataFrame], calendar: pd.DatetimeIndex,
) -> dict[str, Any]:
    evaluated = [event for event in events if event["stages"][name]["status"] != "unevaluated"]
    detected = [event for event in evaluated if event["stages"][name]["status"] == "detected"]
    early = sum(bool(event["stages"][name]["early"]) for event in detected)
    signals = [{"ticker": event["ticker"], "signal_date": event["stages"][name]["signal_date"], "score": 0.0}
               for event in detected]
    trades = simulate_signals(
        signals, histories, holding_days=60, round_trip_cost_pct=ROUND_TRIP_COST_PCT,
        apply_tax=False, market_calendar=calendar,
    )
    for event, trade in zip(detected, trades, strict=True):
        event["stages"][name]["h60"] = {
            "entry_date": trade.entry_date, "exit_date": trade.exit_date,
            "net_return_pct": trade.net_return_pct, "horizon_matured": trade.horizon_matured,
            "price_diagnostics": trade.price_diagnostics,
        }
    return {
        "evaluated_event_count": len(evaluated), "unevaluated_event_count": len(events) - len(evaluated),
        "detected_event_count": len(detected), "early_detected_event_count": early,
        "early_recall_pct": round(early / len(evaluated) * 100.0, 6) if evaluated else None,
        "h60": summarize_trades(trades),
    }


def build_event_recall(
    data: HistoricalData,
    histories: dict[str, pd.DataFrame],
    signals_by_lag: dict[str, list[dict[str, Any]]],
    *,
    financial_start: str | None,
    financial_days: list[str],
    deep_candidates: int = 25,
    min_turnover_jpy: float = 100_000_000,
    focus: tuple[str, ...] = (),
    include_events: bool = True,
) -> dict[str, Any]:
    calendar = pd.DatetimeIndex(pd.to_datetime(data.panel.sessions))
    events: list[dict[str, Any]] = []
    excluded_universe = 0
    label_incomplete = 0
    for ticker, history in histories.items():
        close = _series(history, "Close")
        aligned = close.reindex(calendar)
        counts = aligned.shift(1).rolling(EVENT_WINDOW, min_periods=0).count()
        label_incomplete += int((aligned.notna() & counts.lt(EVENT_WINDOW)).sum())
        for event in extract_events(close, calendar):
            if any(ticker not in data.masters.as_of(event[key])[1] for key in ("trough_date", "confirmation_date")):
                excluded_universe += 1
                continue
            event["ticker"] = ticker
            event["stages"] = {stage: {"status": "not_detected"} for stage in PRICE_STAGES}
            events.append(event)

    # Only days in confirmed event windows need a market-wide rank; missing market days remain missing.
    active: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        for stamp in calendar[(calendar >= event["trough_date"]) & (calendar <= event["measurement_end"])]:
            active[str(stamp.date())].append(event)
    excluded_price_days = 0
    for day in sorted(active):
        _, meta = data.masters.as_of(day)
        frames = {ticker: frame for ticker, frame in data.panel.frames_as_of(day).items() if ticker in meta}
        liquid, usable, _ = preselect_candidates(frames, meta, seed_date=day, min_turnover_jpy=min_turnover_jpy)
        reached = {"price_usable": usable, "liquid": {ticker for _, ticker, _ in liquid},
                   "top25": {ticker for _, ticker, _ in liquid[:deep_candidates]}}
        for event in active[day]:
            ticker = event["ticker"]
            if ticker not in usable:
                excluded_price_days += 1
            for stage in PRICE_STAGES:
                if ticker in reached[stage] and event["stages"][stage]["status"] == "not_detected":
                    event["stages"][stage] = _arrival(event, day, histories[ticker]["Close"], len(frames[ticker]) >= 252)

    stages = {stage: _summarize_stage(events, stage, histories, calendar) for stage in PRICE_STAGES}
    financial: dict[str, Any] = {}
    covered = set(financial_days)
    for lag, signals in signals_by_lag.items():
        by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
        notices = Counter({day: 0 for day in financial_days})
        for signal in signals:
            if signal["classification"] in {"EARLY_CANDIDATE", "WATCH"}:
                by_ticker[str(signal["ticker"])].append(signal)
                notices[str(signal["signal_date"])] += 1
        name = f"early_watch:{lag}"
        for event in events:
            window = calendar[(calendar >= event["trough_date"]) & (calendar <= event["measurement_end"])]
            if financial_start is None or event["trough_date"] < financial_start or any(
                str(stamp.date()) not in covered for stamp in window
            ):
                event["stages"][name] = {"status": "unevaluated", "reason": "financial_history_unavailable"}
                continue
            rows = [row for row in by_ticker[event["ticker"]]
                    if event["trough_date"] <= row["signal_date"] <= event["measurement_end"]]
            if rows:
                day = min(str(row["signal_date"]) for row in rows)
                frame = data.panel.frames_as_of(day)[event["ticker"]]
                event["stages"][name] = _arrival(event, day, histories[event["ticker"]]["Close"], len(frame) >= 252)
            else:
                event["stages"][name] = {"status": "not_detected"}
        financial[lag] = {**_summarize_stage(events, name, histories, calendar),
                          "notification_counts_by_session": dict(sorted(notices.items()))}

    result: dict[str, Any] = {
        "definition": {
            "window_market_sessions": EVENT_WINDOW, "confirmation_multiple": EVENT_MULTIPLE,
            "early_multiple": EARLY_MULTIPLE, "include_50pct_day_in_early": False,
            "trough_tie": "earliest", "confirmation_window": "120 complete sessions strictly before H",
            "suppression": "through trough + 120 market sessions",
            "measurement_window": "trough through trough + 120 sessions, capped at available end",
            "holding_sessions": 60, "round_trip_cost_pct": ROUND_TRIP_COST_PCT,
            "financial_start": financial_start, "deep_candidates": deep_candidates,
        },
        "event_count": len(events), "excluded_outside_universe_count": excluded_universe,
        "incomplete_label_window_session_count": label_incomplete,
        "unevaluable_event_price_session_count": excluded_price_days,
        "price_stages": stages, "financial_by_lag": financial,
        "focus": {ticker: [event for event in events if event["ticker"] == ticker] for ticker in focus},
        "focus_status": {ticker: ("events_found" if any(e["ticker"] == ticker for e in events) else
                                  "no_confirmed_event" if ticker in histories else "no_price_history")
                         for ticker in focus},
        "notes": [
            "Labels use J-Quants split-adjusted closes; production uses yfinance dividend-adjusted prices.",
            "Variant B is a comparison, not a target: its 60-bar high bonus differs from the unchanged 252-bar rule.",
            "Event definitions and measurement windows differ from the prototype's exemplar low-to-global-peak window.",
            "Notification counts are EARLY + WATCH candidates, before Slack display limits; no messages are sent.",
            "First usable open is a backtest convention, not proof of execution; returns are descriptive, not acceptance.",
        ],
    }
    if include_events:
        result["event_rows"] = events
    return result
