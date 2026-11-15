"""Shared test setup (testing.md): no test touches the network, and Hypothesis profiles."""

from __future__ import annotations

import os
import socket
from typing import Any

import pytest
from hypothesis import settings

settings.register_profile("dev", max_examples=50)
settings.register_profile("ci", max_examples=300, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


class NetworkBlockedError(RuntimeError):
    """A test tried to open a connection or resolve a name."""


def _blocked(*args: object, **kwargs: object) -> None:
    raise NetworkBlockedError("tests never touch the network (testing.md)")


_REAL_CONNECT = socket.socket.connect
_REAL_SOCKETPAIR = socket.socketpair


def _local_socketpair(*args: Any, **kwargs: Any) -> tuple[socket.socket, socket.socket]:
    """`socket.socketpair` with the real `connect`, so asyncio's event loop can start.

    Windows has no native socketpair: Python emulates it with a loopback connect, and every asyncio loop opens one
    for its self-pipe. The pair never leaves the machine, so it is the one connect the guard lets through.
    """
    blocked = socket.socket.connect
    socket.socket.connect = _REAL_CONNECT  # type: ignore[method-assign]
    try:
        return _REAL_SOCKETPAIR(*args, **kwargs)
    finally:
        socket.socket.connect = blocked  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "socketpair", _local_socketpair)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
