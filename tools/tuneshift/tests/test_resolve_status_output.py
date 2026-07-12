"""Rendering of the richer `resolve --status` library report."""

import pytest

from tuneshift.commands.resolve import _print_library_status
from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _resolved(db, title, artist, tier="CONFIRMED"):
    tid = db.insert_track(Track(title=title, artist=artist))
    db.hydrate_identity_metadata(tid, confidence_tier=tier, confidence_score=0.85)
    return tid


def _quarantined(db, title, artist, reason):
    tid = db.insert_track(Track(title=title, artist=artist))
    db.set_track_fields(
        tid, {"quarantine_state": "unresolved", "quarantine_reason": reason}, source="t"
    )
    return tid


def test_headline_uses_total_denominator_and_splits_unresolved(db, capsys):
    pid = db.create_playlist("PL")
    db.add_track_to_playlist(pid, _resolved(db, "A", "X"), 0)
    db.add_track_to_playlist(pid, db.insert_track(Track(title="D", artist="W")), 1)  # unresolved in playlist
    db.insert_track(Track(title="E", artist="V"))  # orphaned unresolved
    _quarantined(db, "C", "Z", "no_candidate: none")

    _print_library_status(db, verbose=False)
    out = capsys.readouterr().out

    # 1 playable / 4 total = 25.0%, denominator is total (does not hide gaps).
    assert "25.0% playable  (1 / 4 total)" in out
    assert "1 quarantined (unavailable on platform)" in out
    assert "2 unresolved  (1 in playlists, 1 orphaned/no-playlist)" in out


def test_quarantine_histogram_and_per_playlist_note(db, capsys):
    # A playlist whose only gap is an unavailable track is "done as it can be".
    done = db.create_playlist("Done-ish")
    db.add_track_to_playlist(done, _resolved(db, "A", "X"), 0)
    db.add_track_to_playlist(done, _quarantined(db, "B", "Y", "no_candidate: none"), 1)
    # A playlist with a genuinely unresolved track -> "run resolve".
    todo = db.create_playlist("Todo")
    db.add_track_to_playlist(todo, _resolved(db, "C", "Z"), 0)
    db.add_track_to_playlist(todo, db.insert_track(Track(title="U", artist="Q")), 1)

    _print_library_status(db, verbose=False)
    out = capsys.readouterr().out

    assert "no_candidate" in out
    assert "[done: 1 unavailable]" in out
    assert "[1 unresolved]" in out


def test_verbose_lists_quarantined_tracks(db, capsys):
    _quarantined(db, "Supernova", "Tinashe", "no_confident_match: best 20 < 50")
    _print_library_status(db, verbose=True)
    out = capsys.readouterr().out
    assert "Quarantined tracks:" in out
    assert "Supernova - Tinashe" in out
    assert "no_confident_match" in out
