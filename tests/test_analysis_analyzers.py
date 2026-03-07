"""Tests for individual financial analyzer implementations.

Each analyzer is validated for:
- Correct name property
- Required data fields are specified
- System and user prompts are non-empty
- User prompt includes the financials_summary placeholder
"""

from __future__ import annotations

import pytest

from src.analysis.base import Analyzer
from src.core.models import AnalysisInput


def _make_input() -> AnalysisInput:
    return AnalysisInput(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3_000_000_000_000,
        financials={
            "revenue": 383_285_000_000,
            "ebitda": 130_541_000_000,
            "netIncome": 96_995_000_000,
            "free_cash_flow": 111_443_000_000,
            "totalDebt": 111_088_000_000,
            "totalCash": 29_965_000_000,
        },
    )


ANALYZER_CONFIGS = [
    ("src.analysis.dcf_analyzer", "DCFAnalyzer", "dcf"),
    ("src.analysis.comps_analyzer", "CompsAnalyzer", "comps"),
    ("src.analysis.financial_statement_analyzer", "FinancialStatementAnalyzer", "financial_statement"),
    ("src.analysis.sensitivity_analyzer", "SensitivityAnalyzer", "sensitivity"),
    ("src.analysis.ma_analyzer", "MAAnalyzer", "ma"),
    ("src.analysis.lbo_analyzer", "LBOAnalyzer", "lbo"),
    ("src.analysis.precedent_analyzer", "PrecedentAnalyzer", "precedent"),
    ("src.analysis.ipo_analyzer", "IPOAnalyzer", "ipo"),
    ("src.analysis.credit_analyzer", "CreditAnalyzer", "credit"),
    ("src.analysis.sotp_analyzer", "SOTPAnalyzer", "sotp"),
    ("src.analysis.operating_model_analyzer", "OperatingModelAnalyzer", "operating_model"),
    ("src.analysis.ic_memo_analyzer", "ICMemoAnalyzer", "ic_memo"),
]


def _import_analyzer(module_path: str, class_name: str) -> Analyzer:
    """Dynamically import and instantiate an analyzer."""
    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()


@pytest.mark.parametrize(
    "module_path,class_name,expected_name",
    ANALYZER_CONFIGS,
    ids=[c[2] for c in ANALYZER_CONFIGS],
)
class TestAnalyzerContract:
    """Verify each analyzer meets the Analyzer contract."""

    def test_name_property(self, module_path, class_name, expected_name):
        analyzer = _import_analyzer(module_path, class_name)
        assert analyzer.name == expected_name

    def test_is_analyzer_subclass(self, module_path, class_name, expected_name):
        analyzer = _import_analyzer(module_path, class_name)
        assert isinstance(analyzer, Analyzer)

    def test_required_data_fields_not_empty(self, module_path, class_name, expected_name):
        analyzer = _import_analyzer(module_path, class_name)
        assert len(analyzer.required_data_fields) > 0

    def test_system_prompt_not_empty(self, module_path, class_name, expected_name):
        analyzer = _import_analyzer(module_path, class_name)
        prompt = analyzer._system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 10

    def test_user_prompt_contains_data(self, module_path, class_name, expected_name):
        analyzer = _import_analyzer(module_path, class_name)
        data = _make_input()
        prompt = analyzer._user_prompt(data)
        assert isinstance(prompt, str)
        assert "Apple Inc." in prompt
        assert "AAPL" in prompt
