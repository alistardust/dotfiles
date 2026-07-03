"""Tests for the ``tuneshift review`` command (clustered bulk review)."""
from pathlib import Path
from types import SimpleNamespace

from tuneshift.commands.triage_cmd import handle_triage
from tuneshift.db import Database
from tuneshift.matching import Availability, MatchAudit, ReasonCode
from tuneshift.models import Track


def _add(db: Database, title, artist, playlist_id, availability, reason_code):
    tid = db.add_track(Track(title=title, artist=artist, album="A"))
    position = len(db.get_playlist_track_ids(playlist_id))
    db.add_track_to_playlist(playlist_id, tid, position)
    db.save_match_audit(tid, "tidal", MatchAudit(
        availability=availability, reason_code=reason_code,
    ))
    return tid


def test_review_no_audits(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    rc = handle_triage(SimpleNamespace(playlist=None, platform=None), db)
    assert rc == 0
    assert "No match decisions recorded" in capsys.readouterr().out


def test_review_unknown_playlist(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    rc = handle_triage(SimpleNamespace(playlist="Ghost", platform=None), db)
    assert rc == 1
    assert "Playlist not found" in capsys.readouterr().err


def test_review_all_clean(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    pl = db.create_playlist("Clean")
    _add(db, "Song", "A", pl, Availability.EXACT_AVAILABLE, ReasonCode.MATCHED)
    rc = handle_triage(SimpleNamespace(playlist=None, platform=None), db)
    assert rc == 0
    out = capsys.readouterr().out
    assert "0 of 1 tracks need review" in out
    assert "every track resolved cleanly" in out


def test_review_clusters_and_burden(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    pl = db.create_playlist("Messy")
    _add(db, "S1", "Big Freedia", pl, Availability.AMBIGUOUS, ReasonCode.AMBIGUOUS_TOP)
    _add(db, "S2", "Big Freedia", pl, Availability.AMBIGUOUS, ReasonCode.AMBIGUOUS_TOP)
    _add(db, "S3", "Someone", pl, Availability.NOT_FOUND, ReasonCode.NO_CANDIDATES)
    _add(db, "S4", "Clean Artist", pl, Availability.EXACT_AVAILABLE, ReasonCode.MATCHED)

    rc = handle_triage(SimpleNamespace(playlist="Messy", platform=None), db)
    assert rc == 0
    out = capsys.readouterr().out
    assert "3 of 4 tracks need review" in out
    assert "ambiguous: 2" in out
    assert "hard-fail: 1" in out
    # Largest cluster (Big Freedia ×2) is listed first.
    freedia_idx = out.index("Big Freedia")
    someone_idx = out.index("Someone")
    assert freedia_idx < someone_idx
