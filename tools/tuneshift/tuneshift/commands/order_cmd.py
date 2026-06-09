"""Order command: sequence a playlist by energy arc."""
import sys

from tuneshift.db import Database


def handle_order(args, db: Database) -> int:
    """Reorder a playlist using the sequencer, then sync to platforms."""
    from tuneshift.sequencer import sequence_playlist

    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    arc = getattr(args, "arc", "wave")

    # Handle auto-reorder toggle
    if getattr(args, "auto_on", False):
        db.set_auto_reorder(playlist.id, enabled=True, arc=arc)
        print(f'Auto-reorder enabled for "{playlist.name}" (arc={arc})')
    elif getattr(args, "auto_off", False):
        db.set_auto_reorder(playlist.id, enabled=False)
        print(f'Auto-reorder disabled for "{playlist.name}"')

    # If only toggling the setting, skip the actual reorder
    if getattr(args, "auto_on", False) or getattr(args, "auto_off", False):
        return 0

    tracks = db.get_playlist_tracks(playlist.id)
    if not tracks:
        print(f'Playlist "{playlist.name}" is empty.')
        return 0

    track_ids = [track.id for track in tracks if track.id is not None]

    reordered = sequence_playlist(db, track_ids, arc=arc)
    db.set_playlist_tracks(playlist.id, reordered)

    print(f'Reordered "{playlist.name}" ({len(reordered)} tracks, arc={arc})')

    # Push reordered playlist to all linked platforms
    if not getattr(args, "no_sync", False):
        _push_order_to_platforms(db, playlist)

    return 0


def _push_order_to_platforms(db: Database, playlist) -> None:
    """Push the current DB track order to all linked platforms."""
    from tuneshift.commands.ingest_cmd import _load_client

    platforms = db.get_linked_platforms(playlist.id)
    if not platforms:
        return

    tracks = db.get_playlist_tracks(playlist.id)

    for platform_name in platforms:
        client = _load_client(platform_name)
        if not client or not client.load_session():
            print(f"  {platform_name}: skipped (not logged in)")
            continue

        platform_playlist_id = db.get_platform_playlist_id(playlist.id, platform_name)
        if not platform_playlist_id:
            print(f"  {platform_name}: skipped (no linked playlist)")
            continue

        # Get platform track IDs in the new order
        platform_ids = []
        for track in tracks:
            mappings = db.get_platform_mappings_for_tracks([track.id], platform_name)
            mapping = mappings.get(track.id)
            if mapping and mapping.platform_track_id:
                platform_ids.append(mapping.platform_track_id)

        if platform_ids:
            try:
                client.replace_playlist_tracks(platform_playlist_id, platform_ids)
                print(f"  {platform_name}: synced ({len(platform_ids)} tracks)")
            except Exception as exc:
                print(f"  {platform_name}: sync failed ({exc})")
        else:
            print(f"  {platform_name}: no track mappings found (run tuneshift sync first)")
