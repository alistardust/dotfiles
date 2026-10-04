"""Canonical identity of the primary database.

The primary database is the one real library. Everything else, a copy, an
export, a scratch file, is not, and must never receive a push to a live
platform: the platform playlist IDs live inside the database and travel with
a copy, so a push from a copy reaches the same live playlist (BUG-24).

Identity is a RECORDED ABSOLUTE PATH, not path arithmetic. Deriving it from
``__file__`` cannot work, because the correct arithmetic differs by install
layout and the two layouts disagree:

- source/editable checkout: the database sits beside the package, at
  ``tools/tuneshift/tuneshift.db``
- installed wheel: it would sit inside the package, at
  ``site-packages/tuneshift/tuneshift.db``

``get_default_db_path()`` picks the second and is therefore wrong in this
checkout. That is not a theoretical concern: it resolves to a path where no
library exists, so a bare invocation silently creates an empty database there
and the user appears to have lost their collection.

A recorded path survives both layouts, and survives the directory being moved
or renamed, because it is asserted once rather than inferred every time.
"""

from __future__ import annotations

from pathlib import Path


def marker_path() -> Path:
    """Return the file recording the primary database's absolute path.

    Lives beside the platform tokens in ``~/.local/share/tuneshift/``, the
    established home for uncommitted local state, so it is never committed and
    never travels with a copied database. A marker stored *inside* the database
    would be copied along with it and prove nothing.
    """
    return Path.home() / ".local" / "share" / "tuneshift" / "primary_db"


def get_primary_db() -> Path | None:
    """Return the recorded primary database path, or None if unregistered.

    Only an absent marker means unregistered. Any other failure to read it is
    raised, because a guard that cannot read its own registration must refuse
    rather than assume the permissive answer.
    """
    from tuneshift import PrimaryMarkerError

    marker = marker_path()
    try:
        recorded = marker.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PrimaryMarkerError(
            f"Cannot read the primary-database marker at {marker}: {exc}\n"
            "  Fix its permissions, or re-register with:\n"
            "    tuneshift primary --set <path>"
        ) from exc
    return Path(recorded) if recorded else None


def set_primary_db(path: Path) -> Path:
    """Record ``path`` as the primary database. Returns the resolved path."""
    resolved = Path(path).expanduser().resolve()
    marker = marker_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{resolved}\n", encoding="utf-8")
    marker.chmod(0o600)
    return resolved


def is_primary_db(active: Path) -> bool:
    """Whether ``active`` is the recorded primary database.

    Compared by identity on disk via ``samefile``, so a symlink, a hardlink, a
    relative path, or macOS case-insensitivity cannot make the primary look
    foreign. A byte-identical copy is a different inode and is correctly not
    primary.

    Returns False when nothing is registered. Callers must treat that case as
    "unregistered", not as "this is a copy": the remedy is to register the
    primary, never to reach for the push override.
    """
    primary = get_primary_db()
    if primary is None:
        return False
    try:
        return Path(active).samefile(primary)
    except OSError:
        # One side is missing. Fall back to comparing resolved paths so a
        # recorded-but-absent primary still matches an identical path.
        return Path(active).expanduser().resolve() == primary.expanduser().resolve()
