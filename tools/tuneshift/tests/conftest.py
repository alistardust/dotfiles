"""Shared test fixtures for tuneshift."""

from collections.abc import Iterator
from pathlib import Path

import pytest

import tuneshift.db as _db

# The committed production database that no test may ever open.
_TRACKED_DB = (Path(_db.__file__).parent.parent / "tuneshift.db").resolve()


@pytest.fixture(scope="session", autouse=True)
def _guard_production_db(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Prevent any test from opening the committed production ``tuneshift.db``.

    Three layers of protection:

    1. Point the default DB path (``TUNESHIFT_DB``) at a session-scoped temp file
       so a bare ``Database()`` never resolves the tracked artifact.
    2. Wrap ``Database.__init__`` to fail loudly if any code still resolves the
       tracked path (belt-and-suspenders against an explicit path argument).
    3. Repoint the primary-database marker at a temp file so no test can read
       or overwrite the real registration.
    """
    mp = pytest.MonkeyPatch()
    session_db = tmp_path_factory.mktemp("tuneshift-db") / "session.db"
    mp.setenv("TUNESHIFT_DB", str(session_db))

    original_init = _db.Database.__init__

    def guarded_init(self: _db.Database, db_path: Path | None = None) -> None:
        if db_path is not None:
            resolved = Path(db_path).resolve()
        else:
            resolved = _db.get_default_db_path().resolve()
        if resolved == _TRACKED_DB:
            raise RuntimeError(
                "Test attempted to open the committed production database at "
                f"{_TRACKED_DB}. Use the tmp_db fixture or an explicit temp path."
            )
        original_init(self, db_path)

    mp.setattr(_db.Database, "__init__", guarded_init)

    # 3. Point the primary-database marker at a temp file so no test can read
    #    or overwrite the real one in ~/.local/share/tuneshift/. Without this a
    #    test that registers a primary would silently repoint the user's own
    #    installation at a temp path that no longer exists.
    import tuneshift.persistence.primary as _primary

    session_marker = session_db.parent / "primary_db"
    mp.setattr(_primary, "marker_path", lambda: session_marker)

    try:
        yield
    finally:
        mp.undo()


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Provide a temporary DB path for tests."""
    return tmp_path / "test.db"
