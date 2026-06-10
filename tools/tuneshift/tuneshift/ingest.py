"""Platform playlist ingestion: import playlists into canonical DB."""
from tuneshift.db import Database


def ingest_from_platform(
    db: Database,
    client: object,
    playlist_id: str,
    enrich: bool = True,
) -> tuple[str, int, int]:
    """Ingest a playlist from a platform into the canonical database.

    Returns (playlist_name, total_tracks, new_tracks_created).
    """
    platform_name = client.platform_name  # type: ignore[attr-defined]

    # Fetch playlist info
    pl_info = client.get_playlist(playlist_id)  # type: ignore[attr-defined]
    if pl_info is None:
        raise ValueError(f"Playlist {playlist_id} not found on {platform_name}")

    name = pl_info.name
    raw_tracks = client.get_playlist_tracks(playlist_id)  # type: ignore[attr-defined]

    # Create or find canonical playlist
    existing_playlists = db.list_playlists()
    canonical_playlist = None
    for p in existing_playlists:
        if p.name == name:
            canonical_playlist = p
            break

    if canonical_playlist is None:
        playlist_db_id = db.create_playlist(name)
    else:
        playlist_db_id = canonical_playlist.id

    # Process each track
    new_count = 0
    track_ids_to_enrich: list[tuple[int, str]] = []

    for position, tr in enumerate(raw_tracks, start=1):
        # Find or create canonical track
        existing = db.find_track(tr.title, tr.artist, tr.album)
        if existing:
            track_id = existing.id
        else:
            from tuneshift.models import Track
            new_track = Track(
                title=tr.title,
                artist=tr.artist,
                album=tr.album,
                duration_seconds=tr.duration_seconds,
                isrc=tr.isrc,
            )
            track_id = db.add_track(new_track)
            new_count += 1
            track_ids_to_enrich.append((track_id, tr.platform_id))

        # Add to playlist (skip if already there)
        db.add_track_to_playlist(playlist_db_id, track_id, position)

        # Store platform mapping
        from tuneshift.models import PlatformMapping
        db.upsert_platform_mapping(PlatformMapping(
            track_id=track_id,
            platform=platform_name,
            platform_track_id=tr.platform_id,
            platform_title=tr.title,
            platform_artist=tr.artist,
            platform_album=tr.album,
            match_score=100,
            status="matched",
            user_approved=True,
        ))

    # Link platform playlist
    db.link_platform_playlist(playlist_db_id, platform_name, playlist_id)

    # Enrich new tracks with audio metadata (BPM, key)
    if enrich and track_ids_to_enrich and hasattr(client, "get_track_metadata"):
        _enrich_tracks(db, client, track_ids_to_enrich)

    return name, len(raw_tracks), new_count


def _enrich_tracks(db: Database, client: object, tracks: list[tuple[int, str]]) -> None:
    """Fetch and store audio metadata (BPM, key) for new tracks."""
    import sys

    enriched = 0
    for track_id, platform_track_id in tracks:
        try:
            meta = client.get_track_metadata(platform_track_id)  # type: ignore[attr-defined]
            if meta:
                db.update_track_metadata(track_id, meta)
                enriched += 1
        except (OSError, RuntimeError, ValueError, KeyError, AttributeError):
            continue

    if enriched:
        print(f"  Enriched {enriched}/{len(tracks)} tracks with audio metadata", file=sys.stderr)
