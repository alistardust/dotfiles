"""Tests for the tuneshift sequencer."""

from pathlib import Path

from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.sequencer import sequence_playlist
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.scoring import score_pair


def test_sequence_playlist_handles_missing_energy_and_valence(tmp_db: Path) -> None:
    """Sequencing works when tracks have not been classified yet."""
    db = Database(tmp_db)
    track_ids = [
        db.insert_track(Track(title="Long", artist="A", duration_seconds=400)),
        db.insert_track(Track(title="Near", artist="B", duration_seconds=205)),
        db.insert_track(Track(title="Short", artist="C", duration_seconds=200)),
    ]

    ordered = sequence_playlist(db, track_ids, arc="wave")

    assert set(ordered) == set(track_ids)
    assert len(ordered) == len(track_ids)


def test_score_pair_falls_back_to_duration_similarity() -> None:
    """Duration is used when richer sequencing data is absent."""
    short_a = TrackMetadata(track_id=1, title="A", artist="A", duration_ms=180000)
    short_b = TrackMetadata(track_id=2, title="B", artist="B", duration_ms=182000)
    long_track = TrackMetadata(track_id=3, title="C", artist="C", duration_ms=360000)

    weights = {
        "themes": 0.35,
        "energy": 0.22,
        "instrumentation": 0.18,
        "bpm": 0.12,
        "mode": 0.08,
        "key": 0.05,
    }

    assert score_pair(short_a, short_b, weights) > score_pair(short_a, long_track, weights)
