"""Aggregate helpers for richer resolve --status reporting."""

import pytest

from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _resolved(db, title, artist, tier="CONFIRMED", score=0.85):
    tid = db.insert_track(Track(title=title, artist=artist))
    db.hydrate_identity_metadata(tid, confidence_tier=tier, confidence_score=score)
    return tid


def _quarantined(db, title, artist, reason):
    tid = db.insert_track(Track(title=title, artist=artist))
    db.set_track_fields(tid, {"quarantine_state": "unresolved", "quarantine_reason": reason}, source="test")
    return tid


def _unresolved(db, title, artist):
    return db.insert_track(Track(title=title, artist=artist))


def test_status_summary_partition_sums_to_total(db):
    p1 = _resolved(db, "A", "X", tier="VERIFIED", score=0.97)
    _resolved(db, "B", "Y", tier="CONFIRMED", score=0.85)
    _quarantined(db, "C", "Z", "no_candidate: no platform match found")
    u_in = _unresolved(db, "D", "W")  # will be in a playlist
    _unresolved(db, "E", "V")         # orphaned (no playlist)

    pid = db.create_playlist("PL")
    db.add_track_to_playlist(pid, p1, 0)
    db.add_track_to_playlist(pid, u_in, 1)

    s = db.resolution_status_summary()
    assert s["total"] == 5
    assert s["playable"] == 2
    assert s["quarantined"] == 1
    assert s["unresolved_in_playlist"] == 1
    assert s["unresolved_orphaned"] == 1
    # Partition must sum to total.
    assert (
        s["playable"] + s["quarantined"]
        + s["unresolved_in_playlist"] + s["unresolved_orphaned"]
    ) == s["total"]
    assert s["tiers"] == {"VERIFIED": 1, "CONFIRMED": 1}
    assert s["playable_pct"] == pytest.approx(2 / 5)


def test_status_summary_quarantine_histogram_buckets_by_prefix(db):
    _quarantined(db, "A", "X", "no_confident_match: best score 20 < 50")
    _quarantined(db, "B", "Y", "no_confident_match: best score 30 < 50")
    _quarantined(db, "C", "Z", "no_candidate: no platform match found")

    s = db.resolution_status_summary()
    assert s["quarantine_reasons"] == [("no_confident_match", 2), ("no_candidate", 1)]


def test_quarantine_wins_over_stale_tier(db):
    # A track with both a tier and a quarantine_state counts as quarantined only.
    tid = db.insert_track(Track(title="A", artist="X"))
    db.hydrate_identity_metadata(tid, confidence_tier="CONFIRMED", confidence_score=0.85)
    db.set_track_fields(tid, {"quarantine_state": "unresolved", "quarantine_reason": "later"}, source="test")

    s = db.resolution_status_summary()
    assert s["total"] == 1
    assert s["quarantined"] == 1
    assert s["playable"] == 0


def test_per_playlist_coverage_sorted_lowest_first(db):
    good = db.create_playlist("Good")
    poor = db.create_playlist("Poor")
    for i in range(4):
        db.add_track_to_playlist(good, _resolved(db, f"g{i}", "A"), i)
    # Poor: 1 playable, 1 quarantined, 2 unresolved -> 25% playable.
    db.add_track_to_playlist(poor, _resolved(db, "p0", "B"), 0)
    db.add_track_to_playlist(poor, _quarantined(db, "p1", "B", "no_candidate: x"), 1)
    db.add_track_to_playlist(poor, _unresolved(db, "p2", "B"), 2)
    db.add_track_to_playlist(poor, _unresolved(db, "p3", "B"), 3)

    rows = db.per_playlist_coverage()
    assert [r["name"] for r in rows] == ["Poor", "Good"]  # lowest first
    poor_row = rows[0]
    assert poor_row["total"] == 4
    assert poor_row["playable"] == 1
    assert poor_row["quarantined"] == 1
    assert poor_row["unresolved"] == 2
    assert poor_row["pct"] == pytest.approx(0.25)
