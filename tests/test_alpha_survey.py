"""alpha_survey のテスト: アノマリー検証・JSON生成・エクスポート。"""

import json
from pathlib import Path


# --- run_anomaly_test ---


def test_run_anomaly_test_returns_required_keys():
    """run_anomaly_test が必要なキーを返すことを検証する。"""
    from src.alpha_survey import run_anomaly_test

    result = run_anomaly_test("short_interest_effect")

    assert "name" in result
    assert "n_observations" in result
    assert "t_stat" in result
    assert "p_value" in result
    assert "sharpe" in result
    assert "status" in result


def test_run_anomaly_test_insufficient_data():
    """データ不足時に insufficient_data が返ることを検証する。"""
    from src.alpha_survey import run_anomaly_test

    result = run_anomaly_test("short_interest_effect")
    assert result["status"] == "insufficient_data"
    assert result["n_observations"] < 52


# --- build_alpha_survey_json ---


def test_build_alpha_survey_json_schema():
    """build_alpha_survey_json が正しいスキーマを返すことを検証する。"""
    from src.alpha_survey import build_alpha_survey_json

    results = [
        {"name": "short_interest_effect", "n_observations": 10, "t_stat": None,
         "p_value": None, "sharpe": None, "status": "insufficient_data"},
    ]
    data = build_alpha_survey_json(results)

    assert "as_of_utc" in data
    assert "anomalies" in data
    assert len(data["anomalies"]) == 1


def test_build_alpha_survey_json_score_included():
    """各エントリに score_included が含まれることを検証する。"""
    from src.alpha_survey import build_alpha_survey_json

    results = [
        {"name": "short_interest_effect", "n_observations": 0,
         "t_stat": None, "p_value": None, "sharpe": None},
    ]
    data = build_alpha_survey_json(results)

    entry = data["anomalies"][0]
    assert "score_included" in entry
    assert entry["score_included"] is False


def test_build_alpha_survey_json_insufficient_when_n_lt_52():
    """n_observations < 52 のエントリは insufficient_data になることを検証する。"""
    from src.alpha_survey import build_alpha_survey_json

    results = [
        {"name": "short_interest_effect", "n_observations": 30,
         "t_stat": -2.1, "p_value": 0.03, "sharpe": -0.3, "status": "significant"},
    ]
    data = build_alpha_survey_json(results)

    entry = data["anomalies"][0]
    assert entry["status"] == "insufficient_data"


def test_build_alpha_survey_json_sufficient_data():
    """n_observations >= 52 のエントリはオリジナルの status が使われることを検証する。"""
    from src.alpha_survey import build_alpha_survey_json

    results = [
        {"name": "short_interest_effect", "n_observations": 100,
         "t_stat": -2.34, "p_value": 0.021, "sharpe": -0.42, "status": "significant"},
    ]
    data = build_alpha_survey_json(results)

    entry = data["anomalies"][0]
    assert entry["status"] == "significant"
    assert entry["n_observations"] == 100


# --- run_and_export ---


def test_run_and_export_creates_file(tmp_path):
    """run_and_export が alpha_survey.json を出力することを検証する。"""
    import src.alpha_survey as alpha_module

    original_path = alpha_module.ALPHA_SURVEY_PATH
    original_dir = alpha_module.DATA_DIR

    alpha_module.DATA_DIR = tmp_path
    alpha_module.ALPHA_SURVEY_PATH = tmp_path / "alpha_survey.json"

    try:
        result = alpha_module.run_and_export()
    finally:
        alpha_module.DATA_DIR = original_dir
        alpha_module.ALPHA_SURVEY_PATH = original_path

    assert result is True
    output = tmp_path / "alpha_survey.json"
    assert output.exists()

    data = json.loads(output.read_text(encoding="utf-8"))
    assert "anomalies" in data
    assert len(data["anomalies"]) > 0
    for entry in data["anomalies"]:
        assert "score_included" in entry
