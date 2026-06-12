"""Enrich command: fetch audio metadata from platform for existing tracks."""
import sys

from tuneshift.db import Database


def handle_enrich(args, db: Database) -> int:
    """Fetch BPM, key, and other audio metadata for tracks in a playlist."""
    from tuneshift.commands.ingest_cmd import _load_client

    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    platform_name = args.platform
    client = _load_client(platform_name)
    if not client:
        print(f"Unknown platform: {platform_name}", file=sys.stderr)
        return 1

    if not client.load_session():
        print(f"Not logged in to {platform_name}. Run: tuneshift login {platform_name}", file=sys.stderr)
        return 1

    if not hasattr(client, "get_track_metadata"):
        print(f"{platform_name} does not support metadata enrichment.", file=sys.stderr)
        return 1

    tracks = db.get_playlist_tracks(playlist.id)
    if not tracks:
        print(f"Playlist \"{playlist.name}\" is empty.")
        return 0

    enriched = 0
    skipped = 0

    for i, track in enumerate(tracks, 1):
        # Skip tracks that already have tempo/key
        if track.tempo and track.key:
            skipped += 1
            continue

        # Get platform mapping to find platform track ID
        mappings = db.get_platform_mappings_for_tracks([track.id], platform_name)
        mapping = mappings.get(track.id)
        if not mapping or not mapping.platform_track_id:
            continue

        try:
            meta = client.get_track_metadata(mapping.platform_track_id)
            if meta:
                db.update_track_metadata(track.id, meta)
                enriched += 1
                if enriched % 10 == 0:
                    print(f"  Enriched {enriched} tracks...", end="\r")
        except (OSError, RuntimeError, ValueError, KeyError, AttributeError):
            continue

    # Future: integrate TrackClassifier here
    # from tuneshift.sequencer.classifier import TrackClassifier
    # classifier = TrackClassifier(model=getattr(args, 'model', None))
    # Classify tracks and update metadata with narrative fields

    print(f"Enriched \"{playlist.name}\": {enriched} tracks updated, {skipped} already had metadata")
    return 0
