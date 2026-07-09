"""BUG-7: rm/remove-by-position must delete only the chosen copy, not all copies."""

import pytest

from tuneshift.commands.rm_cmd import _remove_and_sync
from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _playlist_with_duplicate(db):
    pid = db.create_playlist("Hot Girl Summer")
    tid = db.add_track(Track(title="ICY GRL", artist="Saweetie", album=None))
    # Same canonical track at two distinct positions (allowed: PK is
    # (playlist_id, position)).
    db.add_track_to_playlist(pid, tid, 0)
    db.add_track_to_playlist(pid, tid, 1)
    return pid, tid


def test_remove_by_position_keeps_other_copy(db):
    pid, tid = _playlist_with_duplicate(db)
    db.remove_playlist_track_by_position(pid, 1)  # remove the second copy
    remaining = [t.id for t in db.get_playlist_tracks(pid)]
    assert remaining == [tid]  # exactly one copy survives, not zero


def test_remove_last_copy_clears_pin(db):
    pid, tid = _playlist_with_duplicate(db)
    db.set_pin(pid, tid, "opener")

    db.remove_playlist_track_by_position(pid, 1)  # one copy remains
    pins = db.conn.execute(
        "SELECT 1 FROM playlist_pins WHERE playlist_id = ? AND track_id = ?", (pid, tid)
    ).fetchall()
    assert pins  # pin kept while a copy remains

    db.remove_playlist_track_by_position(pid, 0)  # last copy gone
    pins = db.conn.execute(
        "SELECT 1 FROM playlist_pins WHERE playlist_id = ? AND track_id = ?", (pid, tid)
    ).fetchall()
    assert not pins  # pin cleared once no copy remains


def test_remove_and_sync_removes_single_copy_no_platform(db):
    # No linked platform: exercises the DB-removal path of the rm command.
    pid, tid = _playlist_with_duplicate(db)
    playlist = db.find_playlist_by_name("Hot Girl Summer")
    tracks = db.get_playlist_tracks(pid)
    # Remove the 2nd ordinal copy.
    had_failure = _remove_and_sync(db, playlist, tracks[1], 2)
    assert had_failure is False
    remaining = [t.id for t in db.get_playlist_tracks(pid)]
    assert remaining == [tid]  # one copy survives
