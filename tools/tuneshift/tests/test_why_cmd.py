"""Tests for the ``tuneshift why`` command (match-decision explainer)."""
from pathlib import Path
from types import SimpleNamespace

from tuneshift.commands.why_cmd import handle_why
from tuneshift.db import Database
from tuneshift.matching import Availability, MatchAudit, ReasonCode, RejectedCandidate
from tuneshift.models import Track


def _track(db: Database) -> int:
    return db.add_track(Track(title="Heroes", artist="David Bowie", album="Heroes"))


def test_why_unknown_track_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    rc = handle_why(SimpleNamespace(track_id=999, platform=None, live=False), db)
    assert rc == 1
    assert "No track with id 999" in capsys.readouterr().err


def test_why_no_stored_decision_guides_user(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    track_id = _track(db)
    rc = handle_why(SimpleNamespace(track_id=track_id, platform=None, live=False), db)
    assert rc == 1
    out = capsys.readouterr().out
    assert "No stored match decision" in out
    assert "--live" in out


def test_why_prints_stored_match(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    track_id = _track(db)
    db.save_match_audit(track_id, "spotify", MatchAudit(
        availability=Availability.EXACT_AVAILABLE,
        reason_code=ReasonCode.MATCHED,
        chosen_platform_id="sp1", chosen_score=98, decisive_signal="title:exact",
        distance=0.02,
        rejected=[RejectedCandidate(
            platform_id="sp2", title="Heroes (Live)", artist="David Bowie",
            album="Live", score=30, decisive_signal="version:reject")],
    ))
    rc = handle_why(SimpleNamespace(track_id=track_id, platform=None, live=False), db)
    assert rc == 0
    out = capsys.readouterr().out
    assert "spotify: exact version available" in out
    assert "chosen: sp1 (score 98, distance 0.02)" in out
    assert "decisive signal: title:exact" in out
    assert "Heroes (Live)" in out
    assert "version:reject" in out


def test_why_platform_filter(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    track_id = _track(db)
    db.save_match_audit(track_id, "spotify", MatchAudit(
        availability=Availability.EXACT_AVAILABLE, reason_code=ReasonCode.MATCHED))
    db.save_match_audit(track_id, "tidal", MatchAudit(
        availability=Availability.NOT_FOUND, reason_code=ReasonCode.NO_CANDIDATES))
    rc = handle_why(SimpleNamespace(track_id=track_id, platform="tidal", live=False), db)
    assert rc == 0
    out = capsys.readouterr().out
    assert "tidal: not found" in out
    assert "spotify" not in out


def test_why_explains_blocked_not_missing(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    track_id = _track(db)
    db.save_match_audit(track_id, "tidal", MatchAudit(
        availability=Availability.EXACT_UNAVAILABLE,
        reason_code=ReasonCode.BLOCKED_IN_MARKET, chosen_platform_id="td9"))
    handle_why(SimpleNamespace(track_id=track_id, platform="tidal", live=False), db)
    out = capsys.readouterr().out
    assert "exact version found but not playable" in out
    assert "blocked in this market" in out


def test_why_live_reconciles_and_persists(tmp_db: Path, capsys, monkeypatch) -> None:
    from unittest.mock import MagicMock

    from tuneshift.reconcile import ReconcileResult

    db = Database(tmp_db)
    track_id = _track(db)

    client = MagicMock()
    client.load_session.return_value = True
    fresh = MatchAudit(
        availability=Availability.EXACT_AVAILABLE, reason_code=ReasonCode.MATCHED,
        chosen_platform_id="sp42", chosen_score=95)

    import tuneshift.commands.ingest_cmd as ingest_cmd
    import tuneshift.reconcile as reconcile_mod
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda p: client if p == "spotify" else None)
    monkeypatch.setattr(
        reconcile_mod, "reconcile_track",
        lambda *a, **k: ReconcileResult(platform_track_id="sp42", audit=fresh),
    )

    rc = handle_why(SimpleNamespace(track_id=track_id, platform="spotify", live=True), db)
    assert rc == 0
    out = capsys.readouterr().out
    assert "chosen: sp42" in out
    # The live decision was persisted for later non-live `why`.
    assert db.get_match_audit(track_id, "spotify").chosen_platform_id == "sp42"


def test_why_live_not_logged_in_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    from unittest.mock import MagicMock

    db = Database(tmp_db)
    track_id = _track(db)
    client = MagicMock()
    client.load_session.return_value = False
    import tuneshift.commands.ingest_cmd as ingest_cmd
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda p: client)

    rc = handle_why(SimpleNamespace(track_id=track_id, platform="tidal", live=True), db)
    assert rc == 1
    assert "not logged in" in capsys.readouterr().err
