"""ダッシュボードHTMLの静的検証テスト

Residual Risk 対応:
- stock.html に short-interest-panel / institutional-panel の DOM が存在することを保証する。
  これらが欠落すると stock.js の renderShortInterestPanel / renderInstitutionalPanel が
  即 return し、パネルが画面に表示されなくなる。
"""

import re
from pathlib import Path

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"
STOCK_HTML = DASHBOARD_DIR / "stock.html"


def _get_ids(html: str) -> set[str]:
    """HTML 文字列から id 属性値をすべて抽出する。"""
    return set(re.findall(r'\bid=["\']([^"\']+)["\']', html))


class TestStockHtmlPanels:
    """stock.html に必要な DOM コンテナが存在するか検証する。"""

    def setup_method(self):
        self.html = STOCK_HTML.read_text(encoding="utf-8")
        self.ids = _get_ids(self.html)

    def test_short_interest_panel_exists(self):
        """Phase 11: short-interest-panel が stock.html に存在すること。"""
        assert "short-interest-panel" in self.ids, (
            "stock.html に id='short-interest-panel' が見つかりません。"
            " stock.js の renderShortInterestPanel が即 return します。"
        )

    def test_institutional_panel_exists(self):
        """Phase 12: institutional-panel が stock.html に存在すること。"""
        assert "institutional-panel" in self.ids, (
            "stock.html に id='institutional-panel' が見つかりません。"
            " stock.js の renderInstitutionalPanel が即 return します。"
        )

    def test_sizing_panel_exists(self):
        """Phase 8: sizing-panel が stock.html に存在すること。"""
        assert "sizing-panel" in self.ids

    def test_risk_panel_exists(self):
        """Phase 1: risk-panel が stock.html に存在すること。"""
        assert "risk-panel" in self.ids

    def test_evidence_panel_exists(self):
        """Phase 2: evidence-panel が stock.html に存在すること。"""
        assert "evidence-panel" in self.ids
