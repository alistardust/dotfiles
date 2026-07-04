"""Preferences command: manage DB-backed version preferences.

This is the user-facing control surface for the general metadata-driven
preference model (AC-CLI1): a preference is ``(criterion, strength, target)``
settable on ANY criterion at three scopes, and the matcher reads exactly what
this command writes, so a configured preference takes effect on the next
sync/add/doctor run.

Typed grammar (the general model)::

    tuneshift prefs set  <criterion> <strength> <target> [--playlist NAME] [--track ID]
    tuneshift prefs unset <criterion>                     [--playlist NAME] [--track ID]
    tuneshift prefs list                                  [--playlist NAME] [--track ID]

* ``criterion`` is an axis: spatial / mix / fidelity (structured audio) or
  performance / content / edit / production (title-derived).
* ``strength`` is one of require / prefer / avoid / forbid. ``require``/``forbid``
  are HARD filters (a candidate is eliminated); ``prefer``/``avoid`` are SOFT.
* ``target`` is a token in any surface form (``atmos`` / ``Dolby Atmos`` /
  ``dolby_atmos``); it is canonicalised against the whitelist.

Scope is chosen by the flags present: none = global, ``--playlist`` = that
playlist, ``--playlist`` + ``--track`` = that track on that playlist
(most-specific). Precedence when resolving a match is global < playlist <
playlist-track.

Legacy grammar (recording-class / lyric / edition soft intent, retained for
backward compatibility)::

    tuneshift prefs set   version.<field> <value> [--global | --playlist NAME | --track ID]
    tuneshift prefs show                           [--global | --playlist NAME | --track ID]
    tuneshift prefs clear                          [--global | --playlist NAME | --track ID]

where ``version.<field>`` is ``prefer`` / ``avoid`` / ``tiebreak_order``
(comma lists), ``duration_tolerance_percent`` (float) or ``min_lead`` (int).
"""
from __future__ import annotations

from collections.abc import Callable

from tuneshift.db import Database
from tuneshift.matching.criteria import Strength, load_token_whitelist
from tuneshift.matching.preferences import Preferences, resolve_preferences
from tuneshift.matching.registry import KNOWN_AXES

_LIST_KEYS = {"prefer", "avoid", "tiebreak_order"}
_FLOAT_KEYS = {"duration_tolerance_percent"}
_INT_KEYS = {"min_lead"}
_VALID_KEYS = _LIST_KEYS | _FLOAT_KEYS | _INT_KEYS

_STRENGTHS = {s.value for s in Strength}
_STRUCTURED_AXES = {"spatial", "mix", "fidelity"}


# --------------------------------------------------------------------------- #
# Typed (criterion, strength, target) model — the general AC-CLI1 interface.  #
# --------------------------------------------------------------------------- #

def _resolve_typed_scope(args, db: Database):
    """Resolve the typed-pref scope from the flags present.

    Returns ``(label, scope, playlist_id, track_id)`` where ``scope`` is
    ``global`` / ``playlist`` / ``playlist-track``. Returns ``None`` (after
    printing an error) for an unknown playlist/track or a ``--track`` without a
    ``--playlist`` (playlist-track needs both).
    """
    playlist = getattr(args, "playlist", None)
    track = getattr(args, "track", None)

    pid = None
    if playlist is not None:
        matches = [p for p in db.list_playlists() if p.name == playlist]
        if not matches:
            print(f'Playlist "{playlist}" not found.')
            return None
        pid = matches[0].id

    if track is not None:
        if pid is None:
            print("Track-scoped preferences need a playlist too: "
                  "use --playlist NAME --track ID.")
            return None
        if db.get_track(track) is None:
            print(f"Track {track} not found.")
            return None
        return (f'playlist "{playlist}" track {track}', "playlist-track", pid, track)

    if pid is not None:
        return (f'playlist "{playlist}"', "playlist", pid, None)
    return ("global", "global", None, None)


def _get_typed_criteria(db: Database, scope: str, pid, tid) -> list[dict]:
    """Read the stored typed criteria for a scope as a list of dicts."""
    if scope == "playlist-track":
        return db.get_playlist_track_prefs(pid, tid)
    if scope == "playlist":
        return list((db.get_preferences(pid) or {}).get("criteria") or [])
    return list((db.get_global_preferences() or {}).get("criteria") or [])


def _write_criterion(db: Database, scope: str, pid, tid,
                     criterion: str, strength: str, target: str) -> None:
    """Upsert one typed criterion at ``scope`` (most-recent target wins)."""
    if scope == "playlist-track":
        db.set_playlist_track_pref(pid, tid, criterion, strength, target)
        return
    # JSON-backed scopes: replace any existing entry for this criterion.
    blob = (db.get_preferences(pid) if scope == "playlist"
            else db.get_global_preferences()) or {}
    criteria = [c for c in (blob.get("criteria") or [])
                if c.get("criterion") != criterion]
    criteria.append({"criterion": criterion, "strength": strength, "target": target})
    blob["criteria"] = criteria
    if scope == "playlist":
        db.set_preferences(pid, blob)
    else:
        db.set_global_preferences(blob)


def _remove_criterion(db: Database, scope: str, pid, tid, criterion: str) -> bool:
    """Delete one typed criterion at ``scope``. Returns True if one was removed."""
    if scope == "playlist-track":
        return db.remove_playlist_track_pref(pid, tid, criterion)
    blob = (db.get_preferences(pid) if scope == "playlist"
            else db.get_global_preferences()) or {}
    criteria = blob.get("criteria") or []
    kept = [c for c in criteria if c.get("criterion") != criterion]
    if len(kept) == len(criteria):
        return False
    if kept:
        blob["criteria"] = kept
    else:
        blob.pop("criteria", None)
    if scope == "playlist":
        db.set_preferences(pid, blob or None)
    else:
        db.set_global_preferences(blob or None)
    return True


def _handle_typed_set(args, db: Database, criterion: str, strength: str,
                      target: str) -> int:
    """Set a typed (criterion, strength, target) preference at the flagged scope."""
    if criterion not in KNOWN_AXES:
        print(f'Unknown criterion "{criterion}". Valid: {sorted(KNOWN_AXES)}')
        return 1
    if strength not in _STRENGTHS:
        print(f'Unknown strength "{strength}". Valid: {sorted(_STRENGTHS)}')
        return 1
    if not target:
        print("A target token is required: prefs set <criterion> <strength> <target>")
        return 1

    resolved = _resolve_typed_scope(args, db)
    if resolved is None:
        return 1
    label, scope, pid, tid = resolved

    # Warn (do not fail) when a STRUCTURED-audio target is not a known token: it
    # would never match a real candidate. Title axes tolerate free tokens (the
    # whitelist confidence gate demotes an unknown one to a soft signal).
    whitelist = load_token_whitelist()
    if criterion in _STRUCTURED_AXES and whitelist.axis(target) is None:
        print(f'Warning: "{target}" is not a known {criterion} token '
              "— it may never match a candidate.")

    _write_criterion(db, scope, pid, tid, criterion, strength, target)
    print(f"Set {criterion} {strength} {target} ({label}).")
    return 0


def _handle_typed_unset(args, db: Database, criterion: str) -> int:
    """Remove a typed preference for ``criterion`` at the flagged scope."""
    if not criterion:
        print("Usage: prefs unset <criterion> [--playlist NAME] [--track ID]")
        return 1
    resolved = _resolve_typed_scope(args, db)
    if resolved is None:
        return 1
    label, scope, pid, tid = resolved
    if _remove_criterion(db, scope, pid, tid, criterion):
        print(f"Unset {criterion} ({label}).")
    else:
        print(f'No "{criterion}" preference set ({label}).')
    return 0


def _handle_typed_list(args, db: Database) -> int:
    """List effective typed preferences for the flagged scope, in precedence order.

    Precedence is global < playlist < playlist-track (most specific last / wins).
    Prints each scope's stored criteria and marks the effective winner per axis.
    """
    resolved = _resolve_typed_scope(args, db)
    if resolved is None:
        return 1
    label, scope, pid, tid = resolved

    layers: list[tuple[str, list[dict]]] = [
        ("global", _get_typed_criteria(db, "global", None, None))
    ]
    if scope in ("playlist", "playlist-track"):
        layers.append(("playlist", _get_typed_criteria(db, "playlist", pid, None)))
    if scope == "playlist-track":
        layers.append(
            ("playlist-track", _get_typed_criteria(db, "playlist-track", pid, tid))
        )

    whitelist = load_token_whitelist()
    # Effective winner per (axis, canonical target): most specific layer wins.
    effective: dict[tuple, tuple[str, int]] = {}
    for layer_name, criteria in layers:
        for idx, c in enumerate(criteria):
            key = (c.get("criterion"), whitelist.canonical(c.get("target")))
            effective[key] = (layer_name, idx)

    print(f"Effective version preferences ({label}), precedence "
          "global < playlist < playlist-track:")
    any_shown = False
    for layer_name, criteria in layers:
        if not criteria:
            continue
        any_shown = True
        print(f"  [{layer_name}]")
        for idx, c in enumerate(criteria):
            key = (c.get("criterion"), whitelist.canonical(c.get("target")))
            active = effective.get(key) == (layer_name, idx)
            marker = "*" if active else " "
            note = "" if active else "  (overridden)"
            print(f"    {marker} {c.get('criterion')} {c.get('strength')} "
                  f"{c.get('target')}{note}")
    if not any_shown:
        print("    (none set)")
    return 0


# --------------------------------------------------------------------------- #
# Legacy version.<field> keyword-list model (backward compatible).            #
# --------------------------------------------------------------------------- #

def _parse_value(key: str, raw: str):
    """Parse a raw legacy CLI value into the stored type for ``key``."""
    if key in _LIST_KEYS:
        return [t.strip().lower() for t in raw.split(",") if t.strip()]
    if key in _FLOAT_KEYS:
        return float(raw)
    return int(raw)


def _resolve_scope(
    args, db: Database
) -> tuple[str, Callable[[], dict | None], Callable[[dict | None], None], str] | None:
    """Resolve the selected legacy preference layer.

    Returns ``(label, getter, setter, layer)`` where ``layer`` is one of
    ``global``/``playlist``/``track``. Returns ``None`` after printing an error
    when the target playlist/track does not exist.
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
    """Cascade-resolve the effective legacy prefs for the selected layer."""
    global_prefs = db.get_global_preferences()
    if layer == "global":
        return resolve_preferences(stored, None, None)
    if layer == "playlist":
        return resolve_preferences(global_prefs, stored, None)
    return resolve_preferences(global_prefs, None, stored)


def _handle_legacy_set(args, db: Database) -> int:
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
    resolved = _resolve_scope(args, db)
    if resolved is None:
        return 1
    label, getter, setter, _ = resolved
    stored = getter() or {}
    stored[field] = value
    setter(stored)
    shown = ", ".join(value) if isinstance(value, list) else value
    print(f"Set {args.key} = {shown} ({label}).")
    return 0


def handle_prefs(args, db: Database) -> int:
    """Show, set, unset, list or clear DB-backed version preferences."""
    criterion = getattr(args, "key", None)
    strength = getattr(args, "value", None)
    target = getattr(args, "target", None)

    if args.action == "set":
        if not criterion:
            print("Usage: prefs set <criterion> <strength> <target>  "
                  "(or legacy prefs set version.<field> <value>)")
            return 1
        # Typed grammar when the 2nd token names a strength; legacy otherwise.
        if strength in _STRENGTHS:
            return _handle_typed_set(args, db, criterion, strength, target)
        if criterion.startswith("version."):
            if strength is None:
                print("Usage: prefs set version.<field> <value>")
                return 1
            return _handle_legacy_set(args, db)
        print(f'Unknown strength "{strength}". '
              f"Use: prefs set <criterion> <{'|'.join(sorted(_STRENGTHS))}> <target>, "
              'or the legacy "prefs set version.<field> <value>".')
        return 1

    if args.action == "unset":
        return _handle_typed_unset(args, db, criterion)

    if args.action == "list":
        return _handle_typed_list(args, db)

    # Legacy show / clear operate on the keyword-list model.
    resolved = _resolve_scope(args, db)
    if resolved is None:
        return 1
    label, getter, setter, layer = resolved

    if args.action == "show":
        stored = getter()
        print(f"Stored preferences ({label}):")
        if stored:
            for key in ("prefer", "avoid", "tiebreak_order",
                        "duration_tolerance_percent", "min_lead"):
                if key in stored:
                    val = stored[key]
                    shown = ", ".join(val) if isinstance(val, list) else val
                    print(f"    {key} = {shown}")
            if stored.get("criteria"):
                print("    criteria:")
                for c in stored["criteria"]:
                    print(f"        {c.get('criterion')} {c.get('strength')} "
                          f"{c.get('target')}")
        else:
            print("    (none set)")
        print(f"\nEffective preferences ({label}, cascade-resolved):")
        _print_preferences(_effective(db, stored, layer))
        return 0

    if args.action == "clear":
        setter(None)
        print(f"Cleared preferences ({label}).")
        return 0

    print(f"Unknown action: {args.action}")
    return 1
