"""Primary-database identity against the REAL repository layout.

These tests deliberately use the actual checkout rather than ``tmp_path``.
The defect they exist to catch is invisible to a temp-directory fixture: the
original guard derived the primary path from ``__file__`` arithmetic, and in a
temp fixture both sides of the comparison are synthetic and agree with each
other. Only the real layout exposes the disagreement.

Measured before the fix, in this worktree:

    guard thought primary was  .../tools/tuneshift/tuneshift/tuneshift.db
      exists: False
    real git-tracked database  .../tools/tuneshift/tuneshift.db
      exists: True, 22429696 bytes
    _is_primary_db(real) -> False

So the guard refused the one database it was meant to permit, which trains
users to keep ``--allow-nonprimary-push`` switched on, which is exactly when
BUG-24 does its damage.
"""

from pathlib import Path

import pytest

import tuneshift.db as _db
from tuneshift.persistence import primary

# The real database in this checkout, located the same way conftest locates it.
REPO_DB = (Path(_db.__file__).parent.parent / "tuneshift.db").resolve()


@pytest.fixture
def marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the marker file; never touch the user's real registration."""
    path = tmp_path / "primary_db"
    monkeypatch.setattr(primary, "marker_path", lambda: path)
    return path


class TestRealRepositoryLayout:
    def test_the_repo_database_actually_exists(self) -> None:
        """Anchors the other tests: if this moves, they are checking nothing."""
        assert REPO_DB.exists(), f"expected the tracked database at {REPO_DB}"

    def test_the_repo_database_is_classified_primary_once_registered(
        self, marker: Path
    ) -> None:
        """The regression. This failed before the fix and is the whole point."""
        primary.set_primary_db(REPO_DB)
        assert primary.is_primary_db(REPO_DB) is True

    def test_the_inner_package_expression_does_not_find_it(self) -> None:
        """Documents WHY identity is recorded rather than derived.

        The expression that caused the trouble computed from
        ``persistence/base.py`` and stopped one directory short, landing
        inside the package where no library exists in a checkout. Copying
        that arithmetic is what inverted the primary guard.

        Resolution no longer relies on a single expression: it checks both
        layouts and takes whichever is really there. This test keeps the
        cautionary fact anyway, because the inner position must never again
        be treated as the only answer.

        An earlier version also asserted that nothing exists at that path,
        which is a fact about the machine rather than about the code: it held
        in a fresh worktree and failed in a checkout where a stray database
        had been created, so the same commit passed or failed depending on
        which directory it ran in. Detecting a stray on disk is an
        environment check and now lives in ``doctor``.
        """
        from tuneshift.persistence import base

        inner = (Path(base.__file__).parent.parent / "tuneshift.db").resolve()
        assert inner != REPO_DB

    def test_resolution_finds_the_repo_database_in_this_layout(
        self, marker: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bare invocation in this checkout now reaches the real library.

        This is the user-visible change BUG-28 brought: before the fix the
        same invocation resolved to the inner path, created an empty file
        there, and the collection appeared to be gone.

        Asserting against the real repository layout on purpose. The hermetic
        tests in ``test_default_db_path`` prove the rule; this proves the rule
        lands correctly here.
        """
        from tuneshift.persistence.base import get_default_db_path

        monkeypatch.delenv("TUNESHIFT_DB", raising=False)

        assert get_default_db_path().resolve() == REPO_DB


class TestRegistration:
    def test_unregistered_is_not_primary(self, marker: Path) -> None:
        assert primary.get_primary_db() is None
        assert primary.is_primary_db(REPO_DB) is False

    def test_set_then_get_round_trips(self, marker: Path, tmp_path: Path) -> None:
        db_file = tmp_path / "library.db"
        db_file.touch()
        recorded = primary.set_primary_db(db_file)
        assert recorded == db_file.resolve()
        assert primary.get_primary_db() == db_file.resolve()

    def test_marker_is_not_world_readable(self, marker: Path, tmp_path: Path) -> None:
        db_file = tmp_path / "library.db"
        db_file.touch()
        primary.set_primary_db(db_file)
        assert marker.stat().st_mode & 0o077 == 0

    def test_a_copy_is_not_primary(self, marker: Path, tmp_path: Path) -> None:
        """Byte-identical is not good enough; a copy is a different inode."""
        import shutil

        original = tmp_path / "library.db"
        original.write_bytes(b"sqlite stand-in")
        copy = tmp_path / "copy.db"
        shutil.copy(original, copy)

        primary.set_primary_db(original)
        assert primary.is_primary_db(original) is True
        assert primary.is_primary_db(copy) is False

    def test_a_symlink_to_primary_is_primary(
        self, marker: Path, tmp_path: Path
    ) -> None:
        original = tmp_path / "library.db"
        original.touch()
        link = tmp_path / "link.db"
        link.symlink_to(original)

        primary.set_primary_db(original)
        assert primary.is_primary_db(link) is True

    def test_a_relative_path_to_primary_is_primary(
        self, marker: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        original = tmp_path / "library.db"
        original.touch()
        primary.set_primary_db(original)

        monkeypatch.chdir(tmp_path)
        assert primary.is_primary_db(Path("library.db")) is True

    def test_recorded_but_missing_primary_still_matches_itself(
        self, marker: Path, tmp_path: Path
    ) -> None:
        """samefile raises when a side is absent; the fallback must not crash."""
        ghost = tmp_path / "gone.db"
        ghost.touch()
        primary.set_primary_db(ghost)
        ghost.unlink()

        assert primary.is_primary_db(ghost) is True
        assert primary.is_primary_db(tmp_path / "other.db") is False
