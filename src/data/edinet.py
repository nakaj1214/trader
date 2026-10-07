"""EDINET v2 acquisition and live holder diagnostics; cached days are immutable."""

from __future__ import annotations

import csv
import gzip
import io
import json
import math
import os
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo

import requests

from src.data.jquants_history import tse_sessions

JST = ZoneInfo("Asia/Tokyo")
LIST_URL = "https://api.edinet-fsa.go.jp/api/v2/documents.json"
CODE_LIST_URL = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"
MIN_INTERVAL_SECONDS = 3.0
MAX_RETRIES = 5
RETRY_BACKOFF_SECONDS = 15.0
LIVE_FETCH_BUDGET_SECONDS = 300.0
HOLDER_FEATURE_KEYS = ("major_holder_filings_60d", "major_holder_new_filings_60d", "days_since_major_holder_filing")
# Official API appendix 1: changes are also type 350, but have different form codes.
NEW_HOLDER_FORMS = {"010000", "030000"}
CHANGE_HOLDER_FORMS = {"010002", "020002", "030002"}
# These fields are documented in the official v2 specification; probe confirms their use for 350/360.
FIELDS = (
    "docID", "submitDateTime", "docTypeCode", "secCode", "edinetCode", "issuerEdinetCode",
    "subjectEdinetCode", "filerName", "ordinanceCode", "formCode", "parentDocID", "opeDateTime",
    "withdrawalStatus", "docInfoEditStatus", "disclosureStatus",
)
ERASED_FIELDS = tuple(field for field in FIELDS if field != "filerName")


class EdinetError(RuntimeError):
    """A safe failure reason, without response bodies, URLs, or original exception text."""

    def __init__(self, reason: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(reason)


class EdinetClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        max_retries: int = MAX_RETRIES,
        retry_backoff: float = RETRY_BACKOFF_SECONDS,
        deadline: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        if max_retries < 0 or not math.isfinite(retry_backoff) or retry_backoff < 0:
            raise ValueError("retry settings must be finite and non-negative")
        self._api_key = api_key if api_key is not None else os.getenv("EDINET_API_KEY")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None
        self._deadline = deadline

    def _remaining(self) -> float:
        remaining = self.timeout if self._deadline is None else self._deadline - self._clock()
        if remaining <= 0:
            raise EdinetError("EDINET fetch deadline exceeded")
        return remaining

    def _wait(self, seconds: float) -> None:
        if self._deadline is not None and seconds >= self._remaining():
            raise EdinetError("EDINET fetch deadline exceeded")
        self._sleep(seconds)

    def documents(self, day: str) -> list[dict[str, Any]]:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("date must be YYYY-MM-DD")
        if not self._api_key or not self._api_key.strip():
            raise EdinetError("EDINET_API_KEY is required (export it from .env before running)")
        response = self._request(LIST_URL, {"date": day, "type": "2", "Subscription-Key": self._api_key})
        try:
            payload = response.json()
        except ValueError:
            raise EdinetError("EDINET returned invalid JSON") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("metadata"), dict):
            raise EdinetError("EDINET returned invalid metadata")
        raw_status = payload["metadata"].get("status")
        if not isinstance(raw_status, (str, int)) or not str(raw_status).isdigit():
            raise EdinetError("EDINET returned invalid status")
        status = int(raw_status)
        if status != 200:
            raise EdinetError(f"EDINET HTTP/status {status}", status_code=status)
        rows = payload.get("results")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise EdinetError("EDINET returned invalid results")
        return rows

    def code_map(self) -> dict[str, str]:
        return parse_code_list(self._request(CODE_LIST_URL).content)

    def _request(self, url: str, params: dict[str, str] | None = None) -> requests.Response:
        for attempt in range(self.max_retries + 1):
            if self._last_call is not None:
                self._wait(max(0.0, MIN_INTERVAL_SECONDS - (self._clock() - self._last_call)))
            response = None
            try:
                response = requests.get(
                    url, params=params, timeout=min(self.timeout, self._remaining()),
                )
            except requests.RequestException as exc:
                failure = EdinetError(f"EDINET transport failure: {type(exc).__name__}")
                status = None
            else:
                status = response.status_code
                if status == 200:
                    self._remaining()
                    return response
                failure = EdinetError(f"EDINET HTTP/status {status}", status_code=status)
            finally:
                self._last_call = self._clock()
            retryable = status is None or status == 429 or 500 <= status <= 599
            if not retryable or attempt == self.max_retries:
                raise failure from None
            delay = self.retry_backoff * 2**attempt
            if response is not None:
                try:
                    retry_after = float(response.headers.get("Retry-After", ""))
                    if math.isfinite(retry_after):
                        delay = max(delay, retry_after)
                except ValueError:
                    pass
            self._wait(delay)
        raise AssertionError("unreachable")


def parse_code_list(content: bytes) -> dict[str, str]:
    try:
        with ZipFile(io.BytesIO(content)) as archive:
            text = archive.read("EdinetcodeDlInfo.csv").decode("cp932")
        stream = io.StringIO(text)
        next(stream)  # Download-date/count heading, before the actual CSV columns.
        reader = csv.DictReader(stream)
        if not {"ＥＤＩＮＥＴコード", "証券コード"}.issubset(reader.fieldnames or []):
            raise EdinetError("EDINET code list is missing required columns")
        result = {}
        for row in reader:
            issuer = (row.get("ＥＤＩＮＥＴコード") or "").strip()
            code = (row.get("証券コード") or "").strip()
            if not code:
                continue  # Unlisted issuers do not have a listed-security ticker.
            if not issuer or len(code) != 5 or not code.isascii() or not code.isalnum():
                raise EdinetError("EDINET code list has an invalid security code")
            result[issuer] = code[:4] + ".T"
        if not result:
            raise EdinetError("EDINET code list contains no listed issuers")
        return result
    except (BadZipFile, KeyError, UnicodeError, StopIteration, csv.Error):
        raise EdinetError("Invalid EDINET code-list archive") from None


def fetch_live_holder_filings(as_of: str) -> list[dict[str, Any]]:
    """Fresh lists for this scan only; resumable disk snapshots are never used live."""
    end = date.fromisoformat(as_of)
    client = EdinetClient(deadline=time.monotonic() + LIVE_FETCH_BUDGET_SECONDS)
    codes = client.code_map()
    filings = []
    for day in tse_sessions(end - timedelta(days=60), end):
        record = capture_day(client.documents(day), datetime.now(JST))
        for row in record["filings"] + record["erased_records"]:
            filings.append({**row, "ticker": codes.get(row.get("issuerEdinetCode"))})
    return filings


def _filing_time(value: Any) -> datetime:
    try:
        stamp = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise EdinetError("Invalid EDINET filing timestamp") from None
    return stamp.replace(tzinfo=JST) if stamp.utcoffset() is None else stamp.astimezone(JST)


def holder_filing_features(
    filings: list[dict[str, Any]] | None, ticker: str, as_of: date, cutoff: datetime,
) -> dict[str, int | None]:
    """Live diagnostics only. Historical reconstruction is deliberately out of scope."""
    if filings is None:
        return dict.fromkeys(HOLDER_FEATURE_KEYS)
    if cutoff.utcoffset() is None:
        raise ValueError("cutoff must have a timezone")
    withdrawn: set[str] = set()
    latest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for row in filings:
        if row.get("withdrawalStatus") == "2":
            withdrawn.add(str(row.get("docID")))
        if row.get("withdrawalStatus") == "1":
            withdrawn.add(str(row.get("parentDocID")))
        if row.get("docTypeCode") not in ("350", "360"):
            continue
        submitted = _filing_time(row.get("submitDateTime"))
        operation = _filing_time(row["opeDateTime"]) if row.get("opeDateTime") else submitted
        if submitted > cutoff:
            continue
        doc_id = row.get("docID")
        if not isinstance(doc_id, str) or not doc_id:
            raise EdinetError("Invalid EDINET document identifier")
        if doc_id not in latest or latest[doc_id][0] < operation:
            latest[doc_id] = (operation, row)
    # A same-day withdrawal has not yet erased the original list row. Exclude its children too.
    while children := {doc_id for doc_id, (_, row) in latest.items()
                       if row.get("parentDocID") in withdrawn} - withdrawn:
        withdrawn.update(children)
    count = new_count = 0
    ages = []
    new_known = True
    for doc_id, (_, row) in latest.items():
        if doc_id in withdrawn or row.get("withdrawalStatus") != "0" or row.get("ticker") != ticker:
            continue
        age = (as_of - _filing_time(row["submitDateTime"]).date()).days
        if not 0 <= age <= 60:
            continue
        count += 1
        ages.append(age)
        if row["docTypeCode"] == "350":
            form = row.get("formCode")
            new_count += form in NEW_HOLDER_FORMS
            if form not in NEW_HOLDER_FORMS | CHANGE_HOLDER_FORMS:
                new_known = False
    return {
        "major_holder_filings_60d": count,
        "major_holder_new_filings_60d": new_count if new_known else None,
        "days_since_major_holder_filing": min(ages) if ages else None,
    }


def capture_day(rows: list[dict[str, Any]], captured_at: datetime) -> dict[str, Any]:
    if captured_at.utcoffset() is None:
        raise ValueError("captured_at must have a timezone")
    for row in rows:
        if row.get("docTypeCode") in ("350", "360", None) and any(
            row.get(key) is not None and not isinstance(row[key], str) for key in FIELDS
        ):
            raise EdinetError("Invalid EDINET document field type")
    return {
        "captured_at": captured_at.astimezone(JST).isoformat(),
        "filings": [{key: row.get(key) for key in FIELDS} for row in rows if row.get("docTypeCode") in ("350", "360")],
        "erased_records": [
            {key: row.get(key) for key in ERASED_FIELDS} for row in rows if row.get("docTypeCode") is None
        ],
    }


def day_usable(day_record: dict[str, Any], cutoff: datetime) -> bool:
    """Conservative plan gate: a later capture and no unidentified erased documents."""
    if cutoff.utcoffset() is None:
        raise ValueError("cutoff must have a timezone")
    try:
        captured = datetime.fromisoformat(day_record["captured_at"])
        erased = day_record["erased_records"]
    except (KeyError, TypeError, ValueError):
        return False
    return captured.utcoffset() is not None and captured >= cutoff and isinstance(erased, list) and not erased


def read_day(cache_dir: Path, day: str) -> dict[str, Any]:
    with gzip.open(cache_dir / f"{day}.json.gz", "rt", encoding="utf-8") as handle:
        record = json.load(handle)
    if (
        not isinstance(record, dict)
        or not isinstance(record.get("captured_at"), str)
        or any(not isinstance(record.get(key), list) for key in ("filings", "erased_records"))
    ):
        raise EdinetError("Invalid EDINET cache record")
    return record


def fetch_range(
    client: EdinetClient,
    start: date,
    end: date,
    cache_dir: Path,
    *,
    now: Callable[[], datetime] = lambda: datetime.now(JST),
    log: Callable[[str], None] = print,
) -> dict[str, int]:
    """Fetch every calendar day, including holidays; failed days are never cached as empty."""
    if start > end:
        raise ValueError("start must not be after end")
    fetched = skipped = 0
    day = start
    while day <= end:
        path = cache_dir / f"{day.isoformat()}.json.gz"
        if path.exists():
            skipped += 1
        else:
            record = capture_day(client.documents(day.isoformat()), now())
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, path)
            fetched += 1
            log(f"{day.isoformat()} filings={len(record['filings'])} erased={len(record['erased_records'])}")
        day += timedelta(days=1)
    return {"fetched": fetched, "skipped": skipped}


def probe(client: EdinetClient, day: str) -> dict[str, Any]:
    """Expose only field presence/types/lengths, never names or raw response values."""
    started = time.monotonic()
    rows = client.documents(day)
    record = capture_day(rows, datetime.now(JST))
    groups = {
        "350": [row for row in record["filings"] if row["docTypeCode"] == "350"],
        "360": [row for row in record["filings"] if row["docTypeCode"] == "360"],
        "erased": record["erased_records"],
    }
    return {
        "date": day,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "total_documents": len(rows),
        "groups": {
            kind: {
                "count": len(items),
                "fields": {
                    key: {
                        "nonempty": sum(item.get(key) not in (None, "") for item in items),
                        "types": sorted({type(item[key]).__name__ for item in items if item.get(key) is not None}),
                        "lengths": sorted({len(str(item[key])) for item in items if item.get(key) is not None}),
                    }
                    for key in FIELDS
                },
            }
            for kind, items in groups.items()
        },
    }
