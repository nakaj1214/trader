from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.data.sheets_client import STATUS_COLUMNS, read_holdings, write_status


def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet-id")


def test_read_holdings_uses_named_worksheet(monkeypatch: pytest.MonkeyPatch) -> None:
    _environment(monkeypatch)
    worksheet = Mock()
    worksheet.get_all_records.return_value = [{"ticker": "1111.T"}]
    spreadsheet = Mock()
    spreadsheet.worksheet.return_value = worksheet
    client = Mock()
    client.open_by_key.return_value = spreadsheet
    with patch("src.data.sheets_client.Credentials.from_service_account_info", return_value=Mock()) as credentials, patch(
        "src.data.sheets_client.gspread.authorize", return_value=client
    ):
        assert read_holdings() == [{"ticker": "1111.T"}]

    credentials.assert_called_once()
    spreadsheet.worksheet.assert_called_once_with("保有銘柄")


def test_write_status_replaces_dashboard(monkeypatch: pytest.MonkeyPatch) -> None:
    _environment(monkeypatch)
    worksheet = Mock()
    spreadsheet = Mock()
    spreadsheet.worksheet.return_value = worksheet
    client = Mock()
    client.open_by_key.return_value = spreadsheet
    with patch("src.data.sheets_client.Credentials.from_service_account_info", return_value=Mock()), patch(
        "src.data.sheets_client.gspread.authorize", return_value=client
    ):
        write_status([{"ticker": "1111.T", "exit_reason": None, "status": "ok"}])

    worksheet.clear.assert_called_once_with()
    values = worksheet.update.call_args.args[0]
    assert values[0] == list(STATUS_COLUMNS)
    assert values[1][0] == "1111.T"
    assert values[1][10] == ""


def test_sheets_environment_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    with pytest.raises(RuntimeError, match="required"):
        read_holdings()
