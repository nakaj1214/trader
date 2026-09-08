"""EDINET API v2 provider for point-in-time disclosure metadata."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any

import requests

BASE_URL = "https://api.edinet-fsa.go.jp/api/v2"


@dataclass(frozen=True)
class EdinetDocument:
    doc_id: str
    edinet_code: str | None
    sec_code: str | None
    filer_name: str | None
    doc_type_code: str | None
    ordinance_code: str | None
    form_code: str | None
    period_start: str | None
    period_end: str | None
    submit_datetime: str | None
    doc_description: str | None

    @classmethod
    def from_api(cls, row: dict[str, Any]) -> EdinetDocument:
        return cls(
            doc_id=str(row.get("docID") or ""),
            edinet_code=row.get("edinetCode"),
            sec_code=row.get("secCode"),
            filer_name=row.get("filerName"),
            doc_type_code=row.get("docTypeCode"),
            ordinance_code=row.get("ordinanceCode"),
            form_code=row.get("formCode"),
            period_start=row.get("periodStart"),
            period_end=row.get("periodEnd"),
            submit_datetime=row.get("submitDateTime"),
            doc_description=row.get("docDescription"),
        )


class EdinetProvider:
    """Thin client for official EDINET disclosure metadata."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.api_key = api_key or os.getenv("EDINET_API_KEY")
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(self.api_key)

    def list_documents(self, target_date: str | date) -> list[EdinetDocument]:
        if not self.api_key:
            raise RuntimeError("EDINET_API_KEY is not configured")
        date_text = target_date.isoformat() if isinstance(target_date, date) else target_date
        response = requests.get(
            f"{BASE_URL}/documents.json",
            params={
                "date": date_text,
                "type": 2,
                "Subscription-Key": self.api_key,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        if not isinstance(results, list):
            return []
        return [EdinetDocument.from_api(row) for row in results if isinstance(row, dict)]

    def list_stock_documents(self, target_date: str | date) -> list[EdinetDocument]:
        """Return submissions associated with a Japanese security code."""
        return [doc for doc in self.list_documents(target_date) if doc.sec_code]