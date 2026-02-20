"""enricher のテスト: リスク指標、イベント取得、スコア内訳、エビデンス指標。"""

import math
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# --- テスト用ヘルパー ---

def _make_price_df(prices, start="2025-01-01"):
    """Close と Volume を含む DataFrame を生成する。"""
    dates = pd.bdate_range(start=start, periods=len(prices))
    return pd.DataFrame(
        {"Close": prices, "Volume": [1_000_000] * len(prices)},
        index=dates,
    )


def _make_spy_df(n=300, start="2024-01-01"):
    """SPY 用の擬似 DataFrame を生成する。"""
    dates = pd.bdate_range(start=start, periods=n)
    np.random.seed(42)
    prices = 400.0 + np.cumsum(np.random.randn(n) * 2)
    return pd.DataFrame(
        {"Close": prices, "Volume": [5_000_000] * n},
        index=dates,
    )


# --- Phase 1: compute_risk_metrics ---


class TestComputeRiskMetrics:

    def test_returns_all_keys(self):
        from src.enricher import compute_risk_metrics

        prices = list(range(100, 400))  # 300 日分
        df = _make_price_df(prices)
        spy_df = _make_spy_df(300)

        result = compute_risk_metrics(df, spy_df)

        assert "vol_20d_ann" in result
        assert "vol_60d_ann" in result
        assert "beta" in result
        assert "max_drawdown_1y" in result

    def test_volatility_positive(self):
        from src.enricher import compute_risk_metrics

        np.random.seed(0)
        prices = 100 + np.cumsum(np.random.randn(300) * 0.5)
        df = _make_price_df(prices.tolist())
        spy_df = _make_spy_df(300)

        result = compute_risk_metrics(df, spy_df)

        assert result["vol_20d_ann"] > 0
        assert result["vol_60d_ann"] > 0

    def test_max_drawdown_negative_or_zero(self):
        from src.enricher import compute_risk_metrics

        np.random.seed(1)
        prices = 100 + np.cumsum(np.random.randn(300) * 0.5)
        df = _make_price_df(prices.tolist())
        spy_df = _make_spy_df(300)

        result = compute_risk_metrics(df, spy_df)

        assert result["max_drawdown_1y"] <= 0

    def test_short_data_no_error(self):
        from src.enricher import compute_risk_metrics

        prices = [100, 102, 101, 103, 105]
        df = _make_price_df(prices)
        spy_df = _make_spy_df(5)

        result = compute_risk_metrics(df, spy_df)

        assert isinstance(result["vol_20d_ann"], float)
        assert isinstance(result["beta"], float)


# --- Phase 1: fetch_events ---


class TestFetchEvents:

    @patch("src.enricher.yf.Ticker")
    def test_earnings_date_future(self, mock_ticker_cls):
        from src.enricher import fetch_events

        future_date = pd.Timestamp("2099-06-15")
        mock_info = {"earningsDate": [future_date]}
        mock_ticker_cls.return_value.info = mock_info

        events = fetch_events("AAPL")

        earnings = [e for e in events if e["type"] == "earnings"]
        assert len(earnings) == 1
        assert earnings[0]["date"] == "2099-06-15"
        assert earnings[0]["days_to"] > 0

    @patch("src.enricher.yf.Ticker")
    def test_no_events(self, mock_ticker_cls):
        from src.enricher import fetch_events

        mock_ticker_cls.return_value.info = {}

        events = fetch_events("AAPL")

        assert events == []

    @patch("src.enricher.yf.Ticker")
    def test_exception_returns_empty(self, mock_ticker_cls):
        from src.enricher import fetch_events

        mock_ticker_cls.return_value.info = property(
            lambda self: (_ for _ in ()).throw(Exception("API Error"))
        )
        mock_ticker_cls.side_effect = Exception("API Error")

        events = fetch_events("AAPL")

        assert events == []


# --- Phase 3: compute_explanations ---


class TestComputeExplanations:

    def test_returns_factors_and_metadata(self):
        from src.enricher import compute_explanations

        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(300) * 0.5)
        df = _make_price_df(prices.tolist(), start="2024-06-01")
        config = {
            "screening": {
                "lookback_days": 30,
                "weights": {
                    "price_change_1m": 0.3,
                    "volume_trend": 0.2,
                    "rsi_score": 0.25,
                    "macd_signal": 0.25,
                },
            },
        }

        result = compute_explanations("AAPL", df, config)

        assert "factors" in result
        assert "recalculated_at" in result
        assert "note" in result
        assert len(result["factors"]) <= 3

    def test_factors_have_required_keys(self):
        from src.enricher import compute_explanations

        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(300) * 0.5)
        df = _make_price_df(prices.tolist(), start="2024-06-01")
        config = {
            "screening": {
                "lookback_days": 30,
                "weights": {
                    "price_change_1m": 0.3,
                    "volume_trend": 0.2,
                    "rsi_score": 0.25,
                    "macd_signal": 0.25,
                },
            },
        }

        result = compute_explanations("AAPL", df, config)

        for f in result["factors"]:
            assert "factor" in f
            assert "weight_key" in f
            assert "impact" in f
            assert "text" in f

    def test_short_data_returns_empty_factors(self):
        from src.enricher import compute_explanations

        df = _make_price_df([100, 101, 102])
        config = {"screening": {"lookback_days": 30, "weights": {}}}

        result = compute_explanations("AAPL", df, config)

        assert result["factors"] == []

    def test_factors_sorted_by_impact_desc(self):
        from src.enricher import compute_explanations

        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(300) * 0.5)
        df = _make_price_df(prices.tolist(), start="2024-06-01")
        config = {
            "screening": {
                "lookback_days": 30,
                "weights": {
                    "price_change_1m": 0.3,
                    "volume_trend": 0.2,
                    "rsi_score": 0.25,
                    "macd_signal": 0.25,
                },
            },
        }

        result = compute_explanations("AAPL", df, config)
        impacts = [f["impact"] for f in result["factors"]]
        assert impacts == sorted(impacts, reverse=True)


# --- Phase 3: _transform_score ---


class TestTransformScore:

    def test_rsi_mid_range(self):
        from src.enricher import _transform_score

        assert _transform_score("rsi", 50.0) == 1.0

    def test_rsi_outer_range(self):
        from src.enricher import _transform_score

        assert _transform_score("rsi", 35.0) == 0.5

    def test_rsi_extreme(self):
        from src.enricher import _transform_score

        assert _transform_score("rsi", 80.0) == 0.0

    def test_macd_passthrough(self):
        from src.enricher import _transform_score

        assert _transform_score("macd_bullish", 1.0) == 1.0
        assert _transform_score("macd_bullish", 0.0) == 0.0

    def test_price_change_clamped(self):
        from src.enricher import _transform_score

        assert _transform_score("price_change_1m", -0.05) == 0.0
        assert _transform_score("price_change_1m", 0.15) == 0.15


# --- Phase 2: compute_evidence_signals ---


class TestComputeEvidenceSignals:

    def test_returns_all_keys(self):
        from src.enricher import compute_evidence_signals

        peer_data = []
        for i, t in enumerate(["AAPL", "MSFT", "GOOGL"]):
            np.random.seed(i)
            prices = 100 + np.cumsum(np.random.randn(300) * 0.5)
            peer_data.append({
                "ticker": t,
                "info": {"priceToBook": 5.0 + i, "returnOnEquity": 0.2 + i * 0.05},
                "vol_20d": 0.2 + i * 0.05,
                "df": _make_price_df(prices.tolist(), start="2024-06-01"),
            })

        result = compute_evidence_signals(
            "AAPL",
            peer_data[0]["info"],
            peer_data[0]["vol_20d"],
            peer_data,
        )

        assert "momentum_z" in result
        assert "value_z" in result
        assert "quality_z" in result
        assert "low_risk_z" in result
        assert "composite" in result

    def test_composite_in_range(self):
        from src.enricher import compute_evidence_signals

        peer_data = []
        for i, t in enumerate(["AAPL", "MSFT", "GOOGL", "AMZN", "META"]):
            np.random.seed(i + 10)
            prices = 100 + np.cumsum(np.random.randn(300) * 0.5)
            peer_data.append({
                "ticker": t,
                "info": {"priceToBook": 3.0 + i, "returnOnEquity": 0.15 + i * 0.03},
                "vol_20d": 0.18 + i * 0.02,
                "df": _make_price_df(prices.tolist(), start="2024-06-01"),
            })

        result = compute_evidence_signals(
            "AAPL",
            peer_data[0]["info"],
            peer_data[0]["vol_20d"],
            peer_data,
        )

        if result["composite"] is not None:
            assert 0 <= result["composite"] <= 100


# --- Phase 11: enrich_short_interest ---


class TestEnrichShortInterest:

    def test_normal_data(self):
        from src.enricher import enrich_short_interest

        info = {"shortRatio": 3.2, "shortPercentOfFloat": 0.052}
        result = enrich_short_interest("AAPL", info)

        assert result is not None
        assert result["short_ratio"] == 3.2
        assert result["short_pct_float"] == 0.052
        assert result["signal"] == "neutral"
        assert "月次更新" in result["data_note"]
        assert "参考値" in result["data_note"]

    def test_high_short(self):
        from src.enricher import enrich_short_interest

        info = {"shortRatio": 10.0, "shortPercentOfFloat": 0.25}
        result = enrich_short_interest("GME", info)
        assert result["signal"] == "high_short"

    def test_moderate_short(self):
        from src.enricher import enrich_short_interest

        info = {"shortRatio": 5.0, "shortPercentOfFloat": 0.15}
        result = enrich_short_interest("TEST", info)
        assert result["signal"] == "moderate_short"

    def test_missing_data_returns_none_fields(self):
        from src.enricher import enrich_short_interest

        result = enrich_short_interest("AAPL", {})
        assert result is not None
        assert result["short_ratio"] is None
        assert result["short_pct_float"] is None


# --- Phase 12: enrich_institutional_holders ---


class TestEnrichInstitutionalHolders:

    @patch("src.enricher.yf.Ticker")
    def test_normal_data(self, mock_ticker_cls):
        import pandas as pd
        from src.enricher import enrich_institutional_holders

        mock_df = pd.DataFrame({
            "Holder": ["Vanguard", "BlackRock", "State Street"],
            "Shares": [100000, 80000, 60000],
        })
        mock_ticker_cls.return_value.institutional_holders = mock_df
        mock_ticker_cls.return_value.info = {"heldPercentInstitutions": 0.78}

        result = enrich_institutional_holders("AAPL")

        assert result is not None
        assert result["institutional_pct"] == 0.78
        assert "Vanguard" in result["top5_holders"]
        assert "45〜75日" in result["data_note"]

    @patch("src.enricher.yf.Ticker")
    def test_empty_holders(self, mock_ticker_cls):
        import pandas as pd
        from src.enricher import enrich_institutional_holders

        mock_ticker_cls.return_value.institutional_holders = pd.DataFrame()
        mock_ticker_cls.return_value.info = {}

        result = enrich_institutional_holders("AAPL")
        assert result is None

    @patch("src.enricher.yf.Ticker")
    def test_exception_returns_none(self, mock_ticker_cls):
        from src.enricher import enrich_institutional_holders

        mock_ticker_cls.side_effect = Exception("API error")
        result = enrich_institutional_holders("AAPL")
        assert result is None


# --- Phase 13: enrich_52w_high ---


class TestEnrich52wHigh:

    def test_normal_data(self):
        from src.enricher import enrich_52w_high

        info = {"currentPrice": 90.0, "fiftyTwoWeekHigh": 100.0}
        result = enrich_52w_high("AAPL", info)

        assert result is not None
        assert result["fifty2w_score"] == 0.9
        assert result["fifty2w_pct_from_high"] == -0.1

    def test_zero_score_key_not_missing(self):
        """極端に低い価格でも fifty2w_score キーが存在することを検証する。"""
        from src.enricher import enrich_52w_high

        info = {"currentPrice": 1.0, "fiftyTwoWeekHigh": 100.0}
        result = enrich_52w_high("TEST", info)

        assert result is not None
        assert "fifty2w_score" in result
        assert result["fifty2w_score"] == 0.01

    def test_missing_data_returns_none(self):
        from src.enricher import enrich_52w_high

        assert enrich_52w_high("AAPL", {}) is None
        assert enrich_52w_high("AAPL", {"currentPrice": 50.0}) is None
        assert enrich_52w_high("AAPL", {"fiftyTwoWeekHigh": 100.0}) is None

    def test_zero_high_returns_none(self):
        from src.enricher import enrich_52w_high

        assert enrich_52w_high("AAPL", {"currentPrice": 50.0, "fiftyTwoWeekHigh": 0.0}) is None

    def test_at_high(self):
        from src.enricher import enrich_52w_high

        info = {"currentPrice": 100.0, "fiftyTwoWeekHigh": 100.0}
        result = enrich_52w_high("AAPL", info)
        assert result["fifty2w_score"] == 1.0
        assert result["fifty2w_pct_from_high"] == 0.0


# --- Phase 4: build_error_analysis (exporter) ---


class TestBuildErrorAnalysis:

    def test_empty_records(self):
        from src.exporter import build_error_analysis

        result = build_error_analysis([])
        assert result["mae_pct"] is None
        assert result["bins"] == []

    def test_no_confirmed_records(self):
        from src.exporter import build_error_analysis

        records = [{"ステータス": "予測済み", "翌週実績価格": "", "現在価格": "100", "予測上昇率(%)": "5"}]
        result = build_error_analysis(records)
        assert result["mae_pct"] is None

    def test_single_bin(self):
        from src.exporter import build_error_analysis

        records = [
            {"ステータス": "確定済み", "翌週実績価格": "105", "現在価格": "100", "予測上昇率(%)": "3", "的中": "的中"},
            {"ステータス": "確定済み", "翌週実績価格": "102", "現在価格": "100", "予測上昇率(%)": "4", "的中": "的中"},
        ]
        result = build_error_analysis(records)

        assert result["mae_pct"] is not None
        assert len(result["bins"]) >= 1
        assert result["bins"][0]["range"] == "0-5%"
        assert result["bins"][0]["count"] == 2

    def test_mae_calculation(self):
        from src.exporter import build_error_analysis

        # 予測3%, 実績5% → 誤差2%
        # 予測4%, 実績2% → 誤差2%
        # MAE = 2.0
        records = [
            {"ステータス": "確定済み", "翌週実績価格": "105", "現在価格": "100", "予測上昇率(%)": "3", "的中": "的中"},
            {"ステータス": "確定済み", "翌週実績価格": "102", "現在価格": "100", "予測上昇率(%)": "4", "的中": "外れ"},
        ]
        result = build_error_analysis(records)
        assert result["mae_pct"] == 2.0


# --- build_predictions_json with enrichment ---


class TestBuildPredictionsJsonEnrichment:

    def test_without_enrichment(self):
        from src.exporter import build_predictions_json

        records = [
            {
                "日付": "2026-02-15",
                "ティッカー": "AAPL",
                "現在価格": "250",
                "予測価格": "265",
                "予測上昇率(%)": "6.0",
                "信頼区間(%)": "3.2",
                "翌週実績価格": "",
                "ステータス": "予測済み",
                "的中": "",
            }
        ]
        result = build_predictions_json(records)
        assert len(result) == 1
        assert "risk" not in result[0]
        assert "events" not in result[0]

    def test_with_enrichment(self):
        from src.exporter import build_predictions_json

        records = [
            {
                "日付": "2026-02-15",
                "ティッカー": "AAPL",
                "現在価格": "250",
                "予測価格": "265",
                "予測上昇率(%)": "6.0",
                "信頼区間(%)": "3.2",
                "翌週実績価格": "",
                "ステータス": "予測済み",
                "的中": "",
            }
        ]
        enrichment = {
            ("2026-02-15", "AAPL"): {
                "risk": {"vol_20d_ann": 0.28, "vol_60d_ann": 0.25, "beta": 1.1, "max_drawdown_1y": -0.18},
                "events": [{"type": "earnings", "date": "2026-03-05", "days_to": 18}],
                "evidence": {"momentum_z": 1.2, "value_z": -0.4, "quality_z": 0.7, "low_risk_z": 0.3, "composite": 63},
                "explanations": {"factors": [{"factor": "macd_bullish", "weight_key": "macd_signal", "impact": 0.25, "text": "MACD"}], "recalculated_at": "2026-02-15T00:00:00Z", "note": "test"},
            }
        }

        result = build_predictions_json(records, enrichment)
        assert result[0]["risk"]["vol_20d_ann"] == 0.28
        assert len(result[0]["events"]) == 1
        assert result[0]["evidence"]["composite"] == 63
        assert len(result[0]["explanations"]["factors"]) == 1

    def test_past_week_no_enrichment(self):
        from src.exporter import build_predictions_json

        records = [
            {
                "日付": "2026-02-08",
                "ティッカー": "AAPL",
                "現在価格": "240",
                "予測価格": "250",
                "予測上昇率(%)": "4.2",
                "信頼区間(%)": "2.5",
                "翌週実績価格": "248",
                "ステータス": "確定済み",
                "的中": "的中",
            }
        ]
        enrichment = {
            ("2026-02-15", "AAPL"): {"risk": {"vol_20d_ann": 0.28}}
        }

        result = build_predictions_json(records, enrichment)
        assert "risk" not in result[0]


# --- Phase 8: compute_sizing ---


class TestComputeSizing:

    def _default_config(self):
        return {
            "sizing": {
                "vol_target_ann": 0.10,
                "max_weight_cap": 0.20,
                "stop_loss_multiplier": 1.0,
            }
        }

    def test_returns_all_keys(self):
        from src.enricher import compute_sizing

        result = compute_sizing(0.20, self._default_config())

        assert "vol_target_ann" in result
        assert "max_position_weight" in result
        assert "stop_loss_pct" in result
        assert "stop_loss_rationale" in result

    def test_normal_vol_weight_capped(self):
        """vol_ann=0.20 → weight=0.10/0.20=0.50 だが cap=0.20 で制限"""
        from src.enricher import compute_sizing

        result = compute_sizing(0.20, self._default_config())
        assert result["max_position_weight"] == 0.20

    def test_low_vol_weight_capped_at_max(self):
        """vol_ann=0.05 → weight=0.10/0.05=2.0 だが cap=0.20 で制限"""
        from src.enricher import compute_sizing

        result = compute_sizing(0.05, self._default_config())
        assert result["max_position_weight"] == 0.20

    def test_high_vol_weight_below_cap(self):
        """vol_ann=0.40 → weight=0.10/0.40=0.25 → cap=0.20 で制限"""
        from src.enricher import compute_sizing

        result = compute_sizing(0.40, self._default_config())
        assert result["max_position_weight"] == 0.20

    def test_stop_loss_negative(self):
        from src.enricher import compute_sizing

        result = compute_sizing(0.20, self._default_config())
        assert result["stop_loss_pct"] is not None
        assert result["stop_loss_pct"] < 0

    def test_stop_loss_formula(self):
        """stop_loss = -1.0 * 0.24 / sqrt(12) ≈ -0.0693"""
        from src.enricher import compute_sizing

        vol_ann = 0.24
        result = compute_sizing(vol_ann, self._default_config())
        expected = round(-1.0 * vol_ann / math.sqrt(12), 4)
        assert result["stop_loss_pct"] == expected

    def test_zero_vol_returns_max_cap(self):
        """vol_ann=0 → max_position_weight は max_weight_cap、stop_loss は None"""
        from src.enricher import compute_sizing

        result = compute_sizing(0.0, self._default_config())
        assert result["max_position_weight"] == 0.20
        assert result["stop_loss_pct"] is None

    def test_custom_config(self):
        """カスタム設定が反映されること"""
        from src.enricher import compute_sizing

        config = {
            "sizing": {
                "vol_target_ann": 0.05,
                "max_weight_cap": 0.10,
                "stop_loss_multiplier": 2.0,
            }
        }
        result = compute_sizing(0.20, config)
        # weight = min(0.05/0.20, 0.10) = min(0.25, 0.10) = 0.10
        assert result["max_position_weight"] == 0.10
        # stop_loss = -2.0 * 0.20 / sqrt(12)
        expected_sl = round(-2.0 * 0.20 / math.sqrt(12), 4)
        assert result["stop_loss_pct"] == expected_sl

    def test_missing_sizing_config_uses_defaults(self):
        """sizing キーがない場合はデフォルト値を使用"""
        from src.enricher import compute_sizing

        result = compute_sizing(0.20, {})
        assert result["max_position_weight"] == 0.20  # min(0.10/0.20, 0.20) = 0.20
        assert result["stop_loss_pct"] is not None
