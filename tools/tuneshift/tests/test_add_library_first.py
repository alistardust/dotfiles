"""Task 1.7: library-first add/import (spec §4.3, AC-D7 part 1).

`add` and text-import must land the library row and ENQUEUE resolution rather
than performing an inline remote push. Local playlist placement is retained this
chunk (transitional contract); Chunk 4 Task 4.6 routes that placement through
plan/apply.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tuneshift.commands.add_cmd import handle_add
from tuneshift.commands.import_text_cmd import handle_import_text
from tuneshift.db import Database


def _queue_row(db: Database, track_id: int):
    return db.conn.execute(
        "SELECT state FROM resolution_queue WHERE track_id = ?", (track_id,)
    ).fetchone()


def test_add_enqueues_and_does_not_push_remote(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    pid = db.create_playlist("Synced")
    db.link_platform_playlist(pid, "tidal", "tidal-pl-123")

    mock_client = MagicMock()
    mock_client.load_session.return_value = True
    mock_reconcile = MagicMock()

    with patch("tuneshift.commands.ingest_cmd._load_client", return_value=mock_client), \
         patch("tuneshift.reconcile.reconcile_track", mock_reconcile):
        args = SimpleNamespace(
            playlist="Synced", title="Killer Queen", artist="Queen", album=None
        )
        result = handle_add(args, db)

    assert result == 0
    # (a) library row created
    track = db.find_track("Killer Queen", "Queen", None)
    assert track is not None
    # (b) enqueued pending
    row = _queue_row(db, track.id)
    assert row is not None and row["state"] == "pending"
    # (c) NO inline remote push
    mock_client.add_tracks.assert_not_called()
    mock_reconcile.assert_not_called()
    # local placement retained (transitional contract)
    assert len(db.get_playlist_tracks(pid)) == 1


def test_add_existing_track_still_enqueued(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    args = SimpleNamespace(playlist="P", title="Song", artist="A", album=None)
    handle_add(args, db)
    track = db.find_track("Song", "A", None)
    assert _queue_row(db, track.id)["state"] == "pending"


def test_import_text_enqueues_all_no_remote_push(tmp_path: Path) -> None:
    content = (
        "# Imported\n"
        "1. Artist One - Song One\n"
        "2. Artist Two - Song Two\n"
        "3. Artist Three - Song Three\n"
    )
    f = tmp_path / "pl.txt"
    f.write_text(content, encoding="utf-8")
    db = Database(tmp_path / "test.db")

    args = SimpleNamespace(file=str(f), name=None, force=False)
    result = handle_import_text(args, db)
    assert result == 0

    pl = db.find_playlist_by_name("Imported")
    assert pl is not None
    tracks = db.get_playlist_tracks(pl.id)
    assert len(tracks) == 3
    # all N enqueued pending
    pending = db.conn.execute(
        "SELECT COUNT(*) c FROM resolution_queue WHERE state='pending'"
    ).fetchone()["c"]
    assert pending == 3
