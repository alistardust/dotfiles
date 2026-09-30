"""Primary command: show or set which database is the real library.

The primary database is the one that may push to live platforms. See
``tuneshift.persistence.primary`` for why identity is recorded rather than
derived.
"""

import argparse
import sys
from pathlib import Path

from tuneshift.db import Database


def handle_primary(args: argparse.Namespace, db: Database) -> int:
    """Show the registered primary database, or set it."""
    from tuneshift.persistence.primary import (
        get_primary_db,
        is_primary_db,
        marker_path,
        set_primary_db,
    )

    target = getattr(args, "set", None)
    if target:
        path = Path(target).expanduser()
        if not path.exists():
            print(f"No such database: {path}", file=sys.stderr)
            return 1
        resolved = set_primary_db(path)
        print(f"Primary database set to: {resolved}")
        print(f"  recorded in {marker_path()}")
        return 0

    current = get_primary_db()
    if current is None:
        print("No primary database registered.")
        print("  Set one with: tuneshift primary --set <path>")
        print(f"  Active database: {Path(db.path).resolve()}")
        return 0

    print(f"Primary database: {current}")
    if not current.exists():
        print("  WARNING: that path does not exist.", file=sys.stderr)
    active = Path(db.path).resolve()
    print(f"Active database:  {active}")
    print(f"  active is primary: {is_primary_db(active)}")
    return 0
