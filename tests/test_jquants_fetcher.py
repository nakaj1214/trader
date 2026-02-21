"""J-Quants API クライアントのテスト（モック使用 + sample_data_v2 フィクスチャ）

sample_data_v2/ の実際のサンプル CSV を読み込んで API レスポンスを構築することで、
JQUANTS_API_KEY なしに実際のデータ形式でテストを行う。
"""

import csv
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# sample_data_v2 フィクスチャヘルパー
# ---------------------------------------------------------------------------

SAMPLE_DIR = Path(__file__).parent.parent / "data" / "sample_data" / "sample_data_v2"


def _load_csv_rows(filename: str) -> list[dict]:
    """sample_data_v2 の CSV を読み込んでヘッダー付き辞書リストで返す。"""
    path = SAMPLE_DIR / filename
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))


def _make_financial_mock(rows: list[dict]) -> MagicMock:
    """Financial Data.csv の行リストから fins/statements API レスポンスモックを作る。"""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"statements": rows}
    return mock


def _make_listed_mock(rows: list[dict]) -> MagicMock:
    """Listed Issue Master.csv の行リストから listed/info API レスポンスモックを作る。"""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"info": rows}
    return mock


def _make_price_mock(rows: list[dict]) -> MagicMock:
    """Stock Prices (OHLC).csv の行リストから daily_quotes API レスポンスモックを作る。

    CSV 列名（O, H, L, C, Vo, AdjC 等）→ API JSON 列名（Open, High, Low, Close, Volume, AdjustmentClose 等）に変換する。
    """
    col_map = {
        "O": "Open", "H": "High", "L": "Low", "C": "Close",
        "Vo": "Volume", "Va": "TurnoverValue",
        "AdjFactor": "AdjustmentFactor",
        "AdjO": "AdjustmentOpen", "AdjH": "AdjustmentHigh",
        "AdjL": "AdjustmentLow", "AdjC": "AdjustmentClose",
        "AdjVo": "AdjustmentVolume",
    }
    converted = []
    for row in rows:
        new_row = {"Date": row.get("Date", ""), "Code": row.get("Code", "")}
        for csv_key, api_key in col_map.items():
            if csv_key in row:
                new_row[api_key] = row[csv_key]
        converted.append(new_row)

    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {"daily_quotes": converted}
    return mock


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


# ---------------------------------------------------------------------------
# sample_data_v2 を使った統合フィクスチャテスト
# ---------------------------------------------------------------------------


class TestSampleDataFinancial:
    """Financial Data.csv の実データを使って fetch_financial_data() の追加フィールドをテスト。"""

    def setup_method(self):
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"
        jq._financial_cache = {}
        jq._earnings_cache = {}

    def test_extended_fields_from_sample_data(self):
        """sample_data_v2 の Financial Data.csv から追加指標（EPS/配当/営業利益率）が取得できること。"""
        rows = _load_csv_rows("Financial Data.csv")
        if not rows:
            pytest.skip("sample_data_v2 が存在しないためスキップ")

        mock_resp = _make_financial_mock(rows)
        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_financial_data
            result = fetch_financial_data("8697.T")  # コード 86970 のサンプル

        # 追加フィールドの存在確認（値がゼロでも取得されていること）
        assert isinstance(result, dict)
        # EPS が取得できているか（サンプルデータに EPS が含まれる場合）
        last_row = rows[-1]
        if last_row.get("EPS"):
            assert "eps" in result
            assert result["eps"] == pytest.approx(float(last_row["EPS"]))

        # 営業利益率（OP/Sales）が正しく計算されるか
        if last_row.get("OP") and last_row.get("Sales"):
            op = float(last_row["OP"])
            sales = float(last_row["Sales"])
            if sales > 0:
                expected_margin = op / sales
                assert "operating_margin" in result
                assert result["operating_margin"] == pytest.approx(expected_margin, rel=1e-3)

    def test_payout_ratio_converted_to_decimal(self):
        """PayoutRatioAnn が % → 小数に変換されること。"""
        mock_resp = _make_financial_mock([{
            "PBR": "1.2", "ROEAfterTax": "10.0",
            "EPS": "50.0", "FEPS": "60.0",
            "DivAnn": "30.0", "PayoutRatioAnn": "40.0",
            "OP": "1000000", "Sales": "5000000",
            "CFO": "800000",
        }])
        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_financial_data
            result = fetch_financial_data("1234.T")

        assert result["payout_ratio"] == pytest.approx(0.40)   # 40% → 0.40
        assert result["returnOnEquity"] == pytest.approx(0.10)  # 10% → 0.10
        assert result["eps"] == pytest.approx(50.0)
        assert result["forecast_eps"] == pytest.approx(60.0)
        assert result["dividend_annual"] == pytest.approx(30.0)
        assert result["operating_margin"] == pytest.approx(0.20)  # 1000000/5000000
        assert result["cfo"] == pytest.approx(800000.0)

    def test_operating_margin_skipped_when_sales_zero(self):
        """Sales が 0 の場合に operating_margin を含まないこと。"""
        mock_resp = _make_financial_mock([{
            "PBR": "1.0", "ROEAfterTax": "5.0",
            "OP": "100000", "Sales": "0",
        }])
        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_financial_data
            result = fetch_financial_data("5555.T")

        assert "operating_margin" not in result


class TestSampleDataListedInfo:
    """Listed Issue Master.csv の実データを使って fetch_listed_info() をテスト。"""

    def setup_method(self):
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"
        jq._listed_info_cache = {}

    def test_listed_info_returns_sector_and_market(self):
        """セクター分類・市場区分が正しく取得できること。"""
        rows = _load_csv_rows("Listed Issue Master.csv")
        if not rows:
            pytest.skip("sample_data_v2 が存在しないためスキップ")

        mock_resp = _make_listed_mock(rows[:1])
        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_listed_info
            result = fetch_listed_info("8697.T")

        assert isinstance(result, dict)
        # 取得できるフィールドの存在確認
        first_row = rows[0]
        if first_row.get("S17Nm"):
            assert "sector_17" in result
        if first_row.get("S33Nm"):
            assert "sector_33" in result
        if first_row.get("MktNm"):
            assert "market_section" in result

    def test_listed_info_returns_empty_on_no_credentials(self):
        """認証情報なし → {} を返す。"""
        env = {k: v for k, v in os.environ.items()
               if k not in ("JQUANTS_API_KEY", "JQUANTS_MAIL_ADDRESS", "JQUANTS_PASSWORD")}
        with patch.dict(os.environ, env, clear=True):
            from src.jquants_fetcher import fetch_listed_info
            result = fetch_listed_info("7203.T")
        assert result == {}

    def test_listed_info_mock_fields(self):
        """mock レスポンスから各フィールドが正しくマップされること。"""
        import src.jquants_fetcher as jq
        jq._listed_info_cache = {}

        mock_resp = _make_listed_mock([{
            "Code": "86970", "CoName": "日本取引所グループ",
            "S17Nm": "金融（除く銀行）", "S33Nm": "その他金融業",
            "ScaleCat": "TOPIX Large70", "MktNm": "プライム",
        }])
        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_listed_info
            result = fetch_listed_info("8697.T")

        assert result["company_name"] == "日本取引所グループ"
        assert result["sector_17"] == "金融（除く銀行）"
        assert result["sector_33"] == "その他金融業"
        assert result["scale_category"] == "TOPIX Large70"
        assert result["market_section"] == "プライム"

    def test_listed_info_cache(self):
        """2 回目以降はキャッシュを返すこと。"""
        import src.jquants_fetcher as jq
        jq._listed_info_cache["7203.T"] = {"sector_17": "輸送用機器"}

        with patch("src.jquants_fetcher.requests.get") as mock_get:
            from src.jquants_fetcher import fetch_listed_info
            result = fetch_listed_info("7203.T")

        mock_get.assert_not_called()
        assert result["sector_17"] == "輸送用機器"


class TestSampleDataPriceSeries:
    """Stock Prices (OHLC).csv の実データを使って fetch_price_series() をテスト。"""

    def setup_method(self):
        import src.jquants_fetcher as jq
        jq._id_token_cache = "dummy_token"
        jq._price_series_cache = {}

    def test_price_series_returns_dataframe_from_sample(self):
        """sample_data_v2 の株価データが DataFrame として返ること。"""
        rows = _load_csv_rows("Stock Prices (OHLC).csv")
        if not rows:
            pytest.skip("sample_data_v2 が存在しないためスキップ")

        mock_resp = _make_price_mock(rows)
        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_price_series
            df = fetch_price_series("8697.T", "20220104", "20220110")

        assert not df.empty
        assert "AdjustmentClose" in df.columns
        assert "Close" in df.columns
        # インデックスが DatetimeIndex であること
        import pandas as pd
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_price_series_adjclose_is_numeric(self):
        """AdjustmentClose が数値型で返ること。"""
        mock_resp = _make_price_mock([{
            "Date": "2022-01-04", "Code": "86970",
            "O": "2533.0", "H": "2544.5", "L": "2502.0", "C": "2518.5",
            "Vo": "612200.0",
            "AdjFactor": "1.0", "AdjC": "2518.5", "AdjVo": "612200.0",
        }])
        with patch("src.jquants_fetcher.requests.get", return_value=mock_resp):
            from src.jquants_fetcher import fetch_price_series
            df = fetch_price_series("8697.T", "20220104", "20220104")

        assert df["AdjustmentClose"].iloc[0] == pytest.approx(2518.5)
        assert df["Close"].iloc[0] == pytest.approx(2518.5)

    def test_price_series_returns_empty_on_no_credentials(self):
        """認証情報なし → 空 DataFrame を返す。"""
        env = {k: v for k, v in os.environ.items()
               if k not in ("JQUANTS_API_KEY", "JQUANTS_MAIL_ADDRESS", "JQUANTS_PASSWORD")}
        with patch.dict(os.environ, env, clear=True):
            import src.jquants_fetcher as jq
            jq._price_series_cache = {}
            from src.jquants_fetcher import fetch_price_series
            df = fetch_price_series("7203.T", "20240101", "20240131")

        assert df.empty

    def test_price_series_cache(self):
        """同じ条件の 2 回目はキャッシュを返すこと。"""
        import pandas as pd
        import src.jquants_fetcher as jq

        dummy_df = pd.DataFrame([{"Date": "2022-01-04", "AdjustmentClose": 2518.5}])
        jq._price_series_cache["8697.T:20220104:20220104"] = dummy_df

        with patch("src.jquants_fetcher.requests.get") as mock_get:
            from src.jquants_fetcher import fetch_price_series
            result = fetch_price_series("8697.T", "20220104", "20220104")

        mock_get.assert_not_called()
        assert len(result) == 1
