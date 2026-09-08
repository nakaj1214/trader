"""Minimal J-Quants V2 client used by the live Japanese-stock scanner.

This intentionally does not reuse the legacy V1-compatible provider. V2 uses
static x-api-key authentication and renamed endpoints/fields.
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests

BASE_URL = "https://api.jquants.com/v2"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class JQuantsV2Client:
    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
        min_interval: float = 12.2,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if min_interval < 0:
            raise ValueError("min_interval cannot be negative")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_backoff < 0:
            raise ValueError("retry_backoff cannot be negative")
        self.api_key = api_key or os.getenv("JQUANTS_API_KEY")
        self.timeout = timeout
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._last_call = 0.0

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("JQUANTS_API_KEY is not configured")
        return {"x-api-key": self.api_key}

    def _wait_for_slot(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if self._last_call and elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def _retry_delay(self, response: requests.Response | None, attempt: int) -> float:
        retry_after_raw = response.headers.get("Retry-After") if response is not None else None
        if retry_after_raw is not None:
            try:
                retry_after = float(str(retry_after_raw))
                return max(0.0, retry_after)
            except ValueError:
                pass
        return float(self.retry_backoff * (2**attempt))

    def _request(self, path: str, query: dict[str, str]) -> requests.Response:
        for attempt in range(self.max_retries + 1):
            self._wait_for_slot()
            try:
                response = requests.get(
                    f"{BASE_URL}{path}",
                    params=query,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except requests.RequestException:
                # Even a failed transport attempt counts against the local pacing
                # budget so reconnects cannot accidentally exceed the plan limit.
                self._last_call = time.monotonic()
                if attempt >= self.max_retries:
                    raise
                time.sleep(self._retry_delay(None, attempt))
                continue

            self._last_call = time.monotonic()
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response

            if attempt >= self.max_retries:
                response.raise_for_status()
            time.sleep(self._retry_delay(response, attempt))

        raise RuntimeError("unreachable")

    def _get(self, path: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        query = dict(params or {})
        seen_cursors: set[str] = set()
        while True:
            response = self._request(path, query)
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"Invalid J-Quants response for {path}: expected an object")
            data = payload.get("data", [])
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise ValueError(f"Invalid J-Quants response for {path}: data must be a list of objects")
            rows.extend(data)
            cursor_raw = payload.get("pagination_key") or payload.get("cursor")
            if not cursor_raw:
                break
            cursor = str(cursor_raw)
            if cursor in seen_cursors:
                raise ValueError(f"Invalid J-Quants response for {path}: repeated pagination cursor")
            seen_cursors.add(cursor)
            query["pagination_key"] = cursor
        return rows

    def listed_issues(self, date: str | None = None) -> list[dict[str, Any]]:
        params = {"date": date} if date else None
        return self._get("/equities/master", params)

    def financial_summary(self, code: str) -> list[dict[str, Any]]:
        return self._get("/fins/summary", {"code": code})
