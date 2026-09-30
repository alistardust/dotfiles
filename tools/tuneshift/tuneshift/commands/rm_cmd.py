"""Remove command: remove a track from a playlist and sync to platforms."""

import sys
from pathlib import Path

from tuneshift.db import Database


def _primary_db_path() -> Path | None:
    """Return the recorded primary database path, or None if unregistered."""
    from tuneshift.persistence.primary import get_primary_db

    return get_primary_db()


def _is_primary_db(active: Path) -> bool:
    """Whether ``active`` is the recorded primary database."""
    from tuneshift.persistence.primary import is_primary_db

    return is_primary_db(active)


def _resolve_target(args, tracks):
    """Resolve the CLI target to a ``(position, track)`` pair, or an exit code.

    BUG-25: a bare number used to be matched against titles first, so a
    positional intent could silently hit a track whose title merely contained
    that digit. An ambiguous bare number is now refused.
    """
    target = args.target
    want_position = getattr(args, "position", False)
    want_title = getattr(args, "title", False)

    title_matches = [
        (i + 1, t) for i, t in enumerate(tracks) if target.lower() in t.title.lower()
    ]

    try:
        position = int(target)
    except ValueError:
        position = None

    if want_position and position is None:
        print(f'"{target}" is not a position.', file=sys.stderr)
        return 1

    if position is not None and not want_title:
        if title_matches and not want_position:
            print(
                f'Ambiguous target "{target}": it is a valid position and also '
                f"matches {len(title_matches)} title(s). "
                "Re-run with --position or --title.",
                file=sys.stderr,
            )
            return 1
        if position < 1 or position > len(tracks):
            print(
                f"Position {position} out of range (1-{len(tracks)})",
                file=sys.stderr,
            )
            return 1
        return position, tracks[position - 1]

    if not title_matches:
        print(f'No track matching "{target}"', file=sys.stderr)
        return 1

    if len(title_matches) == 1:
        return title_matches[0]

    print(f'Multiple matches for "{target}":')
    offered = dict(title_matches)
    for pos, track in title_matches:
        print(f"  {pos}. {track.title} - {track.artist}")
    choice = input("Remove which position? ").strip()
    try:
        pos = int(choice)
    except ValueError:
        print("Cancelled.", file=sys.stderr)
        return 1
    # Only an offered position is accepted. Indexing the full track list here
    # meant "0" selected tracks[-1], the LAST track, and "-1" selected another
    # bystander: negative indices wrap instead of raising IndexError. That is
    # the same class of failure as BUG-25, a number quietly selecting a track
    # the user never named, and this path then pushes the removal live.
    if pos not in offered:
        print(
            f"{pos} is not one of the offered positions "
            f"({', '.join(str(p) for p in offered)}).",
            file=sys.stderr,
        )
        return 1
    return pos, offered[pos]


def handle_rm(args, db: Database) -> int:
    """Remove a track from a playlist by position or title match."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    tracks = db.get_playlist_tracks(playlist.id)
    resolved = _resolve_target(args, tracks)
    if isinstance(resolved, int):
        return resolved
    position, track = resolved

    platforms = db.get_linked_platforms(playlist.id)
    label = f'"{track.title} - {track.artist}" (position {position})'

    if getattr(args, "dry_run", False):
        print(f'Dry run: would remove {label} from "{playlist.name}"')
        for platform_name in platforms:
            print(f"  would push removal to {platform_name}")
        if not platforms:
            print("  no linked platforms; local removal only")
        return 0

    # BUG-24: a copied database is not a sandbox. platform_playlists travels
    # with the copy, so a push from it reaches the same live playlist.
    if platforms and not getattr(args, "allow_nonprimary_push", False):
        active = Path(db.path).resolve()
        if not _is_primary_db(active):
            if _primary_db_path() is None:
                # Unregistered is not the same as "this is a copy", and the
                # remedy must not be the push override: a guard that answers
                # every refusal with --allow-nonprimary-push teaches people to
                # leave it on, which is precisely when BUG-24 bites.
                print(
                    "Refusing to push: no primary database is registered, so "
                    "there is no way to tell this from a copy. Register the "
                    "real one once with: tuneshift primary --set <path>",
                    file=sys.stderr,
                )
            else:
                print(
                    f"Refusing to push: {active} is not the primary database "
                    f"({_primary_db_path()}). Platform IDs travel with a "
                    "copied database, so this would mutate the live playlist. "
                    "Re-run with --allow-nonprimary-push if that is genuinely "
                    "what you want.",
                    file=sys.stderr,
                )
            return 1

    if platforms and not getattr(args, "yes", False):
        print(f'About to remove {label} from "{playlist.name}"')
        print(f"  and push that removal live to: {', '.join(platforms)}")
        if input("Proceed? [y/N] ").strip().lower() not in {"y", "yes"}:
            print("Cancelled.", file=sys.stderr)
            return 1

    had_failure = _remove_and_sync(db, playlist, track, position)
    return 1 if had_failure else 0


def _remove_and_sync(db: Database, playlist, track, position: int) -> bool:
    """Remove from DB and sync removal to all linked platforms.

    Returns True if any platform operation failed.
    """
    from tuneshift.commands.ingest_cmd import _load_client

    # BUG-7: `position` is the 1-based ordinal in the ordered track list, not the
    # stored playlist_tracks.position value. Map it to the real stored position so
    # we delete ONLY the chosen row: the same track_id may appear at several
    # positions, and a track_id-wide delete would silently wipe every copy.
    ordered = db.get_playlist_track_positions(playlist.id)
    stored_position = ordered[position - 1]
    db.remove_playlist_track_by_position(playlist.id, stored_position)
    print(
        f'Removed "{track.title} - {track.artist}" (position {position}) from "{playlist.name}"'  # noqa: E501
    )

    # Auto-reorder if enabled
    cfg = db.get_playlist_reorder_config(playlist.id)
    if cfg and cfg[0]:
        from tuneshift.sequencer.optimizer import sequence_playlist

        arc = cfg[1] or "wave"
        sequence_playlist(db, playlist.id, arc=arc)

    # Sync removal to linked platforms
    failures = False
    platforms = db.get_linked_platforms(playlist.id)
    for platform_name in platforms:
        client = _load_client(platform_name)
        if not client or not client.load_session():
            print(f"  {platform_name}: skipped (not logged in)")
            continue

        platform_playlist_id = db.get_platform_playlist_id(playlist.id, platform_name)
        if not platform_playlist_id:
            print(f"  {platform_name}: skipped (no linked playlist)")
            continue

        # Find the track on the platform by position and remove it
        try:
            platform_tracks = client.get_playlist_tracks(platform_playlist_id)
            # Find by matching title (position may differ due to prior divergence)
            target_lower = track.title.lower()
            matches = [
                i
                for i, pt in enumerate(platform_tracks)
                if target_lower in pt.title.lower()
            ]
            if matches:
                # BUG-7: remove only ONE platform occurrence to mirror the single
                # local removal. Both copies share the same platform id, so which
                # one is removed does not matter; removing all would wipe the track.
                client.remove_tracks_by_positions(platform_playlist_id, matches[:1])
                print(f"  {platform_name}: removed")
            else:
                print(f"  {platform_name}: track not found on platform")
        except Exception as exc:  # noqa: BLE001
            print(f"  {platform_name}: sync failed ({exc})", file=sys.stderr)
            failures = True

    return failures
