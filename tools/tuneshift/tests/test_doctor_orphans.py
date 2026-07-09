"""Doctor surfaces orphaned tracks: no mapping, no queue, not quarantined (FEAT-3)."""

import pytest

from tuneshift.db import Database
from tuneshift.doctor.scanner import detect_orphaned
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def test_detect_orphaned_finds_unmapped_unqueued_untriaged(db):
    # A freshly inserted track has NULL tier, NULL quarantine, no queue row, and
    # no platform mapping: it is orphaned.
    orphan = db.insert_track(Track(title="Supernova", artist="Tinashe"))
    assert orphan in {t.id for t in detect_orphaned(db)}


def test_detect_orphaned_excludes_queued_track(db):
    queued = db.insert_track(Track(title="Need You Tonight", artist="Lauren Jauregui"))
    db.enqueue_resolution(queued)
    assert queued not in {t.id for t in detect_orphaned(db)}


def test_detect_orphaned_excludes_resolved_track(db):
    resolved = db.insert_track(Track(title="Blinding Lights", artist="The Weeknd"))
    db.hydrate_identity_metadata(resolved, confidence_tier="CONFIRMED", confidence_score=0.85)
    assert resolved not in {t.id for t in detect_orphaned(db)}
