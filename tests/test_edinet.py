from __future__ import annotations

import gzip
import io
import json
import traceback
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
import requests

from scripts.run_edinet_fetch import main
from src.data import edinet


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDINET_API_KEY", raising=False)
    monkeypatch.setattr(edinet.requests, "get", Mock(side_effect=AssertionError("unexpected HTTP request")))


class Clock:
    def __init__(self) -> None:
        self.elapsed = 0.0
        self.waits: list[float] = []

    def now(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.elapsed += seconds


def response(status: int = 200, rows: list[object] | None = None, **kwargs: object) -> Mock:
    return Mock(
        status_code=status, headers=kwargs,
        json=Mock(return_value={"metadata": {"status": str(status)}, "results": rows or []}),
    )


def client(clock: Clock, **kwargs: object) -> edinet.EdinetClient:
    return edinet.EdinetClient(api_key="test-private-key", clock=clock.now, sleep=clock.sleep, **kwargs)


def test_request_parameters_and_three_second_spacing(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    starts: list[float] = []
    def get(*args: object, **kwargs: object) -> Mock:
        starts.append(clock.now())
        assert args == (edinet.LIST_URL,)
        assert kwargs == {
            "params": {"date": "2026-10-01", "type": "2", "Subscription-Key": "test-private-key"},
            "timeout": 30.0,
        }
        return response()
    monkeypatch.setattr(edinet.requests, "get", get)
    api = client(clock)
    assert api.documents("2026-10-01") == []
    assert api.documents("2026-10-01") == []
    assert api.documents("2026-10-01") == []
    assert starts == [0.0, 3.0, 6.0]


@pytest.mark.parametrize("failure", [429, 500, 501, 502, 503, 504, 599, requests.Timeout("test-private-key")])
def test_transient_retry_then_success(failure: object, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    get = Mock(side_effect=[response(failure) if isinstance(failure, int) else failure, response()])
    monkeypatch.setattr(edinet.requests, "get", get)
    assert client(clock, max_retries=1, retry_backoff=0.0).documents("2026-10-01") == []
    assert get.call_count == 2
    assert clock.elapsed >= 3.0


def test_retry_after_and_bounded_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    get = Mock(side_effect=[response(429, **{"Retry-After": "20"}), response(503), response(200)])
    monkeypatch.setattr(edinet.requests, "get", get)
    assert client(clock, max_retries=2).documents("2026-10-01") == []
    assert [wait for wait in clock.waits if wait] == [20.0, 30.0]


@pytest.mark.parametrize("status,retries,expected", [(401, 5, 1), (404, 5, 1), (429, 1, 2), (500, 1, 2)])
def test_failure_preserves_status_without_key(
    status: int, retries: int, expected: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    get = Mock(return_value=response(status))
    monkeypatch.setattr(edinet.requests, "get", get)
    with pytest.raises(edinet.EdinetError) as error:
        client(Clock(), max_retries=retries, retry_backoff=0).documents("2026-10-01")
    assert get.call_count == expected
    assert error.value.status_code == status
    assert str(status) in str(error.value)
    assert "test-private-key" not in "".join(traceback.format_exception(error.value))


def test_exhausted_transport_has_safe_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    get = Mock(side_effect=requests.ConnectionError("URL?Subscription-Key=test-private-key"))
    monkeypatch.setattr(edinet.requests, "get", get)
    with pytest.raises(edinet.EdinetError, match="ConnectionError") as error:
        client(Clock(), max_retries=1, retry_backoff=0).documents("2026-10-01")
    assert get.call_count == 2
    assert error.value.status_code is None
    assert "test-private-key" not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("payload", [[], {}, {"metadata": {}}, {"metadata": {"status": "200"}},
    {"metadata": {"status": "200"}, "results": ["test-private-key"]}])
def test_invalid_success_is_failure(payload: object, monkeypatch: pytest.MonkeyPatch) -> None:
    result = response()
    result.json.return_value = payload
    monkeypatch.setattr(edinet.requests, "get", Mock(return_value=result))
    with pytest.raises(edinet.EdinetError) as error:
        client(Clock()).documents("2026-10-01")
    assert "test-private-key" not in str(error.value)


def test_invalid_json_does_not_expose_response_body(monkeypatch: pytest.MonkeyPatch) -> None:
    result = response()
    result.json.side_effect = ValueError("test-private-key")
    monkeypatch.setattr(edinet.requests, "get", Mock(return_value=result))
    with pytest.raises(edinet.EdinetError, match="invalid JSON") as error:
        client(Clock()).documents("2026-10-01")
    assert "test-private-key" not in "".join(traceback.format_exception(error.value))


def test_metadata_failure_is_not_cached_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    result = response()
    result.json.return_value = {"metadata": {"status": "404", "message": "test-private-key"}}
    get = Mock(return_value=result)
    monkeypatch.setattr(edinet.requests, "get", get)
    with pytest.raises(edinet.EdinetError) as error:
        client(Clock()).documents("2026-10-01")
    assert error.value.status_code == 404
    assert get.call_count == 1


def test_capture_resume_empty_weekend_and_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    api = Mock(spec=edinet.EdinetClient)
    api.documents.side_effect = [
        [
            {"docID": "first", "docTypeCode": "350", "filerName": "private-holder", "formCode": "060000",
             "Subscription-Key": "test-private-key"},
            {"docID": "correction", "docTypeCode": "360"},
            {"docID": "other", "docTypeCode": "120"},
            {"docID": "erased", "docTypeCode": None, "withdrawalStatus": "2", "filerName": "private-holder"},
        ],
        [], edinet.EdinetError("EDINET HTTP/status 500", status_code=500),
    ]
    captured = datetime.fromisoformat("2026-10-07T12:00:00+09:00")
    start, end = date(2026, 10, 2), date(2026, 10, 4)
    with pytest.raises(edinet.EdinetError):
        edinet.fetch_range(api, start, end, tmp_path, now=lambda: captured)
    first_bytes = (tmp_path / "2026-10-02.json.gz").read_bytes()
    first = edinet.read_day(tmp_path, "2026-10-02")
    assert [row["docID"] for row in first["filings"]] == ["first", "correction"]
    assert first["filings"][0]["formCode"] == "060000"
    assert first["erased_records"][0]["docID"] == "erased"
    assert first["erased_records"][0]["withdrawalStatus"] == "2"
    assert "filerName" not in first["erased_records"][0]
    assert first["captured_at"] == captured.isoformat()
    assert "test-private-key" not in json.dumps(first)
    empty = edinet.read_day(tmp_path, "2026-10-03")
    assert empty["filings"] == empty["erased_records"] == []
    assert not (tmp_path / "2026-10-04.json.gz").exists()
    api.documents.side_effect = None
    api.documents.return_value = []
    assert edinet.fetch_range(api, start, end, tmp_path) == {"fetched": 1, "skipped": 2}
    api.documents.assert_called_with("2026-10-04")
    assert (tmp_path / "2026-10-02.json.gz").read_bytes() == first_bytes
    assert not list(tmp_path.glob("*.tmp"))
    assert "private-holder" not in capsys.readouterr().out


@pytest.mark.parametrize("timestamp,erased,expected", [
    ("2026-10-01T09:00:00+09:00", [], False),
    ("2026-10-01T16:40:00+09:00", [], True),
    ("2026-10-04T17:00:00+09:00", [], True),
    ("2026-10-04T17:00:00+09:00", [{"docID": "erased"}], False),
    ("2026-10-01T07:40:00+00:00", [], True),
    ("2026-10-01T16:40:00", [], False),
    ("invalid", [], False),
])
def test_day_usable(timestamp: str, erased: list[object], expected: bool) -> None:
    record = {"captured_at": timestamp, "filings": [], "erased_records": erased}
    assert edinet.day_usable(record, datetime.fromisoformat("2026-10-01T16:40:00+09:00")) is expected


def test_old_pre_withdrawal_capture_is_unusable() -> None:
    record = edinet.capture_day(
        [{"docID": "old", "docTypeCode": "350", "withdrawalStatus": "0"}],
        datetime.fromisoformat("2026-10-01T17:00:00+09:00"),
    )
    assert not edinet.day_usable(record, datetime.fromisoformat("2026-10-05T16:40:00+09:00"))
    assert not edinet.day_usable({}, datetime.now(edinet.JST))
    naive = datetime.fromisoformat("2026-10-01T00:00:00")
    with pytest.raises(ValueError, match="timezone"):
        edinet.day_usable(record, naive)
    with pytest.raises(ValueError, match="timezone"):
        edinet.capture_day([], naive)


def test_probe_cli_is_private_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("EDINET_API_KEY", "test-private-key")
    rows = [
        {"docTypeCode": "350", "docID": "secret-id", "filerName": "private-holder", "issuerEdinetCode": "E00001"},
        {"docTypeCode": "360"},
        {"docTypeCode": None, "withdrawalStatus": "2"},
    ]
    monkeypatch.setattr(edinet.requests, "get", Mock(return_value=response(rows=rows)))
    assert main(["--probe", "2026-10-01", "--cache-dir", str(tmp_path)]) == 0
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["total_documents"] == 3
    assert [group["count"] for group in report["groups"].values()] == [1, 1, 1]
    assert report["groups"]["350"]["fields"]["issuerEdinetCode"] == {
        "nonempty": 1, "types": ["str"], "lengths": [6],
    }
    for private in ("private-holder", "test-private-key", "secret-id", "E00001"):
        assert private not in output.out + output.err
    assert not list(tmp_path.iterdir())


def test_missing_key_cli_returns_one_without_http(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--probe", "2026-10-01"]) == 1
    assert "EDINET_API_KEY is required" in capsys.readouterr().err


@pytest.mark.parametrize("args", [
    [], ["--probe", "bad-date"], ["--probe", "20261001"], ["--probe", "9999-01-01"],
    ["--fetch"], ["--fetch", "--start", "2026-10-02", "--end", "2026-10-01"],
    ["--probe", "2026-10-01", "--fetch"], ["--probe", "2026-10-01", "--start", "2026-10-01"],
])
def test_invalid_cli_args(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exit:
        main(args)
    assert exit.value.code == 2


def test_fetch_cli_uses_requested_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("EDINET_API_KEY", "test-private-key")
    monkeypatch.setattr(edinet.requests, "get", Mock(return_value=response()))
    assert main(["--fetch", "--start", "2026-10-01", "--end", "2026-10-01", "--cache-dir", str(tmp_path)]) == 0
    assert edinet.read_day(tmp_path, "2026-10-01")["filings"] == []
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == {"fetched": 1, "skipped": 0}


@pytest.mark.parametrize("kwargs", [{"timeout": 0}, {"timeout": float("nan")}, {"max_retries": -1},
                                    {"retry_backoff": -1}, {"retry_backoff": float("inf")}])
def test_invalid_settings(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        client(Clock(), **kwargs)


def test_invalid_cache_and_range(tmp_path: Path) -> None:
    with gzip.open(tmp_path / "2026-10-01.json.gz", "wt") as handle:
        json.dump([], handle)
    with pytest.raises(edinet.EdinetError, match="cache"):
        edinet.read_day(tmp_path, "2026-10-01")
    with pytest.raises(ValueError, match="start"):
        edinet.fetch_range(Mock(), date(2026, 10, 2), date(2026, 10, 1), tmp_path)


def code_archive(text: str = "ＥＤＩＮＥＴコード,証券コード\nE00001,11110\nE00002,130A0\nE00003,\n") -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("EdinetcodeDlInfo.csv", ("ダウンロード日付,2026-10-07\n" + text).encode("cp932"))
    return output.getvalue()


def test_code_mapping_uses_official_zip_cp932_and_alpha_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    get = Mock(return_value=Mock(status_code=200, content=code_archive()))
    monkeypatch.setattr(edinet.requests, "get", get)
    assert client(Clock()).code_map() == {"E00001": "1111.T", "E00002": "130A.T"}
    assert get.call_args.args == (edinet.CODE_LIST_URL,)
    assert get.call_args.kwargs["params"] is None  # Public archive never receives the API key.


@pytest.mark.parametrize("content", [b"not a zip", code_archive("wrong,headers\n"),
                                    code_archive("ＥＤＩＮＥＴコード,証券コード\nE00001,1111\n"),
                                    code_archive("ＥＤＩＮＥＴコード,証券コード\nE00001,\n")])
def test_invalid_code_mapping_is_unavailable(content: bytes) -> None:
    with pytest.raises(edinet.EdinetError):
        edinet.parse_code_list(content)


def test_live_fetch_is_fresh_business_days_and_maps_issuer_only(monkeypatch: pytest.MonkeyPatch) -> None:
    api = Mock()
    api.code_map.return_value = {"E00001": "1111.T"}
    api.documents.return_value = [
        {"docID": "one", "docTypeCode": "350", "issuerEdinetCode": "E00001", "secCode": "99990"},
        {"docID": "two", "docTypeCode": "360", "issuerEdinetCode": "E99999", "secCode": "11110"},
        {"docID": "erased", "docTypeCode": None, "withdrawalStatus": "2"},
    ]
    factory = Mock(return_value=api)
    monkeypatch.setattr(edinet, "EdinetClient", factory)
    sessions = Mock(return_value=["2026-10-05", "2026-10-06", "2026-10-07"])
    monkeypatch.setattr(edinet, "tse_sessions", sessions)
    for _ in range(2):
        rows = edinet.fetch_live_holder_filings("2026-10-07")
        assert [row["ticker"] for row in rows] == ["1111.T", None, None] * 3
    assert factory.call_count == api.code_map.call_count == 2
    assert [call.args[0] for call in api.documents.call_args_list] == ["2026-10-05", "2026-10-06", "2026-10-07"] * 2
    sessions.assert_called_with(date(2026, 8, 8), date(2026, 10, 7))


def test_live_deadline_limits_retry_sleep_and_request_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    get = Mock(side_effect=[response(503), response(200)])
    monkeypatch.setattr(edinet.requests, "get", get)
    with pytest.raises(edinet.EdinetError, match="deadline"):
        client(clock, deadline=10.0).documents("2026-10-07")
    assert get.call_count == 1 and clock.elapsed == 0
    assert get.call_args.kwargs["timeout"] == 10.0
    clock.elapsed = 11.0
    with pytest.raises(edinet.EdinetError, match="deadline"):
        client(clock, deadline=10.0).documents("2026-10-07")
    assert get.call_count == 1


def holder(doc_id: str = "one", submitted: str = "2026-10-07T16:40:00", **kwargs: object) -> dict:
    return {"docID": doc_id, "docTypeCode": "350", "formCode": "010000", "ticker": "1111.T",
            "submitDateTime": submitted, "withdrawalStatus": "0", **kwargs}


def features(rows: list[dict] | None, ticker: str = "1111.T") -> dict:
    return edinet.holder_filing_features(rows, ticker, date(2026, 10, 7),
                                         datetime.fromisoformat("2026-10-07T16:40:00+09:00"))


def test_holder_window_cutoff_and_new_vs_change_forms() -> None:
    rows = [holder("boundary", "2026-08-08T10:00:00+09:00"),  # Exactly 60 calendar days.
            holder("old", "2026-08-07T10:00:00"), holder("late", "2026-10-07T16:40:01"),
            holder("future", "2026-10-08T10:00:00"), holder("other", ticker="9999.T"),
            holder("new-special", "2026-10-07T07:40:00+00:00", formCode="030000"),
            *[holder(form, "2026-10-06T10:00:00", formCode=form) for form in ("010002", "020002", "030002")],
            holder("correction", "2026-10-06T11:00:00", docTypeCode="360", formCode="090001")]
    assert features(rows) == {"major_holder_filings_60d": 6, "major_holder_new_filings_60d": 2,
                              "days_since_major_holder_filing": 0}
    assert features([rows[0]])["days_since_major_holder_filing"] == 60


def test_missing_data_is_distinct_from_a_successful_empty_window() -> None:
    assert features(None) == dict.fromkeys(edinet.HOLDER_FEATURE_KEYS)
    assert features([]) == {"major_holder_filings_60d": 0, "major_holder_new_filings_60d": 0,
                            "days_since_major_holder_filing": None}
    assert features([holder(formCode="unknown")]) == {
        "major_holder_filings_60d": 1, "major_holder_new_filings_60d": None, "days_since_major_holder_filing": 0,
    }


def test_holder_uses_latest_live_operation_and_excludes_withdrawn_children() -> None:
    rows = [holder("one", "2026-10-06T10:00:00", opeDateTime="2026-10-06T10:00:00"),
            holder("one", "2026-10-06T10:00:00", opeDateTime="2026-10-07T16:39:00"),
            holder("one", "2026-10-06T10:00:00", opeDateTime="2026-10-07T16:41:00", formCode="010002"),
            holder("removed"), holder("child", docTypeCode="360", parentDocID="removed"),
            holder("grandchild", docTypeCode="360", parentDocID="child"),
            {"docID": "withdraw", "docTypeCode": None, "withdrawalStatus": "1",
             "parentDocID": "removed", "submitDateTime": "2026-10-07T16:39:00"},
            holder("erased"), {"docID": "erased", "docTypeCode": None, "withdrawalStatus": "2"}]
    assert features(rows) == {"major_holder_filings_60d": 1, "major_holder_new_filings_60d": 0,
                              "days_since_major_holder_filing": 1}
    assert features([holder(), {"docTypeCode": None, "withdrawalStatus": "1", "parentDocID": "one",
                               "submitDateTime": "2026-10-07T16:40:01"}])["major_holder_filings_60d"] == 0
    assert features([holder(), {"docID": "one", "docTypeCode": None, "withdrawalStatus": "2",
                               "opeDateTime": "2026-10-07T16:40:01"}])["major_holder_filings_60d"] == 0
    assert features([holder(opeDateTime="2026-10-07T16:41:00")])["major_holder_filings_60d"] == 1


def test_invalid_filing_metadata_fails_safely() -> None:
    for row in [holder(submitted="secret-invalid-date"), holder(doc_id="")]:
        with pytest.raises(edinet.EdinetError):
            features([row])
    with pytest.raises(edinet.EdinetError, match="field type"):
        edinet.capture_day([holder(issuerEdinetCode={"secret": "value"})], datetime.now(edinet.JST))
