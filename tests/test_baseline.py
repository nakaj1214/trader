"""baseline のテスト: 週次リターン計算、統計指標、比較JSON構築。"""

import numpy as np
import pandas as pd
import pytest

from src.baseline import (
    _equity_curve,
    _portfolio_stats,
    build_backtest_hygiene,
    build_comparison_json,
    compute_ai_weekly_returns,
    compute_baseline_momentum,
    compute_spy_weekly_returns,
)


# --- _portfolio_stats ---


def test_portfolio_stats_basic():
    """リターン系列から CAGR / 最大DD / Sharpe が算出されること。"""
    returns = pd.Series([0.01, 0.02, -0.01, 0.015, 0.005] * 10)
    stats = _portfolio_stats(returns)

    assert stats["cagr"] is not None
    assert stats["max_drawdown"] is not None
    assert stats["sharpe"] is not None
    assert stats["max_drawdown"] <= 0.0  # DD は 0 以下


def test_portfolio_stats_insufficient_data():
    """データが 4 件未満の場合は None を返すこと。"""
    returns = pd.Series([0.01, 0.02, 0.03])
    stats = _portfolio_stats(returns)
    assert stats["cagr"] is None
    assert stats["max_drawdown"] is None
    assert stats["sharpe"] is None


def test_portfolio_stats_zero_std():
    """全リターンが同値（分散 0）の場合、Sharpe が None になること。"""
    returns = pd.Series([0.01] * 10)
    stats = _portfolio_stats(returns)
    assert stats["sharpe"] is None


# --- _equity_curve ---


def test_equity_curve_format():
    """equity_curve が {"date": str, "equity": float} のリストであること。"""
    idx = pd.date_range("2025-01-06", periods=4, freq="W")
    returns = pd.Series([0.01, -0.005, 0.02, 0.015], index=idx)
    curve = _equity_curve(returns)

    assert len(curve) == 4
    for pt in curve:
        assert "date" in pt and "equity" in pt
        assert isinstance(pt["date"], str)
        assert isinstance(pt["equity"], float)

    # 初期値 (1+r1) = 1.01
    assert abs(curve[0]["equity"] - 1.01) < 1e-6


# --- compute_ai_weekly_returns ---


SAMPLE_RECORDS = [
    {
        "日付": "2025-01-10",
        "ティッカー": "AAPL",
        "現在価格": "200.0",
        "翌週実績価格": "210.0",
        "ステータス": "確定済み",
    },
    {
        "日付": "2025-01-10",
        "ティッカー": "MSFT",
        "現在価格": "400.0",
        "翌週実績価格": "380.0",
        "ステータス": "確定済み",
    },
    {
        "日付": "2025-01-17",
        "ティッカー": "GOOGL",
        "現在価格": "150.0",
        "翌週実績価格": "160.0",
        "ステータス": "確定済み",
    },
    # 予測済み（実績なし）は無視される
    {
        "日付": "2025-01-24",
        "ティッカー": "NVDA",
        "現在価格": "500.0",
        "翌週実績価格": "",
        "ステータス": "予測済み",
    },
]


def test_compute_ai_weekly_returns_basic():
    """確定済みレコードから週次リターンが算出されること。"""
    returns, curve = compute_ai_weekly_returns(SAMPLE_RECORDS)

    # 週 1: (210-200)/200=0.05, (380-400)/400=-0.05 → 平均 0.0
    # 週 2: (160-150)/150 ≈ 0.0667
    assert len(returns) == 2
    assert abs(returns.iloc[0] - 0.0) < 1e-9
    assert abs(returns.iloc[1] - (10 / 150)) < 1e-9
    assert len(curve) == 2


def test_compute_ai_weekly_returns_empty():
    """確定済みレコードがない場合は空 Series を返すこと。"""
    returns, curve = compute_ai_weekly_returns([])
    assert returns.empty
    assert curve == []


def test_compute_ai_weekly_returns_skips_invalid():
    """価格が 0 や変換不能な値のレコードはスキップされること。"""
    records = [
        {
            "日付": "2025-01-10",
            "ティッカー": "BAD",
            "現在価格": "0.0",
            "翌週実績価格": "100.0",
            "ステータス": "確定済み",
        },
        {
            "日付": "2025-01-10",
            "ティッカー": "GOOD",
            "現在価格": "100.0",
            "翌週実績価格": "110.0",
            "ステータス": "確定済み",
        },
    ]
    returns, _ = compute_ai_weekly_returns(records)
    assert len(returns) == 1
    assert abs(returns.iloc[0] - 0.1) < 1e-9


# --- compute_spy_weekly_returns ---


def _make_spy_df(n_days: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2024-09-01", periods=n_days, freq="B")
    close = pd.Series(np.cumprod(1 + np.random.normal(0.0005, 0.01, n_days)) * 500, index=idx)
    return pd.DataFrame({"Close": close})


def test_compute_spy_weekly_returns_basic():
    spy_df = _make_spy_df(120)
    returns, curve = compute_spy_weekly_returns(spy_df)

    assert not returns.empty
    assert len(curve) > 0
    for pt in curve:
        assert "date" in pt and "equity" in pt


def test_compute_spy_weekly_returns_empty_df():
    empty = pd.DataFrame({"Close": pd.Series(dtype=float)})
    returns, curve = compute_spy_weekly_returns(empty)
    assert returns.empty
    assert curve == []


# --- compute_baseline_momentum ---


def _make_price_data(n_tickers: int = 15, n_days: int = 600) -> dict:
    """十分な履歴を持つダミー株価データを生成する。"""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2023-01-01", periods=n_days, freq="B")
    prices = {}
    for i in range(n_tickers):
        daily_ret = rng.normal(0.0003, 0.012, n_days)
        close = np.cumprod(1 + daily_ret) * (100 + i * 10)
        prices[f"TICK{i:02d}"] = pd.DataFrame({"Close": close}, index=idx)
    return prices


def test_compute_baseline_momentum_basic():
    """十分なデータがあればリターン系列が返ること。"""
    prices = _make_price_data(n_tickers=15, n_days=600)
    returns, curve = compute_baseline_momentum(prices, top_n=5)

    assert not returns.empty
    assert len(curve) > 0


def test_compute_baseline_momentum_insufficient_data():
    """データが不足している場合は空 Series を返すこと。"""
    # 30 日分しかない（56 週のルックバックに全然足りない）
    idx = pd.date_range("2025-01-01", periods=30, freq="B")
    prices = {
        f"T{i}": pd.DataFrame({"Close": np.ones(30) * (100 + i)}, index=idx)
        for i in range(10)
    }
    returns, curve = compute_baseline_momentum(prices, top_n=5)
    assert returns.empty
    assert curve == []


def test_compute_baseline_momentum_empty():
    returns, curve = compute_baseline_momentum({}, top_n=10)
    assert returns.empty
    assert curve == []


# --- build_comparison_json ---


def test_build_comparison_json_schema():
    """strategies キーに各戦略が格納されること。"""
    idx = pd.date_range("2025-01-06", periods=10, freq="W")
    ai_ret = pd.Series(np.random.normal(0.005, 0.02, 10), index=idx)
    mom_ret = pd.Series(np.random.normal(0.003, 0.02, 10), index=idx)
    spy_ret = pd.Series(np.random.normal(0.002, 0.015, 10), index=idx)

    ai_eq = _equity_curve(ai_ret)
    mom_eq = _equity_curve(mom_ret)
    spy_eq = _equity_curve(spy_ret)

    result = build_comparison_json(ai_ret, ai_eq, mom_ret, mom_eq, spy_ret, spy_eq)

    assert "updated_at" in result
    assert "strategies" in result
    strategies = result["strategies"]
    assert "ai" in strategies
    assert "momentum_12_1" in strategies
    assert "benchmark_spy" in strategies

    for key in strategies:
        s = strategies[key]
        assert "label" in s
        assert "cagr" in s
        assert "max_drawdown" in s
        assert "sharpe" in s
        assert "equity_curve" in s


def test_build_comparison_json_empty_strategies():
    """全戦略が空の場合、strategies が空辞書であること。"""
    empty = pd.Series(dtype=float)
    result = build_comparison_json(empty, [], empty, [], empty, [])
    assert result["strategies"] == {}


# --- Phase 9: build_backtest_hygiene ---


def _make_records(n_confirmed=0, n_pending=0):
    """テスト用レコードを生成する。"""
    records = []
    for i in range(n_confirmed):
        records.append({"日付": f"2025-{i+1:02d}-01", "ティッカー": "AAPL", "的中": "的中"})
    for i in range(n_pending):
        records.append({"日付": f"2026-{i+1:02d}-01", "ティッカー": "MSFT", "的中": ""})
    return records


def test_build_backtest_hygiene_returns_all_keys():
    """必須キーが全て返ること。"""
    config = {"backtest": {"num_rules_tested": 1, "num_parameters_tuned": 4, "oos_start": "2025-01-01", "min_rules_for_pbo": 2}}
    result = build_backtest_hygiene(config, [])

    for key in ("num_rules_tested", "num_parameters_tuned", "oos_start", "data_coverage_weeks",
                "transaction_cost_note", "survivorship_bias_note", "hygiene_status",
                "reality_check_pvalue", "pbo", "deflated_sharpe", "hygiene_note"):
        assert key in result, f"キー '{key}' が存在しません"


def test_build_backtest_hygiene_insufficient_trials():
    """num_rules_tested < min_rules_for_pbo のとき hygiene_status が insufficient_trials になること。"""
    config = {"backtest": {"num_rules_tested": 1, "num_parameters_tuned": 4, "oos_start": "2025-01-01", "min_rules_for_pbo": 2}}
    result = build_backtest_hygiene(config, [])

    assert result["hygiene_status"] == "insufficient_trials"
    assert result["reality_check_pvalue"] is None
    assert result["pbo"] is None


def test_build_backtest_hygiene_computed():
    """num_rules_tested >= min_rules_for_pbo のとき hygiene_status が computed になること。"""
    config = {"backtest": {"num_rules_tested": 5, "num_parameters_tuned": 4, "oos_start": "2025-01-01", "min_rules_for_pbo": 2}}
    result = build_backtest_hygiene(config, [])

    assert result["hygiene_status"] == "computed"
    assert result["reality_check_pvalue"] is not None
    assert result["pbo"] is not None


def test_build_backtest_hygiene_deflated_sharpe_present():
    """deflated_sharpe が num_rules=1 でも算出されること（単独算出可能）。"""
    config = {"backtest": {"num_rules_tested": 1, "num_parameters_tuned": 4, "oos_start": "2025-01-01", "min_rules_for_pbo": 2}}
    result = build_backtest_hygiene(config, [])

    assert result["deflated_sharpe"] is not None


def test_build_backtest_hygiene_data_coverage_weeks():
    """確定済みレコードの週数が data_coverage_weeks に反映されること。"""
    config = {"backtest": {"num_rules_tested": 1, "num_parameters_tuned": 4, "oos_start": "2025-01-01", "min_rules_for_pbo": 2}}
    records = _make_records(n_confirmed=3, n_pending=2)
    result = build_backtest_hygiene(config, records)

    # 3 週分の confirmed (「的中」のみカウント)
    assert result["data_coverage_weeks"] == 3


def test_build_backtest_hygiene_missing_config_uses_defaults():
    """backtest キーがない場合もエラーなく動作すること。"""
    result = build_backtest_hygiene({}, [])

    assert result["hygiene_status"] == "insufficient_trials"
    assert result["num_rules_tested"] == 1
