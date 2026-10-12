"""Tests may only use explicit fakes/mocks: any real outbound connection attempt fails and is counted."""

from __future__ import annotations

import socket

import pytest

BLOCKED_NETWORK_ATTEMPTS: list[str] = []
_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _blocked(*args: object, **kwargs: object) -> None:
    BLOCKED_NETWORK_ATTEMPTS.append("outbound-connection")
    raise RuntimeError("real network access is forbidden in tests; use an explicit fake")


@pytest.fixture(autouse=True)
def _forbid_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    real_connect = socket.socket.connect

    def guarded_connect(sock: socket.socket, address: object, *args: object, **kwargs: object) -> object:
        host = address[0] if isinstance(address, tuple) else None
        if host in _LOCAL_HOSTS or sock.family == socket.AF_UNIX:
            return real_connect(sock, address, *args, **kwargs)
        return _blocked()

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    terminalreporter.write_line(f"outbound network attempts blocked: {len(BLOCKED_NETWORK_ATTEMPTS)}")
