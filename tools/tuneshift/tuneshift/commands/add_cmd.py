"""Add command: add a track to a playlist and sync to platforms."""
import sys

from tuneshift.db import Database
from tuneshift.models import Track


def handle_add(args, db: Database) -> int:
    """Add a track to a playlist."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        playlist_id = db.create_playlist(args.playlist)
        print(f"Created playlist: {args.playlist}")
    else:
        playlist_id = playlist.id

    # Find or create canonical track
    existing = db.find_track(args.title, args.artist, getattr(args, "album", None))
    if existing:
        track_id = existing.id
    else:
        track = Track(
            title=args.title,
            artist=args.artist,
            album=getattr(args, "album", None),
        )
        track_id = db.add_track(track)

    # Handle --replace flag
    replace_target = getattr(args, "replace", None)
    position = None
    if replace_target:
        tracks = db.get_playlist_tracks(playlist_id)
        target_lower = replace_target.lower()
        old_matches = [t for t in tracks if target_lower in t.title.lower()]
        if not old_matches:
            print(f"Replace target not found: {replace_target}", file=sys.stderr)
            return 1
        old_track = old_matches[0]
        row = db.conn.execute(
            "SELECT position FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, old_track.id),
        ).fetchone()
        position = row[0] if row else None
        db.transfer_pins(playlist_id, old_track.id, track_id)
        db.remove_track_from_playlist(playlist_id, old_track.id)
        
        # After removal, positions are renumbered. Get current track list and insert at old position
        track_ids = db.get_playlist_track_ids(playlist_id)
        track_ids.insert(position, track_id)
        db.set_playlist_tracks(playlist_id, track_ids)
        print(f'Replacing "{old_track.title}" with "{args.title}"')
    else:
        tracks = db.get_playlist_tracks(playlist_id)
        position = len(tracks) + 1
        db.add_track_to_playlist(playlist_id, track_id, position)

    print(f"Added \"{args.title}\" by {args.artist} to \"{args.playlist}\" at position {position}")



    # Sync to linked platforms
    had_failures = _sync_add_to_platforms(db, playlist_id, track_id, args.title, args.artist)
    return 1 if had_failures else 0


def _sync_add_to_platforms(db: Database, playlist_id: int, track_id: int, title: str, artist: str) -> bool:
    """Reconcile and add the track on all linked platforms.

    Returns True if any platform operation failed.
    """
    from tuneshift.commands.ingest_cmd import _load_client
    from tuneshift.reconcile import reconcile_track

    platforms = db.get_linked_platforms(playlist_id)
    if not platforms:
        return False

    failures = False
    for platform_name in platforms:
        client = _load_client(platform_name)
        if not client or not client.load_session():
            print(f"  {platform_name}: skipped (not logged in)")
            continue

        platform_playlist_id = db.get_platform_playlist_id(playlist_id, platform_name)
        if not platform_playlist_id:
            print(f"  {platform_name}: skipped (no linked playlist)")
            continue

        # Reconcile the track
        result = reconcile_track(db, track_id, client, force=False)
        if result.platform_track_id:
            try:
                client.add_tracks(platform_playlist_id, [result.platform_track_id])
                print(f"  {platform_name}: added")
            except Exception as exc:
                print(f"  {platform_name}: failed ({exc})", file=sys.stderr)
                failures = True
        else:
            print(f"  {platform_name}: could not find \"{title}\" by {artist}")

    return failures
