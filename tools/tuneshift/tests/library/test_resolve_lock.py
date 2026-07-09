"""Tests for the single-flight resolve lock (BUG-2 / FEAT-2)."""

import os

import pytest

from tuneshift.library.lock import ResolveLock, ResolveLockHeld


def test_lock_acquires_and_releases(tmp_path):
    lock_dir = tmp_path / ".tuneshift"
    with ResolveLock(tmp_path / "tuneshift.db"):
        assert (lock_dir / "resolve.lock").exists()
    assert not (lock_dir / "resolve.lock").exists()


def test_lock_refuses_when_live_pid_holds_it(tmp_path):
    lock_dir = tmp_path / ".tuneshift"
    lock_dir.mkdir(parents=True)
    # The parent process is live and distinct from this one: simulates another
    # resolve holding the lock.
    (lock_dir / "resolve.lock").write_text(str(os.getppid()), encoding="utf-8")
    with pytest.raises(ResolveLockHeld):
        with ResolveLock(tmp_path / "tuneshift.db"):
            pass


def test_lock_reclaims_stale_pid(tmp_path):
    lock_dir = tmp_path / ".tuneshift"
    lock_dir.mkdir(parents=True)
    # PID 2^31-2 is effectively never live.
    (lock_dir / "resolve.lock").write_text("2147483646", encoding="utf-8")
    with ResolveLock(tmp_path / "tuneshift.db"):
        assert (lock_dir / "resolve.lock").read_text().strip() == str(os.getpid())
