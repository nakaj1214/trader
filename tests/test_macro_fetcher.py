"""macro_fetcher のテスト: FRED 系列取得・macro.json 構築・リスクオフ判定。"""

from unittest.mock import MagicMock, patch

import pytest


# --- fetch_fred_series ---


class TestFetchFredSeries:

    def _make_response(self, value: str, date: str = "2026-02-19"):
        """urllib.request.urlopen のモックレスポンスを生成する。"""
        import json
        body = json.dumps({
            "observations": [{"value": value, "date": date}]
        }).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    @patch("urllib.request.urlopen")
    def test_normal_value(self, mock_urlopen):
        from src.macro_fetcher import fetch_fred_series

        mock_urlopen.return_value = self._make_response("5.33")
        result = fetch_fred_series("FEDFUNDS", "dummy_key")

        assert result is not None
        assert result["latest_value"] == 5.33
        assert result["latest_date"] == "2026-02-19"

    @patch("urllib.request.urlopen")
    def test_missing_value_dot(self, mock_urlopen):
        """FRED が '.' を返す場合（欠損値）は None を返すこと。"""
        from src.macro_fetcher import fetch_fred_series

        mock_urlopen.return_value = self._make_response(".")
        result = fetch_fred_series("FEDFUNDS", "dummy_key")

        assert result is None

    @patch("urllib.request.urlopen")
    def test_empty_observations(self, mock_urlopen):
        """observations が空の場合は None を返すこと。"""
        import json
        from src.macro_fetcher import fetch_fred_series

        body = json.dumps({"observations": []}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = fetch_fred_series("FEDFUNDS", "dummy_key")
        assert result is None

    @patch("urllib.request.urlopen", side_effect=Exception("network error"))
    def test_exception_returns_none(self, mock_urlopen):
        """ネットワークエラー時は None を返すこと。"""
        from src.macro_fetcher import fetch_fred_series

        result = fetch_fred_series("FEDFUNDS", "dummy_key")
        assert result is None


# --- build_macro_json ---


class TestBuildMacroJson:

    def _patch_fetch(self, values: dict):
        """fetch_fred_series をパッチし、指定の値を返すようにする。"""
        def side_effect(series_id, api_key):
            if series_id in values:
                return {"latest_value": values[series_id], "latest_date": "2026-02-19"}
            return None
        return patch("src.macro_fetcher.fetch_fred_series", side_effect=side_effect)

    def test_returns_required_keys(self):
        from src.macro_fetcher import build_macro_json

        with self._patch_fetch({"FEDFUNDS": 5.33, "T10Y2Y": 0.1, "VIXCLS": 18.0}):
            result = build_macro_json("dummy_key")

        for key in ("as_of_utc", "data_as_of_utc", "series", "regime"):
            assert key in result

    def test_regime_risk_off_vix(self):
        """VIX > 25 のときリスクオフになること。"""
        from src.macro_fetcher import build_macro_json

        with self._patch_fetch({"FEDFUNDS": 5.33, "T10Y2Y": 0.1, "VIXCLS": 30.0}):
            result = build_macro_json("dummy_key")

        assert result["regime"]["is_risk_off"] is True

    def test_regime_risk_off_inverted_yield(self):
        """T10Y2Y < 0 のときリスクオフになること。"""
        from src.macro_fetcher import build_macro_json

        with self._patch_fetch({"FEDFUNDS": 5.33, "T10Y2Y": -0.5, "VIXCLS": 18.0}):
            result = build_macro_json("dummy_key")

        assert result["regime"]["is_risk_off"] is True

    def test_regime_risk_on(self):
        """VIX 低・スプレッド正のときリスクオンになること。"""
        from src.macro_fetcher import build_macro_json

        with self._patch_fetch({"FEDFUNDS": 5.33, "T10Y2Y": 0.2, "VIXCLS": 15.0}):
            result = build_macro_json("dummy_key")

        assert result["regime"]["is_risk_off"] is False

    def test_partial_fetch_failure(self):
        """一部の系列取得が失敗しても残りを返すこと。"""
        from src.macro_fetcher import build_macro_json

        with self._patch_fetch({"FEDFUNDS": 5.33}):  # T10Y2Y と VIXCLS は取得失敗
            result = build_macro_json("dummy_key")

        assert "FEDFUNDS" in result["series"]
        assert "T10Y2Y" not in result["series"]
        assert "VIXCLS" not in result["series"]

    def test_all_fetch_failure(self):
        """全系列取得失敗でも空の series を含む辞書を返すこと。"""
        from src.macro_fetcher import build_macro_json

        with self._patch_fetch({}):
            result = build_macro_json("dummy_key")

        assert result["series"] == {}
        assert "as_of_utc" in result
