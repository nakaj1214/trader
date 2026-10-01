from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
import requests

from src.data.jquants_history import (
    HistoryFetchStopped,
    default_fetch_range,
    fetch_range,
    load_cache,
    monthly_master_days,
    probe,
    read_day,
)
from src.data.jquants_v2_client import JQuantsV2Client

REPO_ROOT = Path(__file__).resolve().parents[1]
SILENT = {"log": lambda _: None}


class FakeClient:
    """Serves canned rows per day and records every call."""

    def __init__(
        self,
        bars: dict[str, list[dict[str, Any]]] | None = None,
        masters: dict[str, list[dict[str, Any]]] | None = None,
        default_master: list[dict[str, Any]] | None = None,
    ) -> None:
        self.bars = bars or {}
        self.masters = masters or {}
        self.default_master = default_master or [{"Code": "11110"}]
        self.calls: list[tuple[str, str]] = []

    def daily_bars(self, date: str) -> list[dict[str, Any]]:
        self.calls.append(("bars", date))
        return self.bars.get(date, [{"Code": "11110", "C": 100.0}])

    def listed_issues(self, date: str | None = None) -> list[dict[str, Any]]:
        assert date is not None
        self.calls.append(("master", date))
        return self.masters.get(date, self.default_master)

    def financial_summary_by_date(self, date: str) -> list[dict[str, Any]]:
        self.calls.append(("fins", date))
        return []


def _http_error(status: int, message: str = "") -> requests.HTTPError:
    response = Mock(spec=requests.Response)
    response.status_code = status
    response.json.return_value = {"message": message}
    return requests.HTTPError(str(status), response=response)


def _response(payload: dict[str, Any]) -> Mock:
    response = Mock(spec=requests.Response)
    response.status_code = 200
    response.headers = {}
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_paged_bars_are_joined_and_saved(tmp_path: Path) -> None:
    client = JQuantsV2Client(api_key="k", min_interval=0)
    pages = [
        _response({"data": [{"Code": "11110", "C": 1}], "pagination_key": "p2"}),
        _response({"data": [{"Code": "22220", "C": 2}]}),
    ]
    sent: list[dict[str, str]] = []

    def fake_get(url: str, *, params: dict[str, str], **kwargs: object) -> Mock:
        del url, kwargs
        sent.append(dict(params))  # the client reuses one dict, so snapshot it per call
        return pages[len(sent) - 1]

    with patch("src.data.jquants_v2_client.requests.get", side_effect=fake_get):
        fetch_range(client, date(2026, 1, 5), date(2026, 1, 5), tmp_path, kinds=("bars",), **SILENT)

    assert [row["Code"] for row in read_day(tmp_path, "bars", "2026-01-05")] == ["11110", "22220"]
    assert sent == [{"date": "2026-01-05"}, {"date": "2026-01-05", "pagination_key": "p2"}]


def test_cached_days_are_not_fetched_again(tmp_path: Path) -> None:
    client = FakeClient()
    fetch_range(client, date(2026, 1, 5), date(2026, 1, 9), tmp_path, **SILENT)
    first_calls = len(client.calls)
    assert first_calls > 0

    client.calls.clear()
    fetch_range(client, date(2026, 1, 5), date(2026, 1, 9), tmp_path, **SILENT)

    assert client.calls == []


def test_fins_cover_every_calendar_day_and_empty_days_are_cached(tmp_path: Path) -> None:
    client = FakeClient()
    fetch_range(client, date(2026, 1, 3), date(2026, 1, 5), tmp_path, kinds=("fins",), **SILENT)

    assert [day for kind, day in client.calls if kind == "fins"] == ["2026-01-03", "2026-01-04", "2026-01-05"]
    assert load_cache(tmp_path).days("fins") == ["2026-01-03", "2026-01-04", "2026-01-05"]
    assert read_day(tmp_path, "fins", "2026-01-03") == []


def test_interrupted_run_resumes_with_only_the_missing_days(tmp_path: Path) -> None:
    class Flaky(FakeClient):
        def daily_bars(self, date: str) -> list[dict[str, Any]]:
            if date == "2026-01-07":
                raise RuntimeError("network down")
            return super().daily_bars(date)

    with pytest.raises(RuntimeError, match="network down"):
        fetch_range(Flaky(), date(2026, 1, 5), date(2026, 1, 9), tmp_path, kinds=("bars",), **SILENT)
    assert load_cache(tmp_path).days("bars") == ["2026-01-05", "2026-01-06"]
    assert not list((tmp_path / "bars").glob("*.tmp"))

    resumed = FakeClient()
    fetch_range(resumed, date(2026, 1, 5), date(2026, 1, 9), tmp_path, kinds=("bars",), **SILENT)

    assert [day for _, day in resumed.calls] == ["2026-01-07", "2026-01-08", "2026-01-09"]


@pytest.mark.parametrize(
    ("status", "message"),
    [(400, "invalid parameter"), (403, "API key is invalid"), (404, "not found")],
)
def test_any_4xx_stops_the_run_and_keeps_the_cache(tmp_path: Path, status: int, message: str) -> None:
    class Rejecting(FakeClient):
        def daily_bars(self, date: str) -> list[dict[str, Any]]:
            if date == "2026-01-06":
                raise _http_error(status, message)
            return super().daily_bars(date)

    client = Rejecting()
    with pytest.raises(HistoryFetchStopped, match=rf"HTTP {status}.*bars 2026-01-06.*{message}"):
        fetch_range(client, date(2026, 1, 5), date(2026, 1, 9), tmp_path, kinds=("bars",), **SILENT)

    assert load_cache(tmp_path).days("bars") == ["2026-01-05"]  # kept; later days are not attempted
    assert [day for _, day in client.calls] == ["2026-01-05"]


@pytest.mark.parametrize("status", [429, 503])
def test_429_and_5xx_are_not_treated_as_a_stop(tmp_path: Path, status: int) -> None:
    class Throttled(FakeClient):
        def daily_bars(self, date: str) -> list[dict[str, Any]]:
            raise _http_error(status)

    with pytest.raises(requests.HTTPError) as caught:
        fetch_range(Throttled(), date(2026, 1, 5), date(2026, 1, 5), tmp_path, kinds=("bars",), **SILENT)
    assert not isinstance(caught.value, HistoryFetchStopped)


def test_extra_master_is_fetched_once_per_new_code_and_non_master_codes_are_remembered(tmp_path: Path) -> None:
    bars = {
        "2026-01-05": [{"Code": "11110"}],
        "2026-01-06": [{"Code": "11110"}, {"Code": "22220"}],  # 22220 listed after the 01-05 master
        "2026-01-07": [{"Code": "11110"}, {"Code": "22220"}, {"Code": "99990"}],  # ETF-like: never in master
        "2026-01-08": [{"Code": "11110"}, {"Code": "22220"}, {"Code": "99990"}],
    }
    masters = {
        "2026-01-05": [{"Code": "11110"}],
        "2026-01-06": [{"Code": "11110"}, {"Code": "22220"}],
        "2026-01-07": [{"Code": "11110"}, {"Code": "22220"}],
    }
    client = FakeClient(bars=bars, masters=masters)

    summary = fetch_range(client, date(2026, 1, 5), date(2026, 1, 8), tmp_path, kinds=("bars", "master"), **SILENT)

    assert [day for kind, day in client.calls if kind == "master"] == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert summary["extra_master_fetches"] == 2
    assert load_cache(tmp_path).non_master_codes() == {"99990"}

    client.calls.clear()
    fetch_range(client, date(2026, 1, 5), date(2026, 1, 8), tmp_path, kinds=("bars", "master"), **SILENT)
    assert client.calls == []


def test_probe_requests_first_and_last_session_once_and_writes_nothing(tmp_path: Path) -> None:
    client = FakeClient()
    result = probe(client, date(2026, 1, 3), date(2026, 1, 10))

    assert client.calls == [("bars", "2026-01-05"), ("bars", "2026-01-09")]
    assert result["first"]["date"] == "2026-01-05" and result["last"]["date"] == "2026-01-09"
    assert list(tmp_path.iterdir()) == []


def test_probe_stops_on_4xx() -> None:
    class Rejecting(FakeClient):
        def daily_bars(self, date: str) -> list[dict[str, Any]]:
            raise _http_error(403, "plan")

    with pytest.raises(HistoryFetchStopped, match="HTTP 403"):
        probe(Rejecting(), date(2026, 1, 5), date(2026, 1, 9))


def test_default_fetch_range_keeps_a_margin_at_both_ends() -> None:
    assert default_fetch_range(date(2026, 10, 1)) == (date(2024, 10, 8), date(2026, 7, 2))


def test_monthly_master_days_picks_first_in_range_session_of_each_month() -> None:
    sessions = ["2026-01-28", "2026-01-29", "2026-02-02", "2026-02-03", "2026-03-02"]
    assert monthly_master_days(sessions) == ["2026-01-28", "2026-02-02", "2026-03-02"]


def test_cache_directory_is_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".data/jquants/bars/2026-01-05.json.gz"],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0


def test_unknown_kind_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown kinds"):
        fetch_range(FakeClient(), date(2026, 1, 5), date(2026, 1, 5), tmp_path, kinds=("prices",), **SILENT)
