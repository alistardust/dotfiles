# tests/where-were-we/test_session.py
import pytest
import wwm_session


def test_explicit_session_wins(fake_home, monkeypatch):
    monkeypatch.setenv("COPILOT_AGENT_SESSION_ID", "from-env")
    assert wwm_session.resolve_session_id("explicit-id") == "explicit-id"


def test_env_is_the_default(fake_home, monkeypatch):
    monkeypatch.setenv("COPILOT_AGENT_SESSION_ID", "from-env")
    assert wwm_session.resolve_session_id(None) == "from-env"


def test_refuses_when_neither_source_available(fake_home):
    with pytest.raises(wwm_session.SessionUnknown) as err:
        wwm_session.resolve_session_id(None)
    assert "--session" in str(err.value)


def test_ledger_path_is_under_session_state(fake_home):
    path = wwm_session.ledger_path("abc-123")
    assert path.parts[-4:] == ("session-state", "abc-123", "files", "ledger.md")


def test_runtime_gate_is_not_the_store_check(fake_home, monkeypatch):
    """A missing store is a degraded mode, not an unsupported runtime.

    These were the same predicate once, which meant losing the database threw
    away every recorded fact in the ledger at exactly the moment the ledger was
    the only source left.
    """
    monkeypatch.delenv(wwm_session.ENV_SESSION, raising=False)
    (fake_home / ".copilot" / "session-state").mkdir(parents=True)
    assert wwm_session.is_copilot_runtime() is True
    assert wwm_session.has_store() is False


def test_runtime_gate_false_when_nothing_identifies_copilot(fake_home, monkeypatch):
    monkeypatch.delenv(wwm_session.ENV_SESSION, raising=False)
    assert wwm_session.is_copilot_runtime() is False


def test_runtime_gate_true_from_env_alone(fake_home, monkeypatch):
    monkeypatch.setenv(wwm_session.ENV_SESSION, "abc-123")
    assert wwm_session.is_copilot_runtime() is True


def test_has_store_tracks_the_database_only(fake_home):
    store = fake_home / ".copilot" / "session-store.db"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.touch()
    assert wwm_session.has_store() is True
