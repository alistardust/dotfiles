"""Remove command: remove a track from a playlist and sync to platforms."""
import sys

from tuneshift.db import Database


def handle_rm(args, db: Database) -> int:
    """Remove a track from a playlist by position or title match."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    target = args.target
    tracks = db.get_playlist_tracks(playlist.id)

    # Try as position number first
    try:
        position = int(target)
        if position < 1 or position > len(tracks):
            print(f"Position {position} out of range (1-{len(tracks)})", file=sys.stderr)
            return 1
        track = tracks[position - 1]
        had_failure = _remove_and_sync(db, playlist, track, position)
        return 1 if had_failure else 0
    except ValueError:
        pass

    # Match by title
    target_lower = target.lower()
    matches = [(i + 1, t) for i, t in enumerate(tracks) if target_lower in t.title.lower()]

    if not matches:
        print(f"No track matching \"{target}\" in \"{playlist.name}\"", file=sys.stderr)
        return 1

    if len(matches) == 1:
        pos, track = matches[0]
        had_failure = _remove_and_sync(db, playlist, track, pos)
        return 1 if had_failure else 0

    # Multiple matches: show and ask
    print(f"Multiple matches for \"{target}\":")
    for pos, track in matches:
        print(f"  {pos}. {track.title} - {track.artist}")
    choice = input("Remove which position? ").strip()
    try:
        pos = int(choice)
        track = tracks[pos - 1]
        had_failure = _remove_and_sync(db, playlist, track, pos)
        return 1 if had_failure else 0
    except (ValueError, IndexError):
        print("Cancelled.", file=sys.stderr)
        return 1


def _remove_and_sync(db: Database, playlist, track, position: int) -> bool:
    """Remove from DB and sync removal to all linked platforms.

    Returns True if any platform operation failed.
    """
    from tuneshift.commands.ingest_cmd import _load_client

    db.remove_playlist_track_by_position(playlist.id, position)
    print(f"Removed \"{track.title} - {track.artist}\" (position {position}) from \"{playlist.name}\"")

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
                i for i, pt in enumerate(platform_tracks)
                if target_lower in pt.title.lower()
            ]
            if matches:
                client.remove_tracks_by_positions(platform_playlist_id, matches)
                print(f"  {platform_name}: removed")
            else:
                print(f"  {platform_name}: track not found on platform")
        except Exception as exc:
            print(f"  {platform_name}: sync failed ({exc})", file=sys.stderr)
            failures = True

    return failures
