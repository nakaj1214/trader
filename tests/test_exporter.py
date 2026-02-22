"""exporter のテスト: JSON生成、スキーマ検証、空データフォールバック。"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# --- テスト用フィクスチャ ---

SAMPLE_RECORDS = [
    {
        "日付": "2026-02-15",
        "ティッカー": "AAPL",
        "現在価格": "250.00",
        "予測価格": "265.00",
        "予測上昇率(%)": "6.0",
        "信頼区間(%)": "3.2",
        "翌週実績価格": "263.50",
        "的中": "的中",
        "ステータス": "確定済み",
    },
    {
        "日付": "2026-02-15",
        "ティッカー": "MSFT",
        "現在価格": "420.00",
        "予測価格": "438.00",
        "予測上昇率(%)": "4.3",
        "信頼区間(%)": "2.8",
        "翌週実績価格": "415.00",
        "的中": "外れ",
        "ステータス": "確定済み",
    },
    {
        "日付": "2026-02-22",
        "ティッカー": "GOOGL",
        "現在価格": "175.00",
        "予測価格": "182.00",
        "予測上昇率(%)": "4.0",
        "信頼区間(%)": "2.5",
        "翌週実績価格": "",
        "的中": "",
        "ステータス": "予測済み",
    },
]


# --- build_predictions_json ---


def test_build_predictions_json_schema():
    """predictions.json の各エントリが必要な基本キーを持つことを検証する（最新週エントリで確認）。"""
    from src.exporter import build_predictions_json

    result = build_predictions_json(SAMPLE_RECORDS)

    assert len(result) == 3
    required_keys = {
        "date",
        "ticker",
        "current_price",
        "predicted_price",
        "predicted_change_pct",
        "ci_pct",
        "actual_price",
        "status",
        "hit",
        "prob_up",
        "prob_up_calibrated",
    }
    for entry in result:
        assert required_keys.issubset(set(entry.keys()))


def test_build_predictions_json_new_keys_from_enrichment():
    """Phase11/12/13の新規キーが enrichment 経由で最新週エントリに付与されることを検証する。"""
    from src.exporter import build_predictions_json

    records = [SAMPLE_RECORDS[2]]  # 最新週 GOOGL
    enrichment = {
        ("2026-02-22", "GOOGL"): {
            "short_interest": {
                "short_ratio": 2.1,
                "short_pct_float": 0.03,
                "signal": "neutral",
                "data_note": "月次更新・参考値（yfinance）",
            },
            "institutional": {
                "institutional_pct": 0.72,
                "top5_holders": ["Vanguard", "BlackRock"],
                "data_note": "四半期報告（45〜75日遅延）・参考値",
            },
            "fifty2w_score": 0.85,
            "fifty2w_pct_from_high": -0.15,
        }
    }

    result = build_predictions_json(records, enrichment)
    entry = result[0]

    assert "short_interest" in entry
    assert entry["short_interest"]["signal"] == "neutral"
    assert "institutional" in entry
    assert "Vanguard" in entry["institutional"]["top5_holders"]
    assert "fifty2w_score" in entry
    assert entry["fifty2w_score"] == 0.85
    assert "fifty2w_pct_from_high" in entry
    assert entry["fifty2w_pct_from_high"] == -0.15


def test_build_predictions_json_fifty2w_zero_not_dropped():
    """fifty2w_score=0.0 の場合にキーが欠落しないことを検証する（in 判定）。"""
    from src.exporter import build_predictions_json

    records = [SAMPLE_RECORDS[2]]
    enrichment = {
        ("2026-02-22", "GOOGL"): {
            "fifty2w_score": 0.0,
            "fifty2w_pct_from_high": -1.0,
        }
    }

    result = build_predictions_json(records, enrichment)
    entry = result[0]

    assert "fifty2w_score" in entry
    assert entry["fifty2w_score"] == 0.0
    assert "fifty2w_pct_from_high" in entry


def test_build_predictions_json_types():
    """predictions.json の値の型が正しいことを検証する。"""
    from src.exporter import build_predictions_json

    result = build_predictions_json(SAMPLE_RECORDS)

    # 確定済みのエントリ
    aapl = result[0]
    assert isinstance(aapl["current_price"], float)
    assert isinstance(aapl["predicted_price"], float)
    assert isinstance(aapl["actual_price"], float)
    assert aapl["hit"] == "的中"

    # 未確定のエントリ
    googl = result[2]
    assert googl["actual_price"] is None
    assert googl["hit"] is None


def test_build_predictions_json_empty():
    """空レコードで空リストが返ることを検証する。"""
    from src.exporter import build_predictions_json

    result = build_predictions_json([])
    assert result == []


# --- build_accuracy_json ---


def test_build_accuracy_json_weekly_aggregation():
    """週単位で的中率が正しく集計されることを検証する。"""
    from src.exporter import build_accuracy_json

    result = build_accuracy_json(SAMPLE_RECORDS)

    # 確定済みは 2026-02-15 の 2件のみ
    assert len(result["weekly"]) == 1
    week = result["weekly"][0]
    assert week["date"] == "2026-02-15"
    assert week["hits"] == 1
    assert week["total"] == 2
    assert week["hit_rate_pct"] == 50.0


def test_build_accuracy_json_cumulative():
    """累計的中率が正しく計算されることを検証する。"""
    from src.exporter import build_accuracy_json

    result = build_accuracy_json(SAMPLE_RECORDS)

    assert result["cumulative"]["hits"] == 1
    assert result["cumulative"]["total"] == 2
    assert result["cumulative"]["hit_rate_pct"] == 50.0


def test_build_accuracy_json_has_updated_at():
    """updated_at フィールドが存在することを検証する。"""
    from src.exporter import build_accuracy_json

    result = build_accuracy_json(SAMPLE_RECORDS)
    assert "updated_at" in result
    assert isinstance(result["updated_at"], str)


def test_build_accuracy_json_empty_records():
    """空レコードで安全なデフォルト値が返ることを検証する。"""
    from src.exporter import build_accuracy_json

    result = build_accuracy_json([])

    assert result["weekly"] == []
    assert result["cumulative"]["hits"] == 0
    assert result["cumulative"]["total"] == 0
    assert result["cumulative"]["hit_rate_pct"] == 0.0


# --- build_stock_history_json ---


def test_build_stock_history_json_groups_by_ticker():
    """銘柄別にグループ化されることを検証する。"""
    from src.exporter import build_stock_history_json

    result = build_stock_history_json(SAMPLE_RECORDS)

    assert "AAPL" in result
    assert "MSFT" in result
    assert "GOOGL" in result
    assert len(result["AAPL"]) == 1
    assert len(result["MSFT"]) == 1


def test_build_stock_history_json_actual_price():
    """確定済みエントリに actual_price が含まれることを検証する。"""
    from src.exporter import build_stock_history_json

    result = build_stock_history_json(SAMPLE_RECORDS)

    assert "actual_price" in result["AAPL"][0]
    assert result["AAPL"][0]["actual_price"] == 263.5


def test_build_stock_history_json_no_actual_price():
    """未確定エントリに actual_price が含まれないことを検証する。"""
    from src.exporter import build_stock_history_json

    result = build_stock_history_json(SAMPLE_RECORDS)

    assert "actual_price" not in result["GOOGL"][0]


def test_build_stock_history_json_sorted_by_date():
    """各銘柄の履歴が日付順にソートされることを検証する。"""
    from src.exporter import build_stock_history_json

    records = [
        {
            "日付": "2026-02-22",
            "ティッカー": "AAPL",
            "予測価格": "270.00",
            "翌週実績価格": "",
        },
        {
            "日付": "2026-02-15",
            "ティッカー": "AAPL",
            "予測価格": "265.00",
            "翌週実績価格": "263.50",
        },
    ]
    result = build_stock_history_json(records)

    dates = [e["date"] for e in result["AAPL"]]
    assert dates == ["2026-02-15", "2026-02-22"]


# --- _safe_write_json ---


def test_safe_write_json_skips_empty_data(tmp_path):
    """空データの場合にファイルを書き出さないことを検証する。"""
    from src.exporter import _safe_write_json

    filepath = tmp_path / "test.json"
    result = _safe_write_json([], filepath)

    assert result is False
    assert not filepath.exists()


def test_safe_write_json_preserves_existing_on_empty(tmp_path):
    """空データの場合に既存ファイルが保持されることを検証する。"""
    from src.exporter import _safe_write_json

    filepath = tmp_path / "test.json"
    filepath.write_text('{"old": "data"}', encoding="utf-8")

    result = _safe_write_json([], filepath)

    assert result is False
    assert json.loads(filepath.read_text(encoding="utf-8")) == {"old": "data"}


def test_safe_write_json_writes_non_empty(tmp_path):
    """非空データが正しくJSONファイルに書き出されることを検証する。"""
    from src.exporter import _safe_write_json

    filepath = tmp_path / "subdir" / "test.json"
    data = [{"key": "value"}]

    result = _safe_write_json(data, filepath)

    assert result is True
    assert filepath.exists()
    loaded = json.loads(filepath.read_text(encoding="utf-8"))
    assert loaded == data


def test_safe_write_json_no_tmp_file_on_success(tmp_path):
    """書き出し成功後に .tmp ファイルが残らないことを検証する。"""
    from src.exporter import _safe_write_json

    filepath = tmp_path / "test.json"
    _safe_write_json([1, 2, 3], filepath)

    assert not filepath.with_suffix(".tmp").exists()


# --- export (統合テスト) ---


@patch("src.exporter.get_client")
@patch("src.exporter.get_or_create_worksheet")
def test_export_integration(mock_get_ws, mock_get_client, tmp_path):
    """export() が Google Sheets から取得してJSONファイルを生成することを検証する。"""
    import src.exporter as exporter

    # DATA_DIR を tmp_path に差し替え
    original_data_dir = exporter.DATA_DIR
    exporter.DATA_DIR = tmp_path

    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = SAMPLE_RECORDS
    mock_get_ws.return_value = mock_ws

    config = {
        "google_sheets": {
            "spreadsheet_name": "Test",
            "worksheet_name": "predictions",
        },
    }

    try:
        result = exporter.export(config)
    finally:
        exporter.DATA_DIR = original_data_dir

    assert result is True
    assert (tmp_path / "predictions.json").exists()
    assert (tmp_path / "accuracy.json").exists()
    assert (tmp_path / "stock_history.json").exists()

    # predictions.json の内容検証
    raw = json.loads((tmp_path / "predictions.json").read_text(encoding="utf-8"))
    predictions = raw["predictions"]
    assert len(predictions) == 3
    assert predictions[0]["ticker"] == "AAPL"


@patch("src.exporter.get_client")
@patch("src.exporter.get_or_create_worksheet")
def test_export_empty_sheets(mock_get_ws, mock_get_client):
    """シートが空の場合に False を返すことを検証する。"""
    from src.exporter import export

    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = []
    mock_get_ws.return_value = mock_ws

    config = {
        "google_sheets": {
            "spreadsheet_name": "Test",
            "worksheet_name": "predictions",
        },
    }

    result = export(config)
    assert result is False
