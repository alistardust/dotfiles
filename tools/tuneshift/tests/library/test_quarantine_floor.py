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


def test_below_floor_quarantine_still_persists_candidates(db):
    """BUG-8: a no_confident_match quarantine keeps the discovered candidates so
    triage/explain can show what was found (previously it discarded them)."""
    tid = _track(db)

    def resolver(_t):
        return [
            ResolvedCandidate("tidal", "wrong1", {"match_score": 15}),
            ResolvedCandidate("tidal", "wrong2", {"match_score": 10}),
        ]

    ResolutionWorker(db, resolver).resolve_tracks([tid], force=True)

    assert db.get_resolution_queue_state(tid) == "quarantined"
    persisted = {c["platform_track_id"] for c in db.get_track_candidates(tid, platform="tidal")}
    assert persisted == {"wrong1", "wrong2"}  # not empty -> diagnosable
