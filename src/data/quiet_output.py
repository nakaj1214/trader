"""Silence third-party output, using only the standard library.

Kept apart from ``provider_output`` (which needs ``requests``) so the failure notifier can import it on a runner
that has no third-party packages installed.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
from collections.abc import Iterator


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
