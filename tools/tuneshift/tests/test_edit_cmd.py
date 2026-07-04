"""Tests for the `tuneshift edit` command (Task 1.5).

Covers direct metadata edits, --strip-album-from-title, validation,
dry-run, normalized-column recomputation, and the edit audit trail.
"""

import argparse
from pathlib import Path

from tuneshift.commands.edit_cmd import handle_edit
from tuneshift.db import Database
from tuneshift.models import Track


def _edit_args(**overrides):
    base = dict(
        track_id=None, playlist=None, title=None, artist=None, album=None,
        strip_album_from_title=False, dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _db(tmp_db: Path) -> Database:
    return Database(tmp_db)


def test_edit_updates_title(tmp_db: Path):
    db = _db(tmp_db)
    tid = db.insert_track(Track(title="Old Title", artist="Artist", album="Album"))

    result = handle_edit(_edit_args(track_id=tid, title="New Title"), db)

    assert result == 0
    assert db.get_track(tid).title == "New Title"


def test_edit_recomputes_norm_columns(tmp_db: Path):
    """After renaming, identity lookup by the new title must succeed."""
    db = _db(tmp_db)
    tid = db.insert_track(Track(title="Wrong Name", artist="Big Freedia", album="3rd Ward Bounce"))

    handle_edit(_edit_args(track_id=tid, title="Louder"), db)

    found = db.find_track("Louder", "Big Freedia", "3rd Ward Bounce")
    assert found is not None
    assert found.id == tid
    # And the stale title no longer resolves.
    assert db.find_track("Wrong Name", "Big Freedia", "3rd Ward Bounce") is None


def test_edit_updates_multiple_fields(tmp_db: Path):
    db = _db(tmp_db)
    tid = db.insert_track(Track(title="T", artist="A", album="Alb"))

    handle_edit(_edit_args(track_id=tid, artist="New Artist", album="New Album"), db)

    track = db.get_track(tid)
    assert track.artist == "New Artist"
    assert track.album == "New Album"


def test_edit_rejects_empty_title(tmp_db: Path, capsys):
    db = _db(tmp_db)
    tid = db.insert_track(Track(title="Keep", artist="A", album=None))

    result = handle_edit(_edit_args(track_id=tid, title="   "), db)

    assert result == 1
    assert db.get_track(tid).title == "Keep"


def test_edit_unknown_id_errors(tmp_db: Path, capsys):
    db = _db(tmp_db)
    result = handle_edit(_edit_args(track_id=999999, title="X"), db)
    assert result == 1
    assert "not found" in capsys.readouterr().err


def test_edit_no_fields_errors(tmp_db: Path, capsys):
    db = _db(tmp_db)
    tid = db.insert_track(Track(title="T", artist="A", album=None))
    result = handle_edit(_edit_args(track_id=tid), db)
    assert result == 1


def test_edit_dry_run_writes_nothing(tmp_db: Path):
    db = _db(tmp_db)
    tid = db.insert_track(Track(title="Original", artist="A", album=None))

    result = handle_edit(_edit_args(track_id=tid, title="Changed", dry_run=True), db)

    assert result == 0
    assert db.get_track(tid).title == "Original"


def test_edit_records_audit_trail(tmp_db: Path):
    db = _db(tmp_db)
    tid = db.insert_track(Track(title="Before", artist="A", album=None))

    handle_edit(_edit_args(track_id=tid, title="After"), db)

    edits = db.get_track_edits(tid)
    assert any(e["field"] == "title" and e["old_value"] == "Before"
               and e["new_value"] == "After" for e in edits)


class TestStripAlbumFromTitle:
    def test_strips_matching_trailing_album(self, tmp_db: Path):
        db = _db(tmp_db)
        tid = db.insert_track(Track(
            title="Femininomenon (The Rise and Fall of a Midwest Princess)",
            artist="Chappell Roan",
            album="The Rise and Fall of a Midwest Princess",
        ))

        result = handle_edit(_edit_args(track_id=tid, strip_album_from_title=True), db)

        assert result == 0
        assert db.get_track(tid).title == "Femininomenon"

    def test_leaves_non_album_parenthetical(self, tmp_db: Path):
        db = _db(tmp_db)
        tid = db.insert_track(Track(
            title="Louder (feat. Icona Pop)",
            artist="Big Freedia",
            album="3rd Ward Bounce",
        ))

        handle_edit(_edit_args(track_id=tid, strip_album_from_title=True), db)

        assert db.get_track(tid).title == "Louder (feat. Icona Pop)"

    def test_playlist_batch_strip(self, tmp_db: Path):
        db = _db(tmp_db)
        pid = db.create_playlist("LM")
        t1 = db.insert_track(Track(title="Song A (My Album)", artist="X", album="My Album"))
        t2 = db.insert_track(Track(title="Song B", artist="Y", album="Other"))
        db.add_track_to_playlist(pid, t1, position=0)
        db.add_track_to_playlist(pid, t2, position=1)

        result = handle_edit(_edit_args(playlist="LM", strip_album_from_title=True), db)

        assert result == 0
        assert db.get_track(t1).title == "Song A"
        assert db.get_track(t2).title == "Song B"

    def test_strip_dry_run_writes_nothing(self, tmp_db: Path):
        db = _db(tmp_db)
        tid = db.insert_track(Track(title="Song (My Album)", artist="X", album="My Album"))

        handle_edit(_edit_args(track_id=tid, strip_album_from_title=True, dry_run=True), db)

        assert db.get_track(tid).title == "Song (My Album)"
