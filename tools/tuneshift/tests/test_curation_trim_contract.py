"""Trim contract: an exact track target, and pins that trim must not cut.

BUG-22: ``curate trim`` ignored pins entirely and proposed the pinned opener
for removal. A pin is the one explicit instruction the user gives the
sequencer, so trim must treat pinned tracks as protected.

BUG-23: ``--target-tracks N`` kept N+2, because the command injected a
tolerance of 2 and then also inflated the hard limit to N+2. A track-count
target is a precise control and must be exact.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from tuneshift.commands.curate_cmd import handle_curate
from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.curator import CurationConstraintError, curate_trim
from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.sequencer.metadata import get_track_metadata_map

TRACK_COUNT = 15


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "trim.db")
    pid = d.create_playlist("Canyon Test")
    d.set_goal(pid, "Laurel Canyon golden hour")
    for i in range(TRACK_COUNT):
        track = Track(title=f"Track {i}", artist=f"Artist {i % 3}")
        tid = d.add_track(track)
        d.add_track_to_playlist(pid, tid, i)
        d.update_track_metadata(tid, {"energy": i * 0.06, "themes": ["folk"]})
    return d


def _playlist_id(db: Database) -> int:
    return [p for p in db.list_playlists() if p.name == "Canyon Test"][0].id


def _tracks_and_ctx(db: Database):
    pid = _playlist_id(db)
    track_ids = db.get_playlist_track_ids(pid)
    metadata_map = get_track_metadata_map(db, track_ids)
    tracks = [metadata_map[tid] for tid in track_ids if tid in metadata_map]
    ctx = PlaylistContext(
        goal=db.get_goal(pid) or "",
        narrative_sections=[],
        mood_profile=None,
        all_tracks=tracks,
    )
    return pid, tracks, ctx


def _trim_args(**overrides) -> SimpleNamespace:
    base = {
        "playlist": "Canyon Test",
        "mode": "trim",
        "dry_run": False,
        "strategy": "quick",
        "target_tracks": 10,
        "hard_limit": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestTargetTracksIsExact:
    """BUG-23: the count target is a precise control, not an approximation."""

    def test_target_tracks_keeps_exactly_target(self, db: Database) -> None:
        assert handle_curate(_trim_args(target_tracks=10), db) == 0
        assert len(db.get_playlist_track_ids(_playlist_id(db))) == 10

    def test_a_second_target_is_also_exact(self, db: Database) -> None:
        """Guards against a fix that merely shifts the off-by-two."""
        assert handle_curate(_trim_args(target_tracks=7), db) == 0
        assert len(db.get_playlist_track_ids(_playlist_id(db))) == 7

    def test_explicit_hard_limit_still_caps_the_result(self, db: Database) -> None:
        args = _trim_args(target_tracks=12, hard_limit=9)
        assert handle_curate(args, db) == 0
        assert len(db.get_playlist_track_ids(_playlist_id(db))) == 9


class TestPinsAreProtected:
    """BUG-22: a pinned track must never appear in the cut list."""

    def test_engine_never_cuts_a_protected_track(self, db: Database) -> None:
        _pid, tracks, ctx = _tracks_and_ctx(db)
        constraints = {"track_count": {"target": 5, "hard_limit": 5}}

        unprotected = curate_trim(tracks, ctx, constraints)
        assert unprotected.cut, "fixture must produce a cut list to be meaningful"
        victim = unprotected.cut[0].track_id

        protected = curate_trim(
            tracks, ctx, constraints, protected_ids=frozenset({victim})
        )
        assert victim not in {t.track_id for t in protected.cut}
        assert victim in {t.track_id for t in protected.keep}
        assert len(protected.keep) == 5, "protection must not inflate the target"

    def test_pinned_opener_survives_the_command(self, db: Database) -> None:
        pid, tracks, ctx = _tracks_and_ctx(db)
        baseline = curate_trim(tracks, ctx, {"track_count": {"target": 5}})
        victim = baseline.cut[0].track_id

        db.set_pin(pid, victim, "opener")

        assert handle_curate(_trim_args(target_tracks=5), db) == 0
        assert victim in db.get_playlist_track_ids(pid)

    def test_trim_refuses_when_target_is_below_the_pin_count(
        self, db: Database
    ) -> None:
        pid, tracks, ctx = _tracks_and_ctx(db)
        pinned = [t.track_id for t in tracks[:4]]
        for track_id in pinned:
            db.set_pin(pid, track_id, "anchor")

        before = db.get_playlist_track_ids(pid)
        assert handle_curate(_trim_args(target_tracks=2), db) == 1
        assert db.get_playlist_track_ids(pid) == before, "must not apply a partial trim"

    def test_engine_raises_rather_than_cutting_a_pin(self, db: Database) -> None:
        _pid, tracks, ctx = _tracks_and_ctx(db)
        protected = frozenset(t.track_id for t in tracks[:4])
        with pytest.raises(CurationConstraintError):
            curate_trim(
                tracks,
                ctx,
                {"track_count": {"target": 2, "hard_limit": 2}},
                protected_ids=protected,
            )


class TestConstraintPrecedence:
    """A stored constraint is what the user said before; the CLI is now.

    Found while fixing BUG-23: `constraints.update(stored_constraints)` let a
    stored `track_count.target` silently beat an explicit `--target-tracks`.
    The +2 tolerance was the reported symptom, but this was a second, quieter
    route to "the number you asked for is not the number you got".
    """

    def test_cli_target_beats_a_stored_target(self, db: Database) -> None:
        pid, _tracks, _ctx = _tracks_and_ctx(db)
        db.set_constraints(pid, {"track_count": {"target": 12}})

        assert handle_curate(_trim_args(target_tracks=5), db) == 0
        assert len(db.get_playlist_track_ids(pid)) == 5

    def test_stored_hard_limit_survives_a_cli_target(
        self, db: Database, capsys
    ) -> None:
        """The CLI overrides only what it actually set.

        A stored hard_limit is a saved rule for the playlist, so asking for a
        larger target must not silently discard it. It binds, and says so.
        """
        pid, _tracks, _ctx = _tracks_and_ctx(db)
        db.set_constraints(pid, {"track_count": {"target": 12, "hard_limit": 4}})

        assert handle_curate(_trim_args(target_tracks=9), db) == 0
        assert len(db.get_playlist_track_ids(pid)) == 4
        assert "another constraint is binding" in capsys.readouterr().err

    def test_no_spurious_note_when_playlist_is_shorter_than_target(
        self, db: Database, capsys
    ) -> None:
        pid, tracks, _ctx = _tracks_and_ctx(db)
        assert handle_curate(_trim_args(target_tracks=len(tracks) + 5), db) == 0
        assert "another constraint is binding" not in capsys.readouterr().err
