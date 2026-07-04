"""Sync command: reconcile and push playlist to platform."""
import sys

from tuneshift.db import Database
from tuneshift.reconcile import reconcile_track
from tuneshift.models import PlatformMapping


def handle_sync(args, db: Database) -> int:
    """Reconcile tracks and push to platform."""

    if args.all:
        any_failures = False
        for pl in db.list_playlists():
            platforms = db.get_linked_platforms(pl.id)
            if platforms:
                rc = _sync_one(db, pl, platforms, args)
                if rc != 0:
                    any_failures = True
        return 1 if any_failures else 0

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

    push_failed = False
    synced_ok: dict[str, bool] = {}
    # The exact release ids the resolver approved for THIS playlist, per platform,
    # keyed by track. AC-L4: the auto-reorder re-push mirrors this resolved set
    # (re-ordered) rather than independently re-reading the global platform_tracks
    # table, so a rejected substitute / a per-playlist override lock is never
    # bypassed on the second push.
    resolved_by_platform: dict[str, dict[int, str]] = {}

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
        resolved_ids = resolved_by_platform.setdefault(platform_name, {})
        unavailable: list[str] = []

        for track in tracks:
            result = reconcile_track(
                db, track.id, client,
                force=getattr(args, "reconcile", False),
                cached_mapping=cached_mappings.get(track.id),
                playlist_id=playlist.id,
                verify_locked=getattr(args, "verify_locks", False),
            )
            db.save_match_audit(track.id, platform_name, result.audit)

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
                resolved_ids[track.id] = result.platform_track_id

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
            try:
                client.replace_playlist_tracks(platform_playlist_id, canonical_platform_ids)
                print(f"  Pushed {len(canonical_platform_ids)} tracks to {platform_name}.")
                synced_ok[platform_name] = True
            except Exception as exc:
                print(f"  Push to {platform_name} failed: {exc}", file=sys.stderr)
                push_failed = True
                synced_ok[platform_name] = False
        else:
            print(f"  No tracks to push to {platform_name}.")

    # Auto-reorder if enabled for this playlist
    if playlist.auto_reorder:
        from tuneshift.sequencer import sequence_playlist

        reordered = sequence_playlist(db, playlist.id, arc=playlist.reorder_arc)
        db.set_playlist_tracks(playlist.id, reordered)
        print(f'\n  Auto-reordered "{playlist.name}" (arc={playlist.reorder_arc})')

        # Push reordered tracks only to the platforms we just synced. AC-L4: use
        # the resolver-approved ids captured above (re-ordered), never a fresh
        # read of the global platform_tracks table — that would resurrect a
        # rejected substitute or ignore a per-playlist override lock.
        reordered_tracks = db.get_playlist_tracks(playlist.id)
        for platform_name in platforms:
            client = _load_client(platform_name)
            if not client or not client.load_session():
                continue
            platform_playlist_id = db.get_platform_playlist_id(playlist.id, platform_name)
            if not platform_playlist_id:
                continue
            resolved_ids = resolved_by_platform.get(platform_name, {})
            platform_ids = [
                resolved_ids[t.id] for t in reordered_tracks if t.id in resolved_ids
            ]
            if platform_ids:
                try:
                    client.replace_playlist_tracks(platform_playlist_id, platform_ids)
                    print(f"  {platform_name}: synced ({len(platform_ids)} tracks)")
                    synced_ok[platform_name] = True
                except Exception as exc:
                    print(f"  {platform_name}: reorder push failed ({exc})", file=sys.stderr)
                    push_failed = True
                    synced_ok[platform_name] = False

    # Record the synced marker only for platforms whose push actually succeeded.
    for platform_name, ok in synced_ok.items():
        if ok:
            db.mark_playlist_synced(playlist.id, platform_name)

    return 1 if push_failed else 0
