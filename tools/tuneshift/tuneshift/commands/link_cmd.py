"""Link command: auto-discover and link platform playlist IDs by name matching."""
import sys
from tuneshift.db import Database


def handle_link(args, db: Database) -> int:
    """Auto-link platform playlists by matching names."""
    platform = args.platform

    client = _load_client(platform)
    if client is None:
        print(f"Unknown platform: {platform}", file=sys.stderr)
        return 1

    if not client.load_session():
        print(f"Not logged in to {platform}. Run: tuneshift login {platform}", file=sys.stderr)
        return 1

    playlists = db.list_playlists()
    if not playlists:
        print("No playlists in database.")
        return 0

    linked = 0
    skipped = 0
    already = 0

    for pl in playlists:
        # Skip if already linked
        existing = db.get_platform_playlist_id(pl.id, platform)
        if existing:
            already += 1
            continue

        # Try to find by name on platform
        found = client.find_playlist_by_name(pl.name)
        if found:
            db.link_platform_playlist(pl.id, platform, found.platform_id)
            print(f"  Linked: {pl.name} -> {found.platform_id}")
            linked += 1
        else:
            if not args.quiet:
                print(f"  Not found: {pl.name}", file=sys.stderr)
            skipped += 1

    print(f"\nDone: {linked} linked, {already} already linked, {skipped} not found on {platform}")
    return 0


def _load_client(platform_name: str):
    """Load a platform client by name."""
    if platform_name == "tidal":
        from tuneshift.platforms.tidal import TidalClient
        return TidalClient()
    elif platform_name == "spotify":
        from tuneshift.platforms.spotify import SpotifyClient
        return SpotifyClient()
    elif platform_name == "ytmusic":
        from tuneshift.platforms.ytmusic import YTMusicClient
        return YTMusicClient()
    return None
