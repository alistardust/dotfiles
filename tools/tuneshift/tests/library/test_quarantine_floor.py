"""Below-floor resolves quarantine instead of getting a misleading tier (BUG-3)."""

import pytest

from tuneshift.db import Database
from tuneshift.library.worker import ResolutionWorker, ResolvedCandidate
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _track(db):
    return db.insert_track(Track(title="Supernova", artist="Tinashe"))


def test_below_floor_best_candidate_quarantines(db):
    tid = _track(db)

    def resolver(_t):
        return [ResolvedCandidate("tidal", "1", {"match_score": 20})]

    ResolutionWorker(db, resolver).resolve_tracks([tid], force=True)

    assert db.get_resolution_queue_state(tid) == "quarantined"
    assert db.get_resolution_state(tid)[0] is None


def test_at_or_above_floor_resolves(db):
    tid = _track(db)

    def resolver(_t):
        return [ResolvedCandidate("tidal", "1", {"match_score": 85})]

    ResolutionWorker(db, resolver).resolve_tracks([tid], force=True)

    assert db.get_resolution_queue_state(tid) == "resolved"
    assert db.get_resolution_state(tid)[0] == "CONFIRMED"
