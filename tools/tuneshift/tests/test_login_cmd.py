"""Tests for the login command's session-validity handling.

``client.load_session()`` only confirms a token file loads structurally; it does
NOT prove the token is still valid. Login must validate before short-circuiting
with "Already authenticated", and fall through to re-auth on an expired session.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import tuneshift.commands.login_cmd as login_cmd


class _ExpiredClient:
    """load_session() succeeds but the session is actually expired."""

    def __init__(self):
        self.login_called = False

    def load_session(self) -> bool:
        return True

    def _ensure_session(self):
        raise RuntimeError("Not logged in")

    def login(self) -> bool:  # single-step (ytmusic-style)
        self.login_called = True
        return True


class _ValidClient:
    def load_session(self) -> bool:
        return True

    def _ensure_session(self):
        return None

    def login(self) -> bool:  # pragma: no cover - should not be called
        raise AssertionError("login() must not be called for a valid session")


@pytest.fixture
def args():
    return SimpleNamespace(platform="ytmusic")


def test_expired_session_falls_through_to_login(monkeypatch, capsys, args):
    client = _ExpiredClient()
    monkeypatch.setattr(login_cmd, "handle_login", login_cmd.handle_login)
    monkeypatch.setattr(
        "tuneshift.commands.ingest_cmd._load_client", lambda name: client
    )
    rc = login_cmd.handle_login(args, MagicMock())
    out = capsys.readouterr().out
    assert "Already authenticated" not in out
    assert client.login_called is True
    assert rc == 0


def test_valid_session_reports_already_authenticated(monkeypatch, capsys, args):
    client = _ValidClient()
    monkeypatch.setattr(
        "tuneshift.commands.ingest_cmd._load_client", lambda name: client
    )
    rc = login_cmd.handle_login(args, MagicMock())
    out = capsys.readouterr().out
    assert "Already authenticated" in out
    assert rc == 0
