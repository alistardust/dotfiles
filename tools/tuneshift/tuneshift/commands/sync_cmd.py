"""Sync command: reconcile and push playlist to platform."""
import sys

from tuneshift.db import Database
from tuneshift.reconcile import reconcile_track, ReconcileResult
from tuneshift.models import PlatformMapping


def handle_sync(args, db: Database) -> int:
    """Reconcile tracks and push to platform."""
    from tuneshift.commands.ingest_cmd import _load_client

    if args.all:
        for pl in db.list_playlists():
            platforms = db.get_linked_platforms(pl.id)
            if platforms:
                _sync_one(db, pl, platforms, args)
        return 0

    if not args.playlist:
        print("Specify a playlist name or use --all.", file=sys.stderr)
        return 1

    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    if args.platform:
        platforms = [args.platform]
    else:
        platforms = db.get_linked_platforms(playlist.id)
        if not platforms:
            print("No platforms linked. Specify: tuneshift sync <playlist> <platform>", file=sys.stderr)
            return 1

    return _sync_one(db, playlist, platforms, args)


def _sync_one(db, playlist, platforms, args) -> int:
    """Sync a single playlist to one or more platforms."""
    from tuneshift.commands.ingest_cmd import _load_client

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
            print(f"Not logged in to {platform_name}. Run: tuneshift login {platform_name}", file=sys.stderr)
            continue

        print(f"\n--- Syncing \"{playlist.name}\" to {platform_name} ---")

        # Batch-load cached mappings
        cached_mappings = db.get_platform_mappings_for_tracks(
            [t.id for t in tracks], platform_name
        )

        canonical_platform_ids: list[str] = []
        unavailable: list[str] = []

        for track in tracks:
            result = reconcile_track(
                db, track.id, client,
                force=getattr(args, "reconcile", False),
                cached_mapping=cached_mappings.get(track.id),
            )

            if result.confidence == "not_found":
                unavailable.append(f"  ? {track.title} - {track.artist}")
                db.upsert_platform_mapping(PlatformMapping(
                    track_id=track.id, platform=platform_name,
                    platform_track_id="", match_score=0,
                    status="unavailable", user_approved=True,
                ))
                continue

            if result.confidence == "ambiguous" and not result.from_cache:
                if not getattr(args, "auto", False):
                    print(f"\n  Ambiguous match for: {track.title} - {track.artist}")
                    print(f"    Best: [{result.score}] {result.platform_track_id}")
                    for i, alt in enumerate(result.alternatives[:3]):
                        print(f"    {i+1}. {alt.title} - {alt.artist} ({alt.album})")
                    choice = input("  Accept best match? [Y/n/skip] ").strip().lower()
                    if choice in ("n", "skip"):
                        unavailable.append(f"  ? {track.title} (skipped)")
                        db.upsert_platform_mapping(PlatformMapping(
                            track_id=track.id, platform=platform_name,
                            platform_track_id="", match_score=0,
                            status="unavailable", user_approved=True,
                        ))
                        continue

            # Prompt for divergent matches
            approved = True
            if result.is_divergent and not result.from_cache:
                if not getattr(args, "auto", False):
                    print(f"\n  Divergent match for: {track.title} - {track.artist} ({track.album})")
                    print(f"    Found: {result.divergence_note}")
                    choice = input("  Accept substitute? [Y/n] ").strip().lower()
                    if choice == "n":
                        unavailable.append(f"  ~ {track.title} (divergent, rejected)")
                        approved = False

            if approved and result.platform_track_id:
                canonical_platform_ids.append(result.platform_track_id)

            # Persist mapping
            db.upsert_platform_mapping(PlatformMapping(
                track_id=track.id, platform=platform_name,
                platform_track_id=result.platform_track_id,
                platform_title=result.platform_title,
                platform_artist=result.platform_artist,
                platform_album=result.platform_album,
                match_score=result.score,
                is_divergent=result.is_divergent,
                divergence_note=result.divergence_note,
                status="matched" if not result.is_divergent else "substitute",
                user_approved=approved,
            ))

        if unavailable:
            print(f"\n  Unavailable ({len(unavailable)} tracks):")
            for line in unavailable:
                print(line)

        # Push to platform
        platform_playlist_id = db.get_platform_playlist_id(playlist.id, platform_name)
        if not platform_playlist_id:
            # Try to find or create on platform
            existing = client.find_playlist_by_name(playlist.name)
            if existing:
                platform_playlist_id = existing.platform_id
                db.link_platform_playlist(playlist.id, platform_name, platform_playlist_id)
            else:
                created = client.create_playlist(playlist.name, playlist.description or "")
                platform_playlist_id = created.platform_id
                db.link_platform_playlist(playlist.id, platform_name, platform_playlist_id)

        if canonical_platform_ids:
            client.replace_playlist_tracks(platform_playlist_id, canonical_platform_ids)
            print(f"  Pushed {len(canonical_platform_ids)} tracks to {platform_name}.")
        else:
            print(f"  No tracks to push to {platform_name}.")

    # Auto-reorder if enabled for this playlist
    if playlist.auto_reorder:
        from tuneshift.sequencer import sequence_playlist

        tracks = db.get_playlist_tracks(playlist.id)
        track_ids = [t.id for t in tracks if t.id is not None]
        reordered = sequence_playlist(db, track_ids, arc=playlist.reorder_arc)
        db.set_playlist_tracks(playlist.id, reordered)
        print(f'\n  Auto-reordered "{playlist.name}" (arc={playlist.reorder_arc})')

        from tuneshift.commands.order_cmd import _push_order_to_platforms
        _push_order_to_platforms(db, playlist)

    return 0
