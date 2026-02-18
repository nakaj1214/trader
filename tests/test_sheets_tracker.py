"""sheets/tracker のテスト: 更新対象を前週に限定できること、評価日の終値で更新されること。"""

from datetime import datetime

import pytest


def _make_records():
    """テスト用のスプレッドシートレコードを生成する。"""
    return [
        # 2週前の予測 (未確定)
        {"日付": "2026-02-08", "ティッカー": "AAPL", "現在価格": 200,
         "予測価格": 210, "予測上昇率(%)": 5.0, "信頼区間(%)": 2.0,
         "翌週実績価格": "", "的中": "", "ステータス": "予測済み"},
        # 先週の予測 (未確定)
        {"日付": "2026-02-15", "ティッカー": "AAPL", "現在価格": 205,
         "予測価格": 215, "予測上昇率(%)": 4.9, "信頼区間(%)": 2.1,
         "翌週実績価格": "", "的中": "", "ステータス": "予測済み"},
        {"日付": "2026-02-15", "ティッカー": "MSFT", "現在価格": 400,
         "予測価格": 420, "予測上昇率(%)": 5.0, "信頼区間(%)": 1.5,
         "翌週実績価格": "", "的中": "", "ステータス": "予測済み"},
    ]


def test_get_pending_predictions_returns_oldest_date():
    """get_pending_predictions が最も古い未確定日のみ返すことを検証する。"""
    from unittest.mock import MagicMock, patch

    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = _make_records()

    with (
        patch("src.tracker.get_client"),
        patch("src.tracker.get_or_create_worksheet", return_value=mock_ws),
    ):
        from src.tracker import get_pending_predictions
        pending, target_date = get_pending_predictions(
            config={"google_sheets": {"spreadsheet_name": "test", "worksheet_name": "test"}}
        )

    # 最も古い日付 (2026-02-08) の行のみ返される
    assert target_date == "2026-02-08"
    assert len(pending) == 1
    assert pending[0]["ティッカー"] == "AAPL"


def test_update_actuals_only_updates_target_date():
    """update_actuals が target_date の行のみ更新することを検証する。"""
    from unittest.mock import MagicMock, patch

    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = _make_records()

    with (
        patch("src.sheets.get_client"),
        patch("src.sheets.get_or_create_worksheet", return_value=mock_ws),
    ):
        from src.sheets import update_actuals
        updated = update_actuals(
            actual_prices={"AAPL": 212.0, "MSFT": 415.0},
            target_date="2026-02-08",
            config={"google_sheets": {"spreadsheet_name": "test", "worksheet_name": "test"}},
        )

    # 2026-02-08 の AAPL のみ更新 (2026-02-15 の行は未更新)
    assert updated == 1
    # update_cell が3回呼ばれる (実績価格, 的中, ステータス)
    assert mock_ws.update_cell.call_count == 3
    # row_num=2 (ヘッダー+1行目) に対して更新
    mock_ws.update_cell.assert_any_call(2, 7, 212.0)  # 翌週実績価格
    mock_ws.update_cell.assert_any_call(2, 8, "的中")   # 上昇予測→実際に上昇
    mock_ws.update_cell.assert_any_call(2, 9, "確定済み")


def test_evaluation_date_default_5_business_days():
    """デフォルト forecast_days=5 で5営業日後が評価日になることを検証する。"""
    from src.tracker import _evaluation_date

    # 日曜 2026-02-08 → 5営業日後 = 月〜金 = 2026-02-13 (金曜)
    eval_dt = _evaluation_date("2026-02-08")
    assert eval_dt == datetime(2026, 2, 13)
    assert eval_dt.weekday() == 4  # 金曜

    # 月曜 2026-02-09 → 5営業日後 = 2026-02-16 (月曜)
    eval_dt = _evaluation_date("2026-02-09")
    assert eval_dt == datetime(2026, 2, 16)
    assert eval_dt.weekday() == 0  # 月曜


def test_evaluation_date_custom_forecast_days():
    """forecast_days を変更した場合に評価日が追従することを検証する。"""
    from src.tracker import _evaluation_date

    # 日曜 2026-02-08, forecast_days=3 → 3営業日後 = 2026-02-11 (水曜)
    eval_dt = _evaluation_date("2026-02-08", forecast_days=3)
    assert eval_dt == datetime(2026, 2, 11)
    assert eval_dt.weekday() == 2  # 水曜

    # 日曜 2026-02-08, forecast_days=10 → 10営業日後 = 2026-02-20 (金曜)
    eval_dt = _evaluation_date("2026-02-08", forecast_days=10)
    assert eval_dt == datetime(2026, 2, 20)
    assert eval_dt.weekday() == 4  # 金曜


def test_evaluation_date_skips_weekends():
    """営業日カウントが土日をスキップすることを検証する。"""
    from src.tracker import _evaluation_date

    # 金曜 2026-02-13, forecast_days=1 → 翌営業日 = 2026-02-16 (月曜)
    eval_dt = _evaluation_date("2026-02-13", forecast_days=1)
    assert eval_dt == datetime(2026, 2, 16)
    assert eval_dt.weekday() == 0  # 月曜


def test_fetch_close_at_counts_trading_days():
    """fetch_close_at が予測日から N 番目の実取引日の終値を返すことを検証する。"""
    from unittest.mock import patch

    import pandas as pd

    # 予測日: 2026-02-08 (日曜)
    # 実取引日: 02-09(1), 02-10(2), 02-11(3), 02-12(4), 02-13(5)
    dates = pd.to_datetime([
        "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
    ])
    mock_df = pd.DataFrame(
        {"Close": [195.0, 200.0, 205.0, 208.0, 210.0]},
        index=dates,
    )

    with patch("src.tracker.yf.download", return_value=mock_df):
        from src.tracker import fetch_close_at
        prices = fetch_close_at(["AAPL"], target_date="2026-02-08")

    # 5番目の実取引日 (02-13) の終値 210.0 が返される
    assert prices["AAPL"] == 210.0


def test_close_unfetched_marks_as_evaluatable():
    """価格未取得の銘柄が「評価不能」でクローズされることを検証する。"""
    from unittest.mock import MagicMock, patch

    records = [
        {"日付": "2026-02-08", "ティッカー": "AAPL", "現在価格": 200,
         "予測価格": 210, "予測上昇率(%)": 5.0, "信頼区間(%)": 2.0,
         "翌週実績価格": "", "的中": "", "ステータス": "予測済み"},
        {"日付": "2026-02-08", "ティッカー": "FAIL", "現在価格": 50,
         "予測価格": 55, "予測上昇率(%)": 10.0, "信頼区間(%)": 3.0,
         "翌週実績価格": "", "的中": "", "ステータス": "予測済み"},
    ]

    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = records

    with (
        patch("src.tracker.get_client"),
        patch("src.tracker.get_or_create_worksheet", return_value=mock_ws),
    ):
        from src.tracker import close_unfetched
        closed = close_unfetched(
            all_tickers=["AAPL", "FAIL"],
            fetched_prices={"AAPL": 212.0},  # FAIL は未取得
            target_date="2026-02-08",
            config={"google_sheets": {"spreadsheet_name": "t", "worksheet_name": "t"}},
        )

    assert closed == 1
    # FAIL の行 (row_num=3) が「評価不能」でクローズされる
    mock_ws.update_cell.assert_any_call(3, 7, "N/A")
    mock_ws.update_cell.assert_any_call(3, 8, "評価不能")
    mock_ws.update_cell.assert_any_call(3, 9, "確定済み")


def test_calculate_accuracy_excludes_unevaluable():
    """calculate_accuracy が「評価不能」行を分母から除外することを検証する。"""
    from unittest.mock import MagicMock, patch

    records = [
        {"日付": "2026-02-01", "ティッカー": "AAPL", "的中": "的中", "ステータス": "確定済み"},
        {"日付": "2026-02-01", "ティッカー": "MSFT", "的中": "外れ", "ステータス": "確定済み"},
        {"日付": "2026-02-01", "ティッカー": "FAIL", "的中": "評価不能", "ステータス": "確定済み"},
        {"日付": "2026-02-01", "ティッカー": "ERR", "的中": "評価不能", "ステータス": "確定済み"},
    ]

    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = records

    with (
        patch("src.tracker.get_client"),
        patch("src.tracker.get_or_create_worksheet", return_value=mock_ws),
    ):
        from src.tracker import calculate_accuracy
        result = calculate_accuracy(
            config={"google_sheets": {"spreadsheet_name": "t", "worksheet_name": "t"}}
        )

    # 評価不能2件は分母から除外 → 的中1 / (的中1 + 外れ1) = 50%
    assert result["total"] == 2
    assert result["hits"] == 1
    assert result["misses"] == 1
    assert result["hit_rate_pct"] == 50.0
    # 累計も同様
    assert result["cumulative_total"] == 2
    assert result["cumulative_hits"] == 1
    assert result["cumulative_hit_rate_pct"] == 50.0


def test_calculate_accuracy_latest_week_all_unevaluable():
    """最新週が全件「評価不能」でも、その週を「今週」として hits=0/total=0 で返すことを検証する。"""
    from unittest.mock import MagicMock, patch

    records = [
        # 先週: 的中・外れあり
        {"日付": "2026-02-08", "ティッカー": "AAPL", "的中": "的中", "ステータス": "確定済み"},
        {"日付": "2026-02-08", "ティッカー": "MSFT", "的中": "外れ", "ステータス": "確定済み"},
        # 今週: 全件「評価不能」
        {"日付": "2026-02-15", "ティッカー": "GOOG", "的中": "評価不能", "ステータス": "確定済み"},
        {"日付": "2026-02-15", "ティッカー": "AMZN", "的中": "評価不能", "ステータス": "確定済み"},
    ]

    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = records

    with (
        patch("src.tracker.get_client"),
        patch("src.tracker.get_or_create_worksheet", return_value=mock_ws),
    ):
        from src.tracker import calculate_accuracy
        result = calculate_accuracy(
            config={"google_sheets": {"spreadsheet_name": "t", "worksheet_name": "t"}}
        )

    # 「今週」は最新確定週 (2026-02-15) を参照 → 評価不能のみで total=0
    assert result["hits"] == 0
    assert result["misses"] == 0
    assert result["total"] == 0
    assert result["hit_rate_pct"] == 0.0
    # 累計は先週分のみ (評価不能除外)
    assert result["cumulative_hits"] == 1
    assert result["cumulative_total"] == 2
    assert result["cumulative_hit_rate_pct"] == 50.0


def test_fetch_close_at_handles_holiday():
    """祝日がある週でも実取引日ベースで正しく評価されることを検証する。"""
    from unittest.mock import patch

    import pandas as pd

    # 予測日: 2026-02-08 (日曜)
    # 2026-02-11 (水) が祝日で市場休場 → yfinance データに含まれない
    # 実取引日: 02-09(1), 02-10(2), 02-12(3), 02-13(4), 02-16(5)
    dates = pd.to_datetime([
        "2026-02-09", "2026-02-10", "2026-02-12", "2026-02-13", "2026-02-16",
    ])
    mock_df = pd.DataFrame(
        {"Close": [195.0, 200.0, 208.0, 210.0, 215.0]},
        index=dates,
    )

    with patch("src.tracker.yf.download", return_value=mock_df):
        from src.tracker import fetch_close_at
        prices = fetch_close_at(["AAPL"], target_date="2026-02-08")

    # 旧ロジック (_evaluation_date) では 02-11 を営業日扱い → 5番目 = 02-13 (210.0)
    # 新ロジックでは実取引日をカウント → 5番目 = 02-16 (215.0)
    assert prices["AAPL"] == 215.0


def test_fetch_close_at_insufficient_trading_days():
    """取引日数が forecast_days に満たない場合は価格を返さないことを検証する。"""
    from unittest.mock import patch

    import pandas as pd

    # 予測日: 2026-02-08, forecast_days=5 だが取引日が3日分しかない
    dates = pd.to_datetime(["2026-02-09", "2026-02-10", "2026-02-11"])
    mock_df = pd.DataFrame(
        {"Close": [195.0, 200.0, 205.0]},
        index=dates,
    )

    with patch("src.tracker.yf.download", return_value=mock_df):
        from src.tracker import fetch_close_at
        prices = fetch_close_at(["AAPL"], target_date="2026-02-08")

    # 5取引日に達していないため、価格は返されない (→ close_unfetched で評価不能に)
    assert "AAPL" not in prices
