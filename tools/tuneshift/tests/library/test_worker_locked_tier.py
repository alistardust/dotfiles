"""A re-resolve must not overwrite the confidence tier of a locked track (BUG-5)."""

import pytest

from tuneshift.db import Database
from tuneshift.library.worker import ResolutionWorker, ResolvedCandidate
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _seed_track(db, *, locked):
    tid = db.insert_track(Track(title="Come On Over Baby", artist="Christina Aguilera"))
    # Start CONFIRMED, as a previously-resolved-and-locked track would be.
    db.hydrate_identity_metadata(tid, confidence_tier="CONFIRMED", confidence_score=0.85)
    db.set_platform_mapping(tid, "tidal", "12270570", user_approved=locked)
    return tid


def _weak_resolver(_track):
    # A deliberately weak candidate that maps to UNCERTAIN if the tier is written.
    return [ResolvedCandidate("tidal", "999", {"match_score": 40})]


def test_resolve_does_not_overwrite_tier_on_locked_track(db):
    tid = _seed_track(db, locked=True)
    worker = ResolutionWorker(db, _weak_resolver)
    worker.resolve_tracks([tid], force=True)
    assert db.get_resolution_state(tid)[0] == "CONFIRMED"  # unchanged


def test_resolve_updates_tier_on_unlocked_track(db):
    tid = _seed_track(db, locked=False)
    worker = ResolutionWorker(db, _weak_resolver)
    worker.resolve_tracks([tid], force=True)
    assert db.get_resolution_state(tid)[0] == "UNCERTAIN"  # recomputed
