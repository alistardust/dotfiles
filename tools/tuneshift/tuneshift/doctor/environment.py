"""Environment checks for the active database.

BUG-28. ``get_default_db_path()`` derives its path from
``persistence/base.py``, one directory below the package root, so in a source
checkout it resolves beside the package instead of above it:

    derived   tools/tuneshift/tuneshift/tuneshift.db
    real      tools/tuneshift/tuneshift.db

Nothing fails when that happens. SQLite creates the file on demand, so a bare
invocation with no ``TUNESHIFT_DB`` set opens an empty database and the
collection simply appears to be gone.

This check reports that situation rather than fixing it, because the fix is a
change to path resolution with a far wider blast radius than a warning. It is
deliberately an environment check and not a test: an earlier attempt asserted
in the test suite that no stray existed on disk, which made the same commit
pass or fail depending on which checkout it ran in.

Nothing here opens the suspect file. Opening a database runs migrations
against it, so probing a stray that way would modify the file being reported.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tuneshift.db import Database


def _derived_default() -> Path:
    """The path a bare invocation resolves, ignoring ``TUNESHIFT_DB``.

    Computed from the package layout rather than read from the environment: a
    deliberate override is not the mix-up this check looks for, and treating
    it as one would warn on every intentional use.
    """
    from tuneshift.persistence import base

    return (Path(base.__file__).parent.parent / "tuneshift.db").resolve()


def check_database_environment(
    db: Database, *, derived: Path | None = None
) -> list[str]:
    """Return human-readable warnings about which database is in use.

    Empty when nothing looks wrong. Advisory only: callers print these, and
    must not turn them into a failure exit code, because an unusual layout is
    not the same as a broken one.
    """
    warnings: list[str] = []
    active = Path(db.path).resolve()
    candidate = (derived if derived is not None else _derived_default()).resolve()

    if candidate != active and candidate.exists():
        size = candidate.stat().st_size
        warnings.append(
            f"A database file exists at {candidate} ({size} bytes). "
            f"A bare `tuneshift` command with no TUNESHIFT_DB set opens that "
            f"file, not {active}. If your collection looks empty, this is why."
        )

    if not db.list_playlists():
        warnings.append(
            f"The active database {active} contains no playlists. "
            f"Check TUNESHIFT_DB if you expected a populated library."
        )

    return warnings
