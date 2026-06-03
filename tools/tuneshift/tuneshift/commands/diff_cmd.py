"""Diff command: show canonical vs platform state without syncing."""
import sys

from tuneshift.db import Database
from tuneshift.reconcile import reconcile_track


def handle_diff(args, db: Database) -> int:
    """Show what would change on sync, without actually syncing."""
    from tuneshift.commands.ingest_cmd import _load_client

    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    if args.platform:
        platforms = [args.platform]
    else:
        platforms = db.get_linked_platforms(playlist.id)
        if not platforms:
            print("No platforms linked.", file=sys.stderr)
            return 1

    tracks = db.get_playlist_tracks(playlist.id)
    if not tracks:
        print(f"Playlist \"{playlist.name}\" is empty.")
        return 0

    for platform_name in platforms:
        client = _load_client(platform_name)
        if not client:
            print(f"Unknown platform: {platform_name}", file=sys.stderr)
            continue
        if not client.load_session():
            print(f"Not logged in to {platform_name}.", file=sys.stderr)
            continue

        print(f"\n--- Diff: \"{playlist.name}\" vs {platform_name} ---")

        cached_mappings = db.get_platform_mappings_for_tracks(
            [t.id for t in tracks], platform_name
        )

        to_add: list[str] = []
        unavailable: list[str] = []
        divergent: list[str] = []

        for track in tracks:
            mapping = cached_mappings.get(track.id)
            if mapping and mapping.user_approved:
                if mapping.status == "unavailable":
                    unavailable.append(f"  ? {track.title} - {track.artist}")
                elif mapping.is_divergent:
                    divergent.append(f"  ~ {track.title} -> {mapping.divergence_note}")
                else:
                    to_add.append(f"  + {track.title} - {track.artist}")
            else:
                to_add.append(f"  * {track.title} - {track.artist} (needs reconciliation)")

        if to_add:
            print(f"\n  Would push ({len(to_add)} tracks):")
            for line in to_add[:20]:
                print(line)
            if len(to_add) > 20:
                print(f"  ... and {len(to_add) - 20} more")

        if divergent:
            print(f"\n  Divergent ({len(divergent)}):")
            for line in divergent:
                print(line)

        if unavailable:
            print(f"\n  Unavailable ({len(unavailable)}):")
            for line in unavailable:
                print(line)

        if not to_add and not divergent and not unavailable:
            print("  In sync.")

    return 0
