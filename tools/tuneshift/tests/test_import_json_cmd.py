"""Round-trip + idempotency for import-json restore (BUG-1 backup/restore)."""

import json
from argparse import Namespace

import pytest

from tuneshift.commands.export_cmd import handle_export
from tuneshift.commands.import_json_cmd import handle_import_json
from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture
def db_with_small_playlist(tmp_path):
    db = Database(tmp_path / "test.db")
    pid = db.create_playlist("Beg For You")
    for i, (title, artist) in enumerate(
        [("Beg For You", "Charli XCX"), ("Boom Clap", "Charli XCX"), ("1999", "Troye Sivan")]
    ):
        tid = db.add_track(Track(title=title, artist=artist, album=None))
        db.add_track_to_playlist(pid, tid, i)
    return db, db.find_playlist_by_name("Beg For You")


def test_export_then_import_json_roundtrip(db_with_small_playlist, tmp_path):
    db, playlist = db_with_small_playlist
    out = tmp_path / "backup.json"
    handle_export(Namespace(playlist=playlist.name, format="json", output=str(out)), db)

    # Simulate loss: delete the playlist (cascade cleans playlist_tracks).
    db.conn.execute("DELETE FROM playlists WHERE id = ?", (playlist.id,))
    db.conn.commit()
    assert db.find_playlist_by_name(playlist.name) is None

    rc = handle_import_json(Namespace(file=str(out), into=None), db)
    assert rc == 0
    restored = db.find_playlist_by_name(playlist.name)
    assert restored is not None
    original = json.loads(out.read_text())
    assert len(db.get_playlist_tracks(restored.id)) == original["track_count"]


def test_import_json_is_idempotent(db_with_small_playlist, tmp_path):
    db, playlist = db_with_small_playlist
    out = tmp_path / "backup.json"
    handle_export(Namespace(playlist=playlist.name, format="json", output=str(out)), db)

    before = len(db.get_playlist_tracks(playlist.id))
    handle_import_json(Namespace(file=str(out), into=None), db)  # into existing
    after = len(db.get_playlist_tracks(playlist.id))
    assert after == before  # no duplicates appended


def test_import_json_into_alternate_name(db_with_small_playlist, tmp_path):
    db, playlist = db_with_small_playlist
    out = tmp_path / "backup.json"
    handle_export(Namespace(playlist=playlist.name, format="json", output=str(out)), db)

    rc = handle_import_json(Namespace(file=str(out), into="Beg For You (restored)"), db)
    assert rc == 0
    restored = db.find_playlist_by_name("Beg For You (restored)")
    assert restored is not None
    assert len(db.get_playlist_tracks(restored.id)) == 3


def test_import_json_missing_file_errors(tmp_path):
    db = Database(tmp_path / "test.db")
    rc = handle_import_json(Namespace(file=str(tmp_path / "nope.json"), into=None), db)
    assert rc == 1
