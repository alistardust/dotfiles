"""E2E tests for the routed ``lock`` / ``unlock`` CLI (AC-CLI1, AC-L1/L2/P1).

Exercises the command layer against a real DB: plan-by-default writes a plan and
mutates nothing; ``--apply`` performs the lock in one step; the applied lock is
the effective lock resolved by the matcher; per-playlist overrides win over the
global default; unlock releases while keeping the auto-match.
"""

from __future__ import annotations

from types import SimpleNamespace

from tuneshift.commands.lock_cmd import handle_lock, handle_unlock
from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.planapply.plan import list_plans


def _seed(tmp_path):
    db = Database(tmp_path / "lock.db")
    pid = db.create_playlist("Atmos Sessions")
    tid = db.add_track(Track(title="Beg For You", artist="Charli XCX", album="Crash"))
    db.add_track_to_playlist(pid, tid, 0)
    return db, pid, tid


def _lock_args(**over):
    base = dict(
        playlist=None, title=None, track_id=None,
        tidal=None, ytmusic=None, scope="global",
        apply=False, interactive=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestGlobalLockCLI:
    def test_plan_by_default_writes_plan_and_mutates_nothing(self, tmp_path, capsys):
        db, _pid, tid = _seed(tmp_path)
        rc = handle_lock(_lock_args(track_id=tid, tidal="GID"), db)
        assert rc == 0
        # Nothing applied — no mapping yet, but a plan file exists.
        assert db.get_platform_mapping(tid, "tidal") is None
        assert list_plans(db.path)
        assert "wrote plan" in capsys.readouterr().out

    def test_apply_locks_in_one_step_and_is_effective(self, tmp_path, capsys):
        db, _pid, tid = _seed(tmp_path)
        rc = handle_lock(_lock_args(track_id=tid, tidal="GID", apply=True), db)
        assert rc == 0
        m = db.get_platform_mapping(tid, "tidal")
        assert m is not None and m.platform_track_id == "GID" and m.user_approved
        eff = db.get_effective_lock(tid, "tidal")
        assert eff is not None and eff.scope == "global" and eff.platform_track_id == "GID"
        assert "applied" in capsys.readouterr().out

    def test_lock_by_playlist_title_selector(self, tmp_path):
        db, _pid, tid = _seed(tmp_path)
        rc = handle_lock(
            _lock_args(playlist="Atmos Sessions", title="Beg", tidal="GID", apply=True), db
        )
        assert rc == 0
        assert db.get_platform_mapping(tid, "tidal").platform_track_id == "GID"

    def test_lock_requires_platform_id(self, tmp_path, capsys):
        db, _pid, tid = _seed(tmp_path)
        assert handle_lock(_lock_args(track_id=tid), db) == 1
        assert "Specify --tidal or --ytmusic" in capsys.readouterr().err

    def test_relock_same_id_is_empty_noop(self, tmp_path, capsys):
        db, _pid, tid = _seed(tmp_path)
        handle_lock(_lock_args(track_id=tid, tidal="GID", apply=True), db)
        capsys.readouterr()
        rc = handle_lock(_lock_args(track_id=tid, tidal="GID", apply=True), db)
        assert rc == 0
        assert "nothing to do" in capsys.readouterr().out


class TestPerPlaylistLockCLI:
    def test_playlist_override_wins_over_global(self, tmp_path):
        db, pid, tid = _seed(tmp_path)
        # Global lock to G, per-playlist override to P.
        handle_lock(_lock_args(track_id=tid, tidal="GLOBAL", apply=True), db)
        handle_lock(
            _lock_args(playlist="Atmos Sessions", title="Beg", tidal="OVERRIDE",
                       scope="playlist", apply=True),
            db,
        )
        # Global scope still resolves to the global lock.
        assert db.get_effective_lock(tid, "tidal").platform_track_id == "GLOBAL"
        # Playlist scope resolves to the override.
        eff = db.get_effective_lock(tid, "tidal", playlist_id=pid)
        assert eff.platform_track_id == "OVERRIDE" and eff.scope == "playlist"

    def test_scope_playlist_without_playlist_errors(self, tmp_path, capsys):
        db, _pid, tid = _seed(tmp_path)
        rc = handle_lock(
            _lock_args(track_id=tid, tidal="X", scope="playlist"), db
        )
        assert rc == 1
        assert "requires a playlist" in capsys.readouterr().err


class TestUnlockCLI:
    def test_global_unlock_releases_but_keeps_match(self, tmp_path):
        db, _pid, tid = _seed(tmp_path)
        handle_lock(_lock_args(track_id=tid, tidal="GID", apply=True), db)
        rc = handle_unlock(_lock_args(track_id=tid, tidal=True, apply=True), db)
        assert rc == 0
        m = db.get_platform_mapping(tid, "tidal")
        assert m is not None and m.platform_track_id == "GID"
        assert m.user_approved is False
        assert db.get_effective_lock(tid, "tidal") is None

    def test_playlist_unlock_removes_override_falls_back_to_global(self, tmp_path):
        db, pid, tid = _seed(tmp_path)
        handle_lock(_lock_args(track_id=tid, tidal="GLOBAL", apply=True), db)
        handle_lock(
            _lock_args(playlist="Atmos Sessions", title="Beg", tidal="OVERRIDE",
                       scope="playlist", apply=True),
            db,
        )
        rc = handle_unlock(
            _lock_args(playlist="Atmos Sessions", title="Beg", tidal=True,
                       scope="playlist", apply=True),
            db,
        )
        assert rc == 0
        # Override gone; playlist scope now falls back to the global lock.
        eff = db.get_effective_lock(tid, "tidal", playlist_id=pid)
        assert eff.platform_track_id == "GLOBAL" and eff.scope == "global"

    def test_unlock_when_nothing_locked_is_noop(self, tmp_path, capsys):
        db, _pid, tid = _seed(tmp_path)
        rc = handle_unlock(_lock_args(track_id=tid, tidal=True, apply=True), db)
        assert rc == 0
        assert "nothing to do" in capsys.readouterr().out

    def test_unlock_plan_by_default_does_not_release(self, tmp_path):
        db, _pid, tid = _seed(tmp_path)
        handle_lock(_lock_args(track_id=tid, tidal="GID", apply=True), db)
        rc = handle_unlock(_lock_args(track_id=tid, tidal=True), db)  # no --apply
        assert rc == 0
        # Still locked — a plan was written but not applied.
        assert db.get_platform_mapping(tid, "tidal").user_approved is True
