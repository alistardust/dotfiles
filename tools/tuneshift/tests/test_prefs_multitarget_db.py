"""FL3 proof (DB layer): multi-target prefs + folded per-track-global scope.

Locked remediation decisions:
  * A preference is keyed by ``(scope, criterion, target)`` — so two targets on
    the SAME axis (``content avoid karaoke`` and ``content avoid instrumental``)
    coexist instead of the second silently overwriting the first (Alice's bug #2).
  * ``tracks.preferences`` is folded into ``playlist_track_prefs`` using a NULL
    ``playlist_id`` for playlist-agnostic per-track prefs (decision #4). The
    orphan ``tracks.preferences`` column is dropped.
"""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import Database
from tuneshift.models import Track


def _seed(db: Database) -> tuple[int, int]:
    track_id = db.add_track(Track(title="T", artist="A", album="X"))
    playlist_id = db.create_playlist("P")
    db.add_track_to_playlist(playlist_id, track_id, 0)
    return playlist_id, track_id


def test_multiple_targets_same_axis_coexist(tmp_path: Path) -> None:
    db = Database(tmp_path / "mt.db")
    pid, tid = _seed(db)

    db.set_playlist_track_pref(pid, tid, "content", "avoid", "karaoke")
    db.set_playlist_track_pref(pid, tid, "content", "avoid", "instrumental")

    rows = db.get_playlist_track_prefs(pid, tid)
    targets = {r["target"] for r in rows if r["criterion"] == "content"}
    assert targets == {"karaoke", "instrumental"}


def test_same_target_replaces_strength(tmp_path: Path) -> None:
    """Re-setting the same (criterion, target) updates in place (no duplicate)."""
    db = Database(tmp_path / "rep.db")
    pid, tid = _seed(db)

    db.set_playlist_track_pref(pid, tid, "content", "avoid", "karaoke")
    db.set_playlist_track_pref(pid, tid, "content", "forbid", "karaoke")

    rows = [r for r in db.get_playlist_track_prefs(pid, tid)
            if r["criterion"] == "content" and r["target"] == "karaoke"]
    assert len(rows) == 1
    assert rows[0]["strength"] == "forbid"


def test_track_global_scope_null_playlist(tmp_path: Path) -> None:
    """A NULL playlist_id stores a playlist-agnostic per-track preference."""
    db = Database(tmp_path / "tg.db")
    pid, tid = _seed(db)

    db.set_playlist_track_pref(None, tid, "spatial", "prefer", "atmos")

    # Fetched via the global-per-track accessor, NOT under any specific playlist.
    glob = db.get_track_global_prefs(tid)
    assert [(r["criterion"], r["strength"], r["target"]) for r in glob] == [
        ("spatial", "prefer", "atmos")
    ]
    # And it does not leak into a specific playlist's own rows.
    assert db.get_playlist_track_prefs(pid, tid) == []


def test_remove_by_criterion_and_by_target(tmp_path: Path) -> None:
    db = Database(tmp_path / "rm.db")
    pid, tid = _seed(db)
    db.set_playlist_track_pref(pid, tid, "content", "avoid", "karaoke")
    db.set_playlist_track_pref(pid, tid, "content", "avoid", "instrumental")

    # Remove one specific target: the other survives.
    assert db.remove_playlist_track_pref(pid, tid, "content", "karaoke") is True
    remaining = {r["target"] for r in db.get_playlist_track_prefs(pid, tid)}
    assert remaining == {"instrumental"}

    # Remove all remaining targets for the criterion (target omitted).
    assert db.remove_playlist_track_pref(pid, tid, "content") is True
    assert db.get_playlist_track_prefs(pid, tid) == []


def test_tracks_preferences_column_dropped(tmp_path: Path) -> None:
    """The orphan per-track blob column is gone after migration (decision #4)."""
    db = Database(tmp_path / "drop.db")
    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(tracks)")}
    assert "preferences" not in cols
