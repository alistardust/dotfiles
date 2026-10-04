"""Environment checks for the active database.

Path resolution no longer creates a database at a guessed path (BUG-28), so
the failure this once reported can no longer begin on a fresh machine. What
remains is the wreckage: a checkout that ran the old code may still hold an
empty file at the position an installed wheel would use, inside the package
rather than beside it.

    beside the package   tools/tuneshift/tuneshift.db              the library
    inside the package   tools/tuneshift/tuneshift/tuneshift.db    a stray

That file is inert now, because a library beside the package wins. It is
still worth reporting: it is confusing to find, and it is the residue of a
real data scare.

This is deliberately an environment check and not a test: an earlier attempt
asserted in the test suite that no stray existed on disk, which made the same
commit pass or fail depending on which checkout it ran in.

Nothing here opens the suspect file. Opening a database runs migrations
against it, so probing a stray that way would modify the file being reported.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tuneshift.db import Database


def _layout_positions() -> tuple[Path, Path]:
    """The two positions resolution considers: checkout layout, then wheel.

    Imported from the resolver rather than recomputed. Duplicating this
    arithmetic is what inverted the primary-database guard, and any copy
    drifts the moment either side moves.
    """
    from tuneshift.persistence.base import derived_db_candidates

    beside, inside = derived_db_candidates()
    return beside.resolve(), inside.resolve()


def check_database_environment(
    db: Database, *, positions: tuple[Path, Path] | None = None
) -> list[str]:
    """Return human-readable warnings about which database is in use.

    Empty when nothing looks wrong. Advisory only: callers print these, and
    must not turn them into a failure exit code, because an unusual layout is
    not the same as a broken one.
    """
    warnings: list[str] = []
    active = Path(db.path).resolve()
    beside, inside = positions if positions is not None else _layout_positions()

    from tuneshift.persistence.base import is_sqlite_database

    # Only a checkout has a database beside the package, so its presence is
    # what settles the inner file's status: it cannot be the library a wheel
    # would use. Beside must be a real database for that argument to hold, so
    # an empty file there proves nothing and is left alone.
    if inside.exists() and is_sqlite_database(beside):
        size = inside.stat().st_size
        if inside == active:
            # The worst case, and the one this check used to stay silent on.
            warnings.append(
                f"The active database is the leftover file inside the package: "
                f"{inside} ({size} bytes). A real library sits beside the "
                f"package at {beside}, which is almost certainly the one you "
                f"meant. Point at it with: tuneshift primary --set {beside}"
            )
        else:
            warnings.append(
                f"A leftover database file sits inside the package at {inside} "
                f"({size} bytes). It is not the active database ({active}), and a "
                f"library also exists beside the package at {beside}. Nothing here "
                f"opened it, so confirm it holds nothing you need before deleting it."
            )

    if not db.list_playlists():
        warnings.append(
            f"The active database {active} contains no playlists. "
            f"Check TUNESHIFT_DB if you expected a populated library."
        )

    return warnings
