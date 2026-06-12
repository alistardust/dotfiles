"""Map command: manually link a track to a platform ID."""
import sys

from tuneshift.db import Database


def _load_client(platform: str):
    """Load a platform client by name."""
    if platform == "tidal":
        from tuneshift.platforms.tidal import TidalClient
        return TidalClient()
    if platform == "ytmusic":
        from tuneshift.platforms.ytmusic import YTMusicClient
        return YTMusicClient()
    return None


def handle_map(args, db: Database) -> int:
    """Store a user-approved platform mapping for a track."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    track = _find_track_by_title(db, playlist.id, args.title)
    if not track:
        print(f"Track not found: {args.title}", file=sys.stderr)
        return 1

    platform, platform_id = _extract_platform_args(args)
    if not platform:
        print("Specify --tidal or --ytmusic with a track ID", file=sys.stderr)
        return 1

    platform_title = None
    platform_artist = None
    platform_album = None

    if args.verify:
        client = _load_client(platform)
        if not client or not client.load_session():
            print(f"Not logged in to {platform}. Run: tuneshift login {platform}", file=sys.stderr)
            return 1

        result = client.get_track(platform_id)
        if not result:
            print(f"Track ID {platform_id} not found on {platform}", file=sys.stderr)
            return 1

        platform_title = result.title
        platform_artist = result.artist
        platform_album = result.album
        duration = f" ({result.duration_seconds}s)" if result.duration_seconds else ""
        print(f"Found: {result.title} - {result.artist} [{result.album}]{duration}")

    db.set_platform_mapping(
        track_id=track.id,
        platform=platform,
        platform_track_id=platform_id,
        user_approved=True,
        platform_title=platform_title,
        platform_artist=platform_artist,
        platform_album=platform_album,
        match_score=100,
    )
    print(f'Mapped "{track.title}" -> {platform}:{platform_id}')
    return 0


def handle_unmap(args, db: Database) -> int:
    """Remove a platform mapping, forcing re-reconcile on next sync."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    track = _find_track_by_title(db, playlist.id, args.title)
    if not track:
        print(f"Track not found: {args.title}", file=sys.stderr)
        return 1

    platform = _extract_unmap_platform(args)
    if not platform:
        print("Specify --tidal or --ytmusic", file=sys.stderr)
        return 1

    db.delete_platform_mapping(track.id, platform)
    print(f'Unmapped "{track.title}" from {platform}')
    return 0


def _find_track_by_title(db: Database, playlist_id: int, title: str):
    """Find a track in a playlist by title substring match."""
    tracks = db.get_playlist_tracks(playlist_id)
    title_lower = title.lower()
    matches = [t for t in tracks if title_lower in t.title.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        exact = [t for t in matches if t.title.lower() == title_lower]
        if len(exact) == 1:
            return exact[0]
        print(f'Multiple matches for "{title}":', file=sys.stderr)
        for t in matches:
            print(f"  - {t.title} - {t.artist}", file=sys.stderr)
        return None
    return None


def _extract_platform_args(args) -> tuple[str | None, str | None]:
    """Extract platform name and ID from args."""
    if getattr(args, "tidal", None):
        return "tidal", args.tidal
    if getattr(args, "ytmusic", None):
        return "ytmusic", args.ytmusic
    return None, None


def _extract_unmap_platform(args) -> str | None:
    """Extract platform name for unmap."""
    if getattr(args, "tidal", False):
        return "tidal"
    if getattr(args, "ytmusic", False):
        return "ytmusic"
    return None
