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

    # Find next position
    tracks = db.get_playlist_tracks(playlist_id)
    position = len(tracks) + 1

    db.add_track_to_playlist(playlist_id, track_id, position)
    print(f"Added \"{args.title}\" by {args.artist} to \"{args.playlist}\" at position {position}")

    # Sync to linked platforms
    _sync_add_to_platforms(db, playlist_id, track_id, args.title, args.artist)
    return 0


def _sync_add_to_platforms(db: Database, playlist_id: int, track_id: int, title: str, artist: str) -> None:
    """Reconcile and add the track on all linked platforms."""
    from tuneshift.commands.ingest_cmd import _load_client
    from tuneshift.reconcile import reconcile_track

    platforms = db.get_linked_platforms(playlist_id)
    if not platforms:
        return

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
                print(f"  {platform_name}: failed ({exc})")
        else:
            print(f"  {platform_name}: could not find \"{title}\" by {artist}")
