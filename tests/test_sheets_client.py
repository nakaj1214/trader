from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.data.sheets_client import STATUS_COLUMNS, read_holdings, read_status, write_status


def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", '{"type":"service_account"}')
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet-id")


def _client(worksheet: Mock) -> Mock:
    spreadsheet = Mock()
    spreadsheet.worksheet.return_value = worksheet
    client = Mock()
    client.open_by_key.return_value = spreadsheet
    return client


@pytest.mark.parametrize(
    ("reader", "worksheet_name"),
    [(read_holdings, "保有銘柄"), (read_status, "状況")],
)
def test_read_rows_uses_named_worksheet(
    monkeypatch: pytest.MonkeyPatch,
    reader,
    worksheet_name: str,
) -> None:
    _environment(monkeypatch)
    worksheet = Mock()
    worksheet.get_all_records.return_value = [{"ticker": "1111.T"}]
    client = _client(worksheet)
    with (
        patch("src.data.sheets_client.Credentials.from_service_account_info", return_value=Mock()) as credentials,
        patch("src.data.sheets_client.gspread.authorize", return_value=client),
    ):
        assert reader() == [{"ticker": "1111.T"}]

    credentials.assert_called_once()
    client.open_by_key.return_value.worksheet.assert_called_once_with(worksheet_name)


def test_write_status_replaces_dashboard_in_one_atomic_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _environment(monkeypatch)
    worksheet = Mock(id=123, row_count=100, col_count=30)
    client = _client(worksheet)
    with (
        patch("src.data.sheets_client.Credentials.from_service_account_info", return_value=Mock()),
        patch("src.data.sheets_client.gspread.authorize", return_value=client),
    ):
        write_status(
            [
                {
                    "ticker": "=1+1",
                    "entry_price": 100.0,
                    "triggered": True,
                    "exit_reason": None,
                    "status": "ok",
                }
            ]
        )

    worksheet.clear.assert_not_called()
    worksheet.update.assert_not_called()
    worksheet.spreadsheet.batch_update.assert_called_once()
    requests = worksheet.spreadsheet.batch_update.call_args.args[0]["requests"]
    assert [next(iter(request)) for request in requests] == ["repeatCell", "updateCells"]
    rows = requests[1]["updateCells"]["rows"]
    assert [cell["userEnteredValue"]["stringValue"] for cell in rows[0]["values"]] == list(STATUS_COLUMNS)
    assert rows[1]["values"][0] == {"userEnteredValue": {"stringValue": "=1+1"}}
    assert rows[1]["values"][2] == {"userEnteredValue": {"numberValue": 100.0}}
    assert rows[1]["values"][9] == {"userEnteredValue": {"boolValue": True}}
    assert rows[1]["values"][10] == {}


def test_grid_growth_and_write_share_the_same_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    _environment(monkeypatch)
    worksheet = Mock(id=123, row_count=1, col_count=1)
    client = _client(worksheet)
    with (
        patch("src.data.sheets_client.Credentials.from_service_account_info", return_value=Mock()),
        patch("src.data.sheets_client.gspread.authorize", return_value=client),
    ):
        write_status([{"ticker": "1111.T"}])

    body = worksheet.spreadsheet.batch_update.call_args.args[0]
    assert [next(iter(request)) for request in body["requests"]] == [
        "updateSheetProperties",
        "repeatCell",
        "updateCells",
    ]
    properties = body["requests"][0]["updateSheetProperties"]["properties"]
    assert properties["gridProperties"] == {
        "rowCount": 2,
        "columnCount": len(STATUS_COLUMNS),
    }


def test_batch_failure_propagates_without_fallback_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    _environment(monkeypatch)
    worksheet = Mock(id=123, row_count=100, col_count=30)
    worksheet.spreadsheet.batch_update.side_effect = RuntimeError("batch failed")
    client = _client(worksheet)
    with (
        patch("src.data.sheets_client.Credentials.from_service_account_info", return_value=Mock()),
        patch("src.data.sheets_client.gspread.authorize", return_value=client),
        pytest.raises(RuntimeError, match="batch failed"),
    ):
        write_status([])

    worksheet.clear.assert_not_called()
    worksheet.update.assert_not_called()


def test_sheets_environment_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CREDENTIALS_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SHEET_ID", raising=False)
    with pytest.raises(RuntimeError, match="required"):
        read_holdings()
