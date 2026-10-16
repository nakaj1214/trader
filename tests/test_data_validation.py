from __future__ import annotations

import pandas as pd
import pytest

from src.data.validation import validate_ohlcv


def test_validate_ohlcv_accepts_valid_data() -> None:
    df = pd.DataFrame(
        {
            "Open": [100, 105],
            "High": [110, 115],
            "Low": [95, 100],
            "Close": [108, 112],
            "Volume": [1000, 2000],
        },
        index=pd.to_datetime(["2026-01-05", "2026-01-06"]),
    )
    assert validate_ohlcv(df) == []


def test_validate_ohlcv_detects_structural_errors() -> None:
    df = pd.DataFrame(
        {
            "Open": [100, 105],
            "High": [90, 115],
            "Low": [95, 120],
            "Close": [108, 112],
            "Volume": [-1, 2000],
        },
        index=pd.to_datetime(["2026-01-05", "2026-01-05"]),
    )
    codes = {issue.code for issue in validate_ohlcv(df)}
    assert "DUPLICATE_INDEX" in codes
    assert "HIGH_INCONSISTENT" in codes
    assert "LOW_INCONSISTENT" in codes
    assert "NEGATIVE_VOLUME" in codes


@pytest.mark.parametrize("column", ["Open", "High", "Low", "Close", "Volume"])
@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_validation_rejects_nonfinite_ohlcv(column: str, value: float) -> None:
    frame = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1000.0},
                         index=pd.bdate_range("2026-01-05", periods=2))
    frame.loc[frame.index[0], column] = value
    codes = {issue.code for issue in validate_ohlcv(frame)}
    prefix = "VOLUME" if column == "Volume" else "PRICE"
    assert f"{prefix}_{'NAN' if pd.isna(value) else 'NONFINITE'}" in codes


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_validation_rejects_invalid_adjusted_close(value: float) -> None:
    frame = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1000.0,
                          "Adj Close": [value, 100.0]}, index=pd.bdate_range("2026-01-05", periods=2))
    assert "ADJUSTED_PRICE_INVALID" in {issue.code for issue in validate_ohlcv(frame)}


@pytest.mark.parametrize("column", ["Open", "High", "Low", "Close"])
@pytest.mark.parametrize("value", [0.0, -1.0])
def test_validation_rejects_nonpositive_prices(column: str, value: float) -> None:
    frame = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1000.0},
                         index=pd.bdate_range("2026-01-05", periods=2))
    frame.loc[frame.index[0], column] = value
    assert "NONPOSITIVE_PRICE" in {issue.code for issue in validate_ohlcv(frame)}


def test_validation_detects_duplicate_market_dates_and_invalid_dates() -> None:
    frame = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1000.0},
                         index=pd.to_datetime(["2026-01-05 09:00", "2026-01-05 15:30"]))
    assert "DUPLICATE_INDEX" in {issue.code for issue in validate_ohlcv(frame)}
    frame.index = pd.Index(["2026-01-05", "invalid"])
    assert "INVALID_INDEX" in {issue.code for issue in validate_ohlcv(frame)}


def test_real_network_access_is_blocked_in_tests() -> None:
    import socket

    from tests.conftest import BLOCKED_NETWORK_ATTEMPTS

    before = len(BLOCKED_NETWORK_ATTEMPTS)
    with pytest.raises(RuntimeError, match="forbidden"):
        socket.getaddrinfo("example.com", 443)
    del BLOCKED_NETWORK_ATTEMPTS[before:]  # keep the run-level count to unintended attempts only


def test_curl_cffi_native_transport_is_blocked_and_counted_like_a_python_socket() -> None:
    """yfinance talks through curl_cffi, which calls libcurl directly and never touches Python's socket module."""
    import http.server
    import threading

    from curl_cffi import requests as curl_requests

    from tests.conftest import BLOCKED_NETWORK_ATTEMPTS

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"reached")

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)  # local only: nothing here leaves the machine
    threading.Thread(target=server.serve_forever, daemon=True).start()
    before = len(BLOCKED_NETWORK_ATTEMPTS)
    try:
        with pytest.raises(RuntimeError, match="forbidden"):
            curl_requests.get(f"http://127.0.0.1:{server.server_address[1]}/", timeout=5)
        assert len(BLOCKED_NETWORK_ATTEMPTS) == before + 1
        assert BLOCKED_NETWORK_ATTEMPTS[-1] == "native-transport"
    finally:
        server.shutdown()
        del BLOCKED_NETWORK_ATTEMPTS[before:]  # keep the run-level count to unintended attempts only
