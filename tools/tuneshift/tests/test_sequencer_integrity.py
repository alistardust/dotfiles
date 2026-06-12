"""Tests for sequencer data integrity guarantees."""
import pytest

from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.sequencer import sequence_playlist


@pytest.fixture
def db_with_playlist(tmp_path):
    """Create DB with a 5-track playlist, one without energy metadata."""
    db = Database(tmp_path / "test.db")
    playlist_id = db.create_playlist("Test")
    track_ids = []
    for i, (title, energy) in enumerate([
        ("Track A", 0.8),
        ("Track B", 0.5),
        ("Track C", None),
        ("Track D", 0.3),
        ("Track E", 0.9),
    ]):
        t = Track(title=title, artist="Artist", energy=energy, valence=0.5)
        tid = db.add_track(t)
        db.add_track_to_playlist(playlist_id, tid, position=i)
        track_ids.append(tid)
    return db, playlist_id, track_ids


def test_sequence_playlist_never_drops_tracks(db_with_playlist):
    """All tracks appear in output, including those without metadata."""
    db, playlist_id, track_ids = db_with_playlist
    result = sequence_playlist(db, playlist_id, arc="wave")
    assert set(result) == set(track_ids)
    assert len(result) == 5


def test_sequence_playlist_uses_authoritative_list(db_with_playlist):
    """Sequencer loads from DB, ignoring stale caller state."""
    db, playlist_id, track_ids = db_with_playlist
    db.remove_track_from_playlist(playlist_id, track_ids[2])
    result = sequence_playlist(db, playlist_id, arc="wave")
    assert len(result) == 4
    assert track_ids[2] not in result
