"""Tests for the login command handler.

Covers two concerns:

1. Session-validity handling. ``client.load_session()`` only confirms a token
   file loads structurally; it does NOT prove the token is still valid. Login
   must validate before short-circuiting with "Already authenticated", and fall
   through to re-auth on an expired session.
2. Command-handler orchestration. ``handle_login`` authenticates against a
   streaming platform client. These tests stub the platform client entirely, so
   no network or real OAuth flow occurs. Two client shapes are covered: the
   Tidal-style two-step flow (login returns a URL, login_wait polls) and the
   YT Music-style single-step flow (login returns a bool).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tuneshift.commands import ingest_cmd, login_cmd


# --- Session-validity handling -------------------------------------------------


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


# --- Command-handler orchestration --------------------------------------------


class _TidalStyleClient:
    """Two-step device-auth client: exposes login_wait()."""

    def __init__(self, *, session_loaded=False, wait_result=True):
        self._session_loaded = session_loaded
        self._wait_result = wait_result
        self.login_wait_timeout = None

    def load_session(self):
        return self._session_loaded

    def login(self):
        return "https://link.tidal.com/ABC123"

    def login_wait(self, timeout):
        self.login_wait_timeout = timeout
        return self._wait_result


class _YtMusicStyleClient:
    """Single-step interactive client: no login_wait()."""

    def __init__(self, *, session_loaded=False, login_result=True):
        self._session_loaded = session_loaded
        self._login_result = login_result

    def load_session(self):
        return self._session_loaded

    def login(self):
        return self._login_result


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)


def test_unknown_platform_returns_error(monkeypatch, capsys):
    _patch_client(monkeypatch, None)
    rc = login_cmd.handle_login(SimpleNamespace(platform="bogus"), db=None)
    assert rc == 1
    assert "Unknown platform: bogus" in capsys.readouterr().err


def test_already_authenticated_short_circuits(monkeypatch, capsys):
    _patch_client(monkeypatch, _TidalStyleClient(session_loaded=True))
    rc = login_cmd.handle_login(SimpleNamespace(platform="tidal"), db=None)
    assert rc == 0
    assert "Already authenticated with tidal." in capsys.readouterr().out


def test_tidal_flow_success_prints_url_and_waits(monkeypatch, capsys):
    client = _TidalStyleClient(session_loaded=False, wait_result=True)
    _patch_client(monkeypatch, client)
    rc = login_cmd.handle_login(SimpleNamespace(platform="tidal"), db=None)
    out = capsys.readouterr().out
    assert rc == 0
    assert "https://link.tidal.com/ABC123" in out
    assert "Authenticated with tidal." in out
    assert client.login_wait_timeout == 300.0


def test_tidal_flow_timeout_returns_error(monkeypatch, capsys):
    _patch_client(monkeypatch, _TidalStyleClient(session_loaded=False, wait_result=False))
    rc = login_cmd.handle_login(SimpleNamespace(platform="tidal"), db=None)
    assert rc == 1
    assert "Authentication timed out for tidal." in capsys.readouterr().err


def test_ytmusic_flow_success_returns_zero(monkeypatch, capsys):
    _patch_client(monkeypatch, _YtMusicStyleClient(session_loaded=False, login_result=True))
    rc = login_cmd.handle_login(SimpleNamespace(platform="ytmusic"), db=None)
    assert rc == 0
    assert "Authenticated with ytmusic." in capsys.readouterr().out


def test_ytmusic_flow_failure_returns_error(monkeypatch, capsys):
    _patch_client(monkeypatch, _YtMusicStyleClient(session_loaded=False, login_result=False))
    rc = login_cmd.handle_login(SimpleNamespace(platform="ytmusic"), db=None)
    assert rc == 1
    assert "Authentication failed for ytmusic." in capsys.readouterr().err
