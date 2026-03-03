"""Backtest module: multi-strategy comparison.

Migrated from src/baseline.py. Compares AI predictions, 12-1 momentum,
and SPY benchmark using weekly return series.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

MOM_SKIP_WEEKS = 4
MOM_SPAN_WEEKS = 52
MOM_MIN_WEEKS = MOM_SKIP_WEEKS + MOM_SPAN_WEEKS


def portfolio_stats(returns: pd.Series) -> dict[str, Any]:
    """Compute annualized portfolio statistics from weekly returns.

    Args:
        returns: Weekly return series (decimal: 0.01 = 1%).

    Returns:
        Dict with cagr, max_drawdown, sharpe.
    """
    if len(returns) < 4:
        return {"cagr": None, "max_drawdown": None, "sharpe": None}

    weeks = len(returns)
    cumulative = float((1 + returns).prod())
    cagr = round(float(cumulative ** (52.0 / weeks) - 1), 4) if weeks > 0 else None

    equity = (1 + returns).cumprod()
    peak = equity.cummax()
    dd = (equity - peak) / peak
    max_dd = round(float(dd.min()), 4)

    std = returns.std()
    eps = 1e-12
    sharpe = round(float((returns.mean() / std) * (52 ** 0.5)), 2) if std > eps else None

    return {"cagr": cagr, "max_drawdown": max_dd, "sharpe": sharpe}


def equity_curve(returns: pd.Series) -> list[dict[str, Any]]:
    """Convert weekly returns to equity curve list."""
    eq = (1 + returns).cumprod()
    result: list[dict[str, Any]] = []
    for date, val in eq.items():
        try:
            date_str = str(date.date())
        except AttributeError:
            date_str = str(date)
        result.append({"date": date_str, "equity": round(float(val), 4)})
    return result


def compute_baseline_momentum(
    prices: dict[str, pd.DataFrame],
    top_n: int = 10,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    """Compute 12-1 momentum top-N equal-weight weekly returns.

    Args:
        prices: Mapping of ticker -> price DataFrame with Close.
        top_n: Number of top momentum stocks per week.

    Returns:
        Tuple of (weekly returns Series, equity curve list).
    """
    if not prices:
        return pd.Series(dtype=float), []

    closes: dict[str, pd.Series] = {}
    for ticker, df in prices.items():
        try:
            s = df["Close"].squeeze()
            if isinstance(s, pd.Series) and not s.empty:
                closes[ticker] = s
        except Exception:
            continue

    if not closes:
        return pd.Series(dtype=float), []

    combined = pd.DataFrame(closes)
    weekly: pd.DataFrame = combined.resample("W").last()

    if len(weekly) < MOM_MIN_WEEKS + 2:
        logger.info(
            "momentum_data_insufficient",
            weeks=len(weekly),
            min_required=MOM_MIN_WEEKS + 2,
        )
        return pd.Series(dtype=float), []

    weekly_returns: list[float] = []
    weekly_dates: list[Any] = []

    for i in range(MOM_MIN_WEEKS, len(weekly) - 1):
        end_idx = i - MOM_SKIP_WEEKS
        start_idx = i - MOM_MIN_WEEKS

        if start_idx < 0 or end_idx < 0:
            continue

        scores: dict[str, float] = {}
        for ticker in weekly.columns:
            try:
                end_p = float(weekly[ticker].iloc[end_idx])
                start_p = float(weekly[ticker].iloc[start_idx])
                if np.isnan(end_p) or np.isnan(start_p) or start_p <= 0:
                    continue
                scores[ticker] = (end_p - start_p) / start_p
            except Exception:
                continue

        if len(scores) < top_n:
            continue

        top_tickers = sorted(scores, key=lambda k: scores[k], reverse=True)[:top_n]

        next_rets: list[float] = []
        for ticker in top_tickers:
            try:
                curr = float(weekly[ticker].iloc[i])
                nxt = float(weekly[ticker].iloc[i + 1])
                if np.isnan(curr) or np.isnan(nxt) or curr <= 0:
                    continue
                next_rets.append((nxt - curr) / curr)
            except Exception:
                continue

        if not next_rets:
            continue

        weekly_returns.append(float(np.mean(next_rets)))
        weekly_dates.append(weekly.index[i + 1])

    if not weekly_returns:
        return pd.Series(dtype=float), []

    series = pd.Series(weekly_returns, index=pd.DatetimeIndex(weekly_dates))
    return series, equity_curve(series)


def compute_ai_weekly_returns(
    records: list[dict[str, Any]],
) -> tuple[pd.Series, list[dict[str, Any]]]:
    """Compute AI strategy weekly returns from confirmed prediction records.

    Each week's return is the equal-weight average of actual returns.

    Args:
        records: List of prediction record dicts (from DB or Sheets).

    Returns:
        Tuple of (weekly returns Series, equity curve list).
    """
    confirmed_by_week: dict[str, list[float]] = {}
    for r in records:
        status = r.get("status", r.get("ステータス", ""))
        if status not in ("confirmed", "確定済み"):
            continue
        try:
            actual = float(r.get("actual_price", r.get("翌週実績価格", "")))
            current = float(r.get("current_price", r.get("現在価格", "")))
        except (ValueError, TypeError):
            continue
        if actual <= 0 or current <= 0:
            continue
        date = r.get("date", r.get("日付", ""))
        if date not in confirmed_by_week:
            confirmed_by_week[date] = []
        confirmed_by_week[date].append((actual - current) / current)

    if not confirmed_by_week:
        return pd.Series(dtype=float), []

    dates = sorted(confirmed_by_week.keys())
    returns = [float(np.mean(confirmed_by_week[d])) for d in dates]
    series = pd.Series(returns, index=pd.DatetimeIndex(dates))
    return series, equity_curve(series)


def compute_spy_weekly_returns(
    spy_df: pd.DataFrame,
) -> tuple[pd.Series, list[dict[str, Any]]]:
    """Compute SPY weekly returns.

    Args:
        spy_df: SPY daily price DataFrame with Close column.

    Returns:
        Tuple of (weekly returns Series, equity curve list).
    """
    try:
        close = spy_df["Close"].squeeze()
        weekly = close.resample("W").last().dropna()
        returns = weekly.pct_change().dropna()
        if returns.empty:
            return pd.Series(dtype=float), []
        return returns, equity_curve(returns)
    except Exception:
        logger.exception("spy_weekly_returns_error")
        return pd.Series(dtype=float), []


def build_backtest_hygiene(
    config: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build backtest quality disclosure metadata.

    Args:
        config: Application configuration.
        records: All prediction records.

    Returns:
        Backtest hygiene metadata dict.
    """
    bt_cfg = config.get("evaluation", {}).get("backtest", {})
    num_rules = int(bt_cfg.get("num_rules_tested", 1))
    num_params = int(bt_cfg.get("num_parameters_tuned", 4))
    oos_start = str(bt_cfg.get("oos_start", ""))
    min_rules = int(bt_cfg.get("min_rules_for_pbo", 2))

    confirmed_dates = set()
    for r in records:
        hit = r.get("is_hit", r.get("的中", ""))
        if hit in (True, False, "的中", "外れ"):
            date = r.get("date", r.get("日付", ""))
            if date:
                confirmed_dates.add(date)
    coverage_weeks = len(confirmed_dates)

    deflated_sharpe: float | None = None
    if num_rules >= 1 and num_params >= 1:
        penalty = float(num_rules * num_params) ** 0.5
        deflated_sharpe = round(1.0 / penalty, 4)

    if num_rules >= min_rules:
        reality_check_pvalue: float | None = round(1.0 / num_rules, 4)
        pbo: float | None = round(0.5 / num_rules, 4)
        hygiene_status = "computed"
        hygiene_note = "Quality metrics computed (simplified estimates)"
        is_placeholder = True
    else:
        reality_check_pvalue = None
        pbo = None
        hygiene_status = "insufficient_trials"
        hygiene_note = (
            f"num_rules_tested ({num_rules}) < min_rules_for_pbo ({min_rules}), "
            "pbo / reality_check_pvalue not computable"
        )
        is_placeholder = None

    return {
        "num_rules_tested": num_rules,
        "num_parameters_tuned": num_params,
        "oos_start": oos_start,
        "data_coverage_weeks": coverage_weeks,
        "transaction_cost_note": "Transaction costs and taxes not considered",
        "survivorship_bias_note": "Delisted stocks excluded (survivorship bias present)",
        "hygiene_status": hygiene_status,
        "is_placeholder": is_placeholder,
        "reality_check_pvalue": reality_check_pvalue,
        "pbo": pbo,
        "deflated_sharpe": deflated_sharpe,
        "hygiene_note": hygiene_note,
    }


def build_comparison_json(
    ai_returns: pd.Series,
    ai_eq: list[dict[str, Any]],
    momentum_returns: pd.Series,
    momentum_eq: list[dict[str, Any]],
    spy_returns: pd.Series,
    spy_eq: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build 3-strategy comparison data.

    Returns:
        comparison.json-compatible dict.
    """
    strategies: dict[str, Any] = {}

    if not ai_returns.empty:
        stats = portfolio_stats(ai_returns)
        strategies["ai"] = {
            "label": "AI Prediction (Weekly Top10)",
            **stats,
            "equity_curve": ai_eq,
        }

    if not momentum_returns.empty:
        stats = portfolio_stats(momentum_returns)
        strategies["momentum_12_1"] = {
            "label": "12-1 Momentum (Top10)",
            **stats,
            "equity_curve": momentum_eq,
        }

    if not spy_returns.empty:
        stats = portfolio_stats(spy_returns)
        strategies["benchmark_spy"] = {
            "label": "SPY (Benchmark)",
            **stats,
            "equity_curve": spy_eq,
        }

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "strategies": strategies,
    }
