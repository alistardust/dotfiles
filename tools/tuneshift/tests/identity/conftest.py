"""Shared fixtures for identity tests."""

import pytest

from tuneshift.db import Database


@pytest.fixture
def db(tmp_path):
    """Create a fresh TuneShift database for testing."""
    db_path = tmp_path / "test.db"
    return Database(db_path)


@pytest.fixture
def db_with_track(db):
    """Database with one track inserted."""
    from tuneshift.models import Track

    track = Track(title="Heroes", artist="David Bowie", album="Heroes", isrc="GBAYE7700012", duration_seconds=372)
    track_id = db.add_track(track)
    return db, track_id
