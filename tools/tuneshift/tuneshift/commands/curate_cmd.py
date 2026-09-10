"""Curate command: trim, analyze, or fill playlists."""

import sys

from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.curator import (
    CurationConstraintError,
    curate_analyze,
    curate_trim,
)
from tuneshift.db import Database
from tuneshift.sequencer.metadata import get_track_metadata_map


def handle_curate(args, db: Database) -> int:
    """Handle curation operations."""
    playlists = db.list_playlists()
    matches = [p for p in playlists if p.name == args.playlist]
    if not matches:
        print(f'Playlist "{args.playlist}" not found.')
        return 1

    pid = matches[0].id
    track_ids = db.get_playlist_track_ids(pid)
    if not track_ids:
        print(f'Playlist "{args.playlist}" is empty.')
        return 1

    metadata_map = get_track_metadata_map(db, track_ids)
    tracks = [metadata_map[tid] for tid in track_ids if tid in metadata_map]

    ctx = PlaylistContext(
        goal=db.get_goal(pid) or "",
        narrative_sections=[],
        mood_profile=None,
        all_tracks=tracks,
    )

    if args.mode == "analyze":
        report = curate_analyze(tracks, ctx)
        print(f'Analysis for "{args.playlist}" ({len(tracks)} tracks):\n')
        print("Strongest tracks:")
        for entry in report.get("strongest", [])[:5]:
            print(
                f"  {entry['title']} - {entry['artist']} (score: {entry['average']:.2f})"  # noqa: E501
            )
        print("\nWeakest tracks:")
        for entry in report.get("weakest", [])[:5]:
            print(
                f"  {entry['title']} - {entry['artist']} (score: {entry['average']:.2f})"  # noqa: E501
            )
        return 0

    if args.mode == "trim":
        constraints = {}
        if hasattr(args, "target_tracks") and args.target_tracks:
            # BUG-23: the target is exact. No tolerance padding, and no
            # inflated hard limit; --hard-limit is honoured only when given.
            constraints["track_count"] = {
                "target": args.target_tracks,
                "hard_limit": getattr(args, "hard_limit", None),
            }
        stored_constraints = db.get_constraints(pid)
        if stored_constraints:
            # An explicit --target-tracks is the user speaking now; a stored
            # constraint is what they said earlier. The CLI wins per key
            # rather than being silently replaced wholesale. Keys the CLI did
            # not set (a stored hard_limit, say) are still honoured.
            merged = dict(stored_constraints)
            for key, value in constraints.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    combined = dict(merged[key])
                    combined.update({k: v for k, v in value.items() if v is not None})
                    merged[key] = combined
                else:
                    merged[key] = value
            constraints = merged

        # BUG-22: pins are protected instructions, not suggestions.
        protected_ids = frozenset(pin.track_id for pin in db.get_pins(pid))

        try:
            result = curate_trim(tracks, ctx, constraints, protected_ids=protected_ids)
        except CurationConstraintError as exc:
            print(f"Trim aborted: {exc}", file=sys.stderr)
            return 1

        target = constraints.get("track_count", {}).get("target")
        # Only a genuinely binding constraint is worth reporting: if the
        # playlist was simply shorter than the target, nothing was cut and
        # there is nothing to explain.
        if (
            target is not None
            and len(result.keep) != target
            and len(tracks) > len(result.keep)
        ):
            print(
                f"Note: kept {len(result.keep)} tracks, not the requested "
                f"{target}; another constraint is binding.",
                file=sys.stderr,
            )

        if args.dry_run:
            print(
                f"Dry run: would keep {len(result.keep)}, cut {len(result.cut)} tracks:"
            )
            for track in result.cut:
                print(f"  CUT: {track.title} - {track.artist}")
            if protected_ids:
                print(f"  ({len(protected_ids)} pinned track(s) protected)")
        else:
            # Apply the trim
            new_order = [t.track_id for t in result.keep]
            db.set_playlist_tracks(pid, new_order)
            print(
                f'Trimmed "{args.playlist}": kept {len(result.keep)}, removed {len(result.cut)} tracks.'  # noqa: E501
            )
        return 0

    print(f"Unknown mode: {args.mode}")
    return 1
