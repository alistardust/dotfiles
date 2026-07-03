"""Unavailable tracks must not distort sequencing.

Tidal is the availability source of truth. A track that is unavailable there
(genuinely absent, or known-but-blocked) should be pulled out of the energy-arc
optimization and parked at the end of the order — never dropped, and never
allowed to sit between two playable tracks where it would break the flow. A
playlist that has never been reconciled has no audits and must be unaffected.
"""

from pathlib import Path

from tuneshift.db import Database
from tuneshift.matching import Availability, MatchAudit, ReasonCode
from tuneshift.models import Track
from tuneshift.sequencer import sequence_playlist


def _add(db: Database, playlist_id: int, position: int, **track_kw) -> int:
    tid = db.insert_track(Track(**track_kw))
    db.add_track_to_playlist(playlist_id, tid, position=position)
    return tid


def _mark_unavailable(
    db: Database, track_id: int, platform: str, availability: str
) -> None:
    db.save_match_audit(
        track_id,
        platform,
        MatchAudit(availability=availability, reason_code=ReasonCode.NO_CANDIDATES),
    )


class TestGetUnavailableTrackIds:
    def test_returns_not_found_and_blocked_only(self, tmp_db: Path):
        db = Database(tmp_db)
        pl = db.create_playlist("Mixed")
        gone = _add(db, pl, 0, title="Gone", artist="A")
        blocked = _add(db, pl, 1, title="Blocked", artist="B")
        fine = _add(db, pl, 2, title="Fine", artist="C")
        ambiguous = _add(db, pl, 3, title="Maybe", artist="D")

        _mark_unavailable(db, gone, "tidal", Availability.NOT_FOUND)
        _mark_unavailable(db, blocked, "tidal", Availability.EXACT_UNAVAILABLE)
        _mark_unavailable(db, fine, "tidal", Availability.EXACT_AVAILABLE)
        _mark_unavailable(db, ambiguous, "tidal", Availability.AMBIGUOUS)

        got = set(db.get_unavailable_track_ids(pl, "tidal"))
        assert got == {gone, blocked}

    def test_platform_scoped(self, tmp_db: Path):
        db = Database(tmp_db)
        pl = db.create_playlist("PlatformScoped")
        tid = _add(db, pl, 0, title="OnlyGoneOnSpotify", artist="A")
        _mark_unavailable(db, tid, "spotify", Availability.NOT_FOUND)
        # Tidal is source of truth: no Tidal audit => not excluded from Tidal.
        assert db.get_unavailable_track_ids(pl, "tidal") == []
        assert db.get_unavailable_track_ids(pl, "spotify") == [tid]

    def test_no_audits_returns_empty(self, tmp_db: Path):
        db = Database(tmp_db)
        pl = db.create_playlist("Untouched")
        _add(db, pl, 0, title="A", artist="A")
        _add(db, pl, 1, title="B", artist="B")
        assert db.get_unavailable_track_ids(pl, "tidal") == []


class TestSequencerExcludesUnavailable:
    def test_unavailable_track_moved_to_end(self, tmp_db: Path):
        db = Database(tmp_db)
        pl = db.create_playlist("Arc")
        # Energy set so the optimizer has a real arc to build.
        low = _add(db, pl, 0, title="Low", artist="A", energy=0.1, valence=0.2)
        unavail = _add(db, pl, 1, title="Dead", artist="B", energy=0.5, valence=0.5)
        high = _add(db, pl, 2, title="High", artist="C", energy=0.9, valence=0.8)
        mid = _add(db, pl, 3, title="Mid", artist="D", energy=0.5, valence=0.5)

        _mark_unavailable(db, unavail, "tidal", Availability.NOT_FOUND)

        ordered = sequence_playlist(db, pl, arc="wave")

        # Nothing dropped, and the unavailable track is parked last.
        assert set(ordered) == {low, unavail, high, mid}
        assert ordered[-1] == unavail
        # The available tracks occupy the front, unavailable excluded from them.
        assert unavail not in ordered[:-1]

    def test_never_reconciled_playlist_unaffected(self, tmp_db: Path):
        """With no audits, ordering matches the availability-agnostic result."""
        db = Database(tmp_db)
        pl = db.create_playlist("NoAudits")
        ids = [
            _add(db, pl, i, title=f"T{i}", artist=chr(65 + i),
                 energy=0.1 * i, valence=0.1 * i)
            for i in range(4)
        ]
        ordered = sequence_playlist(db, pl, arc="wave")
        assert set(ordered) == set(ids)
        assert len(ordered) == len(ids)

    def test_all_unavailable_preserves_membership(self, tmp_db: Path):
        db = Database(tmp_db)
        pl = db.create_playlist("AllDead")
        ids = [_add(db, pl, i, title=f"T{i}", artist=chr(65 + i)) for i in range(3)]
        for tid in ids:
            _mark_unavailable(db, tid, "tidal", Availability.NOT_FOUND)
        ordered = sequence_playlist(db, pl, arc="wave")
        assert set(ordered) == set(ids)
        assert len(ordered) == len(ids)
