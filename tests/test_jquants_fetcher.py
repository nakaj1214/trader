"""J-Quants API クライアントのテスト（モック使用）"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestFetchFinancialData:
    def setup_method(self):
        """各テスト前にキャッシュをリセットする。"""
        import src.jquants_fetcher as jq
        jq._id_token_cache = None
        jq._financial_cache = {}
        jq._earnings_cache = {}

    def test_returns_empty_when_no_credentials(self):
        """JQUANTS_MAIL_ADDRESS 未設定 → {} を返す。"""
        with patch.dict(os.environ, {}, clear=True):
            # 環境変数から削除
            env = {k: v for k, v in os.environ.items()
                   if k not in ("JQUANTS_MAIL_ADDRESS", "JQUANTS_PASSWORD")}
            with patch.dict(os.environ, env, clear=True):
                from src.jquants_fetcher import fetch_financial_data
                result = fetch_financial_data("7203.T")
        assert result == {}

    def test_supplements_pbr_from_jquants(self):
        """J-Quants から PBR を補完できること。"""
        import src.jquants_fetcher as jq

        # 認証トークン取得をモック
        jq._id_token_cache = "dummy_token"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "statements": [
                {"PBR": "1.5", "ROEAfterTax": "12.3"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_financial_data
            result = fetch_financial_data("7203.T")

        assert result["priceToBook"] == pytest.approx(1.5)
        assert result["returnOnEquity"] == pytest.approx(0.123)

    def test_returns_empty_when_statements_empty(self):
        """J-Quants がデータなし → {} を返す。"""
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"statements": []}
        mock_resp.raise_for_status = MagicMock()

        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_financial_data
            result = fetch_financial_data("9999.T")

        assert result == {}

    def test_returns_empty_on_request_error(self):
        """API エラー時でも {} を返し、処理が継続する。"""
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"

        with patch("src.jquants_fetcher.requests.get", side_effect=Exception("timeout")):
            from src.jquants_fetcher import fetch_financial_data
            result = fetch_financial_data("1234.T")

        assert result == {}

    def test_cache_prevents_duplicate_calls(self):
        """同じティッカーの 2 回目以降はキャッシュを返す。"""
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"
        jq._financial_cache["7203.T"] = {"priceToBook": 2.0}

        with patch("src.jquants_fetcher.requests.get") as mock_get:
            from src.jquants_fetcher import fetch_financial_data
            result = fetch_financial_data("7203.T")

        # requests.get が呼ばれていないこと（キャッシュヒット）
        mock_get.assert_not_called()
        assert result["priceToBook"] == 2.0


# ---------------------------------------------------------------------------
# Phase 22: V2 APIキー認証テスト
# ---------------------------------------------------------------------------

class TestGetAuthHeader:
    def setup_method(self):
        import src.jquants_fetcher as jq
        jq._id_token_cache = None
        jq._financial_cache = {}
        jq._earnings_cache = {}

    def test_v2_api_key_takes_priority(self):
        """JQUANTS_API_KEY が設定されている場合は V2 Bearer ヘッダーを返す。"""
        with patch.dict(os.environ, {"JQUANTS_API_KEY": "test_v2_key"}):
            from src.jquants_fetcher import _get_auth_header
            result = _get_auth_header()
        assert result == {"Authorization": "Bearer test_v2_key"}

    def test_v1_fallback_when_no_api_key(self):
        """JQUANTS_API_KEY 未設定かつ V1 トークンがある場合は V1 ヘッダーを返す。"""
        import src.jquants_fetcher as jq
        jq._id_token_cache = "v1_id_token"
        env = {k: v for k, v in os.environ.items() if k != "JQUANTS_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            from src.jquants_fetcher import _get_auth_header
            result = _get_auth_header()
        assert result == {"Authorization": "Bearer v1_id_token"}

    def test_returns_none_when_no_credentials(self):
        """どちらも未設定 → None を返す（degraded mode）。"""
        env = {k: v for k, v in os.environ.items()
               if k not in ("JQUANTS_API_KEY", "JQUANTS_MAIL_ADDRESS", "JQUANTS_PASSWORD")}
        with patch.dict(os.environ, env, clear=True):
            from src.jquants_fetcher import _get_auth_header
            result = _get_auth_header()
        assert result is None

    def test_fetch_financial_data_uses_v2_endpoint(self):
        """JQUANTS_API_KEY 設定時、V2 エンドポイントを呼び出すこと。"""
        import src.jquants_fetcher as jq
        jq._financial_cache = {}

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"statements": [{"PBR": "1.2", "ROEAfterTax": "8.5"}]}
        mock_resp.raise_for_status = MagicMock()

        with (
            patch.dict(os.environ, {"JQUANTS_API_KEY": "test_v2_key"}),
            patch("src.jquants_fetcher.requests.get", return_value=mock_resp) as mock_get,
        ):
            from src.jquants_fetcher import fetch_financial_data
            result = fetch_financial_data("7203.T")

        # V2 URL が使われていること
        call_url = mock_get.call_args[0][0]
        assert "v2" in call_url
        assert result["priceToBook"] == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# Phase 24: fetch_earnings_calendar テスト
# ---------------------------------------------------------------------------

class TestFetchEarningsCalendar:
    def setup_method(self):
        import src.jquants_fetcher as jq
        jq._id_token_cache = None
        jq._earnings_cache = {}

    def test_returns_none_when_no_credentials(self):
        """認証情報未設定 → None を返す。"""
        env = {k: v for k, v in os.environ.items()
               if k not in ("JQUANTS_API_KEY", "JQUANTS_MAIL_ADDRESS", "JQUANTS_PASSWORD")}
        with patch.dict(os.environ, env, clear=True):
            from src.jquants_fetcher import fetch_earnings_calendar
            result = fetch_earnings_calendar("7203.T")
        assert result is None

    def test_returns_earnings_date_with_days(self):
        """次回決算日と残日数を正しく返すこと。"""
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"

        from datetime import date, timedelta
        future_date = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"announcement": [{"Date": future_date}]}
        mock_resp.raise_for_status = MagicMock()

        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_earnings_calendar
            result = fetch_earnings_calendar("7203.T")

        assert result is not None
        assert result["announcement_date"] == future_date
        assert result["days_to_earnings"] == 10

    def test_returns_none_when_no_future_earnings(self):
        """過去の決算しかない場合 → None を返す。"""
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"announcement": [{"Date": "2020-01-01"}]}
        mock_resp.raise_for_status = MagicMock()

        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_earnings_calendar
            result = fetch_earnings_calendar("7203.T")

        assert result is None

    def test_returns_none_on_api_error(self):
        """API エラー時でも None を返し、処理が継続する。"""
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"

        with patch("src.jquants_fetcher.requests.get", side_effect=Exception("timeout")):
            from src.jquants_fetcher import fetch_earnings_calendar
            result = fetch_earnings_calendar("1234.T")

        assert result is None

    def test_cache_prevents_duplicate_calls(self):
        """同じティッカーの 2 回目以降はキャッシュを返す。"""
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"
        jq._earnings_cache["7203.T"] = {"announcement_date": "2026-05-10", "days_to_earnings": 78}

        with patch("src.jquants_fetcher.requests.get") as mock_get:
            from src.jquants_fetcher import fetch_earnings_calendar
            result = fetch_earnings_calendar("7203.T")

        mock_get.assert_not_called()
        assert result["days_to_earnings"] == 78
