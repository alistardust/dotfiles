"""Preferences command: manage DB-backed version preferences.

Preferences cascade global < playlist < track and are read by the
reconciliation scorer (see :mod:`tuneshift.matching.preferences`). This command
is the user-facing control surface for that cascade: it writes to the same DB
layers the matcher reads, so a configured preference actually takes effect on
the next sync/add/doctor run.

Grammar::

    tuneshift prefs show  [--global | --playlist NAME | --track ID]
    tuneshift prefs set KEY VALUE [--global | --playlist NAME | --track ID]
    tuneshift prefs clear [--global | --playlist NAME | --track ID]

Keys are dotted ``version.<field>``:

* ``version.prefer`` / ``version.avoid`` -- comma-separated keyword lists
  (recording classes: live/remix/acoustic/karaoke/instrumental/tribute/studio;
  lyric axis: explicit/clean; editions: radio/single/expanded/anniversary/
  deluxe/compilation).
* ``version.tiebreak_order`` -- comma-separated ordering hints.
* ``version.duration_tolerance_percent`` -- float.
* ``version.min_lead`` -- int (wider lead required before a pick is confident).
"""
from __future__ import annotations

from collections.abc import Callable

from tuneshift.db import Database
from tuneshift.matching.preferences import Preferences, resolve_preferences

_LIST_KEYS = {"prefer", "avoid", "tiebreak_order"}
_FLOAT_KEYS = {"duration_tolerance_percent"}
_INT_KEYS = {"min_lead"}
_VALID_KEYS = _LIST_KEYS | _FLOAT_KEYS | _INT_KEYS


def _parse_value(key: str, raw: str):
    """Parse a raw CLI value into the stored type for ``key``."""
    if key in _LIST_KEYS:
        return [t.strip().lower() for t in raw.split(",") if t.strip()]
    if key in _FLOAT_KEYS:
        return float(raw)
    return int(raw)


def _resolve_scope(
    args, db: Database
) -> tuple[str, Callable[[], dict | None], Callable[[dict | None], None], str] | None:
    """Resolve the selected preference layer.

    Returns ``(label, getter, setter, layer)`` where ``layer`` is one of
    ``global``/``playlist``/``track`` (used to slot the stored dict into the
    right cascade position for effective resolution). Returns ``None`` after
    printing an error when the target playlist/track does not exist.
    """
    playlist = getattr(args, "playlist", None)
    track = getattr(args, "track", None)
    if playlist is not None:
        matches = [p for p in db.list_playlists() if p.name == playlist]
        if not matches:
            print(f'Playlist "{playlist}" not found.')
            return None
        pid = matches[0].id
        return (
            f'playlist "{playlist}"',
            lambda: db.get_preferences(pid),
            lambda d: db.set_preferences(pid, d),
            "playlist",
        )
    if track is not None:
        if db.get_track(track) is None:
            print(f"Track {track} not found.")
            return None
        return (
            f"track {track}",
            lambda: db.get_track_preferences(track),
            lambda d: db.set_track_preferences(track, d),
            "track",
        )
    return (
        "global",
        db.get_global_preferences,
        db.set_global_preferences,
        "global",
    )


def _print_preferences(prefs: Preferences) -> None:
    print(f"    prefer                      = {', '.join(prefs.prefer) or '(none)'}")
    print(f"    avoid                       = {', '.join(prefs.avoid) or '(none)'}")
    print(f"    duration_tolerance_percent  = {prefs.duration_tolerance_percent}")
    print(f"    tiebreak_order              = {', '.join(prefs.tiebreak_order) or '(none)'}")
    print(f"    min_lead                    = {prefs.min_lead}")


def _effective(db: Database, stored: dict | None, layer: str) -> Preferences:
    """Cascade-resolve the effective prefs for the selected layer.

    Global always applies; a playlist/track layer stacks its own stored dict on
    top of global so ``show`` reflects what the scorer will actually use.
    """
    global_prefs = db.get_global_preferences()
    if layer == "global":
        return resolve_preferences(stored, None, None)
    if layer == "playlist":
        return resolve_preferences(global_prefs, stored, None)
    return resolve_preferences(global_prefs, None, stored)


def handle_prefs(args, db: Database) -> int:
    """Show, set or clear DB-backed version preferences."""
    resolved = _resolve_scope(args, db)
    if resolved is None:
        return 1
    label, getter, setter, layer = resolved

    if args.action == "show":
        stored = getter()
        print(f"Stored preferences ({label}):")
        if stored:
            for key in ("prefer", "avoid", "tiebreak_order", "duration_tolerance_percent", "min_lead"):
                if key in stored:
                    val = stored[key]
                    shown = ", ".join(val) if isinstance(val, list) else val
                    print(f"    {key} = {shown}")
        else:
            print("    (none set)")
        print(f"\nEffective preferences ({label}, cascade-resolved):")
        _print_preferences(_effective(db, stored, layer))
        return 0

    if args.action == "clear":
        setter(None)
        print(f"Cleared preferences ({label}).")
        return 0

    if args.action == "set":
        if not args.key or args.value is None:
            print("Usage: prefs set version.<field> <value>")
            return 1
        parts = args.key.split(".", 1)
        if len(parts) != 2 or parts[0] != "version":
            print(f'Key must be "version.<field>": {args.key}')
            return 1
        field = parts[1]
        if field not in _VALID_KEYS:
            print(f'Unknown field "{field}". Valid: {sorted(_VALID_KEYS)}')
            return 1
        try:
            value = _parse_value(field, args.value)
        except ValueError:
            print(f'Invalid value for {args.key}: "{args.value}"')
            return 1
        stored = getter() or {}
        stored[field] = value
        setter(stored)
        shown = ", ".join(value) if isinstance(value, list) else value
        print(f"Set {args.key} = {shown} ({label}).")
        return 0

    print(f"Unknown action: {args.action}")
    return 1
