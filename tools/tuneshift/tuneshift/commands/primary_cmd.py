"""Primary command: show or set which database is the real library.

The primary database is the one that may push to live platforms. See
``tuneshift.persistence.primary`` for why identity is recorded rather than
derived.
"""

import argparse
import sys
from pathlib import Path

from tuneshift.db import Database


def handle_primary(args: argparse.Namespace, db: Database | None) -> int:
    """Show the registered primary database, or set it.

    ``db`` is None when no database could be resolved. That is not an error
    here: registering a primary is the remedy for an unresolvable database, so
    it is the one command that has to work without one.
    """
    active = Path(db.path).resolve() if db is not None else None
    return _run_primary(args, active)


def _run_primary(args: argparse.Namespace, active: Path | None) -> int:
    from tuneshift.persistence.base import is_sqlite_database
    from tuneshift.persistence.primary import (
        get_primary_db,
        is_primary_db,
        marker_path,
        set_primary_db,
    )

    target = getattr(args, "set", None)
    if target:
        path = Path(target).expanduser()
        if not path.is_file():
            if path.is_dir():
                print(f"Not a file: {path}", file=sys.stderr)
            else:
                print(f"No such database: {path}", file=sys.stderr)
            return 1
        # Registration grants the authority to push to a live platform, so the
        # thing being registered has to be a library and not merely a path that
        # exists. An empty file here would hand that authority to a stray.
        if not is_sqlite_database(path):
            print(f"Not a database: {path}", file=sys.stderr)
            print(
                "  Create one first with: tuneshift --db <path> list",
                file=sys.stderr,
            )
            return 1
        try:
            resolved = set_primary_db(path)
        except OSError as exc:
            # The marker lives under the user's data directory, which a
            # command that exists to repair a broken environment cannot
            # assume is writable.
            print(f"Cannot record the primary database: {exc}", file=sys.stderr)
            print(f"  Marker path: {marker_path()}", file=sys.stderr)
            return 1
        print(f"Primary database set to: {resolved}")
        print(f"  recorded in {marker_path()}")
        return 0
    current = get_primary_db()
    if current is None:
        print("No primary database registered.")
        print("  Set one with: tuneshift primary --set <path>")
        if active is not None:
            print(f"  Active database: {active}")
        return 0

    print(f"Primary database: {current}")
    if not current.exists():
        print("  WARNING: that path does not exist.", file=sys.stderr)
    if active is None:
        print("Active database:  (none resolved)")
        return 0
    print(f"Active database:  {active}")
    print(f"  active is primary: {is_primary_db(active)}")
    return 0
