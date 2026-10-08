"""Keep third-party output and exception bodies out of public runner logs."""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from collections.abc import Iterator


def safe_error_details(error: Exception) -> str:
    error_type = getattr(error, "provider_error_type", type(error).__name__)
    status = getattr(error, "http_status", getattr(getattr(error, "response", None), "status_code", None))
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        status = None
    return f"type={error_type} http_status={status}"


class ProviderFailure(RuntimeError):
    def __init__(self, stage: str, error: Exception) -> None:
        self.provider_error_type = type(error).__name__
        self.http_status = getattr(getattr(error, "response", None), "status_code", None)
        super().__init__(f"stage={stage} {safe_error_details(error)}")


@contextlib.contextmanager
def suppress_provider_output() -> Iterator[None]:
    """Suppress print and all ordinary loggers only while calling a private provider."""
    previous = logging.root.manager.disable
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        logging.disable(sys.maxsize)
        try:
            yield
        finally:
            logging.disable(previous)
