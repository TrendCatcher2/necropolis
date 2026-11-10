"""Shared test setup (testing.md): no test touches the network, and Hypothesis profiles."""

from __future__ import annotations

import os
import socket

import pytest
from hypothesis import settings

settings.register_profile("dev", max_examples=50)
settings.register_profile("ci", max_examples=300, deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


class NetworkBlockedError(RuntimeError):
    """A test tried to open a connection or resolve a name."""


def _blocked(*args: object, **kwargs: object) -> None:
    raise NetworkBlockedError("tests never touch the network (testing.md)")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
