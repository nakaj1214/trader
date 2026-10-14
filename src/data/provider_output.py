"""Keep third-party output and exception bodies out of public runner logs."""

from __future__ import annotations

import math
from enum import StrEnum

import requests

from src.data.quiet_output import suppress_provider_output

__all__ = ["MAX_RETRY_AFTER_SECONDS", "ProviderFailure", "ProviderFailureCategory", "bounded_retry_after",
           "classify_provider_failure", "safe_error_details", "suppress_provider_output"]

MAX_RETRY_AFTER_SECONDS = 300.0


class ProviderFailureCategory(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    PROTOCOL = "protocol"
    EMPTY = "empty"
    INVALID_OHLCV = "invalid_ohlcv"
    VALIDATION = "validation"
    AUTH = "auth"
    UNEXPECTED = "unexpected"


def classify_provider_failure(error: Exception) -> ProviderFailureCategory:
    status = getattr(error, "status_code", getattr(getattr(error, "response", None), "status_code", None))
    if isinstance(status, int):
        if status == 429:
            return ProviderFailureCategory.RATE_LIMIT
        if status in (401, 403):
            return ProviderFailureCategory.AUTH
        if 500 <= status <= 599:
            return ProviderFailureCategory.SERVER_ERROR
    if isinstance(error, (requests.Timeout, TimeoutError)):
        return ProviderFailureCategory.TIMEOUT
    if isinstance(error, requests.RequestException):
        return ProviderFailureCategory.PROTOCOL
    if isinstance(error, RuntimeError):
        return ProviderFailureCategory.PROTOCOL
    if isinstance(error, (ValueError, KeyError)):
        return ProviderFailureCategory.VALIDATION
    if type(error).__name__ == "YFRateLimitError":
        return ProviderFailureCategory.RATE_LIMIT
    return ProviderFailureCategory.UNEXPECTED


def bounded_retry_after(value: object, *, maximum: float = MAX_RETRY_AFTER_SECONDS) -> float | None:
    try:
        seconds = float(str(value))
    except (TypeError, ValueError):
        return None
    return min(seconds, maximum) if math.isfinite(seconds) and seconds >= 0 else None


def safe_error_details(error: Exception) -> str:
    error_type = getattr(error, "provider_error_type", type(error).__name__)
    category = getattr(error, "category", classify_provider_failure(error))
    status = getattr(
        error,
        "http_status",
        getattr(error, "status_code", getattr(getattr(error, "response", None), "status_code", None)),
    )
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        status = None
    return f"category={category} type={error_type} http_status={status}"


class ProviderFailure(RuntimeError):
    def __init__(self, stage: str, error: Exception) -> None:
        self.category = classify_provider_failure(error)
        self.provider_error_type = type(error).__name__
        self.http_status = getattr(getattr(error, "response", None), "status_code", None)
        super().__init__(f"stage={stage} category={self.category} {safe_error_details(error)}")
