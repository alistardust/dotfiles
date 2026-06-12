"""Tests for cascade delete behavior in rm command."""
import pytest

from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture
def db_with_pinned_track(tmp_path):
    """Create DB with a playlist containing a pinned track."""
    db = Database(tmp_path / "test.db")
    track = Track(title="Family Tree (Intro)", artist="Ethel Cain", album="Preacher's Daughter")
    track_id = db.add_track(track)
    playlist_id = db.create_playlist("Test Playlist")
    db.add_track_to_playlist(playlist_id, track_id, position=0)
    db.set_pin(playlist_id, track_id, pin_type="opener")
    return db, playlist_id, track_id


def test_remove_track_from_playlist_cleans_pins(db_with_pinned_track):
    """Removing a track also removes its pins."""
    db, playlist_id, track_id = db_with_pinned_track
    db.remove_track_from_playlist(playlist_id, track_id)

    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 0

    pins = db.get_pins(playlist_id)
    assert len(pins) == 0


def test_remove_track_recompacts_positions(tmp_path):
    """After removal, positions are recompacted (no gaps)."""
    db = Database(tmp_path / "test.db")
    playlist_id = db.create_playlist("Test")
    ids = []
    for i, title in enumerate(["A", "B", "C", "D"]):
        t = Track(title=title, artist="Artist")
        tid = db.add_track(t)
        db.add_track_to_playlist(playlist_id, tid, position=i)
        ids.append(tid)

    db.remove_track_from_playlist(playlist_id, ids[1])

    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 3
    positions = [
        db.conn.execute(
            "SELECT position FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, t.id),
        ).fetchone()[0]
        for t in tracks
    ]
    assert positions == [0, 1, 2]
