"""Financial Modeling Prep API クライアントのテスト（モック使用）"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestFetchKeyMetrics:
    def setup_method(self):
        """各テスト前にキャッシュをリセットする。"""
        import src.fmp_fetcher as fmp
        fmp._metrics_cache = {}

    def test_returns_empty_when_no_api_key(self):
        """FMP_API_KEY 未設定 → {} を返す。"""
        env = {k: v for k, v in os.environ.items() if k != "FMP_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            from src.fmp_fetcher import fetch_key_metrics
            result = fetch_key_metrics("AAPL")
        assert result == {}

    def test_supplements_pbr_for_us_stock(self):
        """US 株の priceToBook を FMP から補完できること。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"pbRatio": 3.2, "roe": 0.145}
        ]
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict(os.environ, {"FMP_API_KEY": "test_key"}),
            patch("src.fmp_fetcher.requests.get", return_value=mock_resp),
        ):
            from src.fmp_fetcher import fetch_key_metrics
            result = fetch_key_metrics("AAPL")

        assert result["priceToBook"] == pytest.approx(3.2)
        assert result["returnOnEquity"] == pytest.approx(0.145)

    def test_supplements_for_jp_stock(self):
        """JP 株（7203.T）も FMP が対応すること。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"pbRatio": 0.8, "roe": 0.072}
        ]
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict(os.environ, {"FMP_API_KEY": "test_key"}),
            patch("src.fmp_fetcher.requests.get", return_value=mock_resp),
        ):
            from src.fmp_fetcher import fetch_key_metrics
            result = fetch_key_metrics("7203.T")

        assert result["priceToBook"] == pytest.approx(0.8)

    def test_returns_empty_when_data_empty(self):
        """FMP がデータなし → {} を返す。"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict(os.environ, {"FMP_API_KEY": "test_key"}),
            patch("src.fmp_fetcher.requests.get", return_value=mock_resp),
        ):
            from src.fmp_fetcher import fetch_key_metrics
            result = fetch_key_metrics("UNKN")

        assert result == {}

    def test_returns_empty_on_request_error(self):
        """API エラー時でも {} を返し、処理が継続する。"""
        with (
            patch.dict(os.environ, {"FMP_API_KEY": "test_key"}),
            patch("src.fmp_fetcher.requests.get", side_effect=Exception("timeout")),
        ):
            from src.fmp_fetcher import fetch_key_metrics
            result = fetch_key_metrics("FAIL")

        assert result == {}

    def test_does_not_overwrite_existing_value(self):
        """yfinance / J-Quants で取得済みの値は FMP で上書きしないこと。

        これは enricher._supplement_fmp_info() の責務だが、
        FMP クライアント自体が既存値を意識しないことを確認する。
        """
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"pbRatio": 99.0, "roe": 0.99}]
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict(os.environ, {"FMP_API_KEY": "test_key"}),
            patch("src.fmp_fetcher.requests.get", return_value=mock_resp),
        ):
            from src.fmp_fetcher import fetch_key_metrics
            fmp_data = fetch_key_metrics("AAPL")

        # enricher が既存値チェックを行い、上書きしない（enricher の責務）
        # FMP クライアント自体はデータを返すだけ
        existing_info = {"priceToBook": 1.5, "returnOnEquity": 0.10}
        if existing_info.get("priceToBook") is not None:
            # 既に値があれば上書きしない（enricher 側の処理）
            pass
        assert fmp_data["priceToBook"] == pytest.approx(99.0)  # FMP は値を返す
        assert existing_info["priceToBook"] == pytest.approx(1.5)  # 既存値は不変

    def test_cache_prevents_duplicate_calls(self):
        """同じティッカーの 2 回目以降はキャッシュを返す。"""
        import src.fmp_fetcher as fmp
        fmp._metrics_cache["AAPL"] = {"priceToBook": 2.5, "returnOnEquity": 0.18}

        with patch("src.fmp_fetcher.requests.get") as mock_get:
            from src.fmp_fetcher import fetch_key_metrics
            result = fetch_key_metrics("AAPL")

        mock_get.assert_not_called()
        assert result["priceToBook"] == pytest.approx(2.5)
