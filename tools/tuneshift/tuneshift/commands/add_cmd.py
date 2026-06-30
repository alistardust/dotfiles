"""Add command: add a track to a playlist and sync to platforms."""
import sys

from tuneshift.db import Database
from tuneshift.models import Track


def handle_add(args, db: Database) -> int:
    """Add a track to a playlist."""
    # Check banned artists BEFORE doing anything
    from tuneshift.commands.batch_cmd import check_track_against_bans
    banned = check_track_against_bans(db, args.title, args.artist)
    if banned:
        print(
            f"Blocked: \"{args.title}\" by {args.artist} "
            f"includes banned artist \"{banned}\".",
            file=sys.stderr,
        )
        return 1

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

    # Auto-enrich: classify track and artist if not already done
    _auto_enrich(db, track_id, args.artist)

    # Auto-reorder if enabled
    _auto_reorder(db, playlist_id)

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


def _auto_enrich(db: Database, track_id: int, artist_name: str) -> None:
    """Auto-classify track and enrich artist on add.

    Uses the search-grounded pipeline (Last.fm + Genius + LLM synthesis).
    Runs silently. Failures are non-fatal.
    """
    from tuneshift.sequencer.classifier import TrackClassifier
    from tuneshift.enrichment.pipeline import classify_track_grounded

    classifier = TrackClassifier()
    track = db.get_track(track_id)
    if not track:
        return

    # Enrich artist first (so we have genre context for track classification)
    artist = db.get_artist_by_name(artist_name)
    if artist and not artist.genres and not artist.enriched_at:
        _enrich_artist_via_llm(db, artist, classifier)
        artist = db.get_artist_by_name(artist_name)  # reload

    # Classify track if missing vibes/themes (using grounded pipeline)
    metadata = track.metadata or {}
    if not metadata.get("vibes") and not metadata.get("narrator_stance"):
        artist_genres = artist.genres if artist else []
        result = classify_track_grounded(
            track.title, track.artist,
            artist_genres=artist_genres,
            classifier=classifier if classifier.available else None,
        )
        if result:
            metadata.update(result)
            import json as _json
            db.conn.execute(
                "UPDATE tracks SET metadata = ? WHERE id = ?",
                (_json.dumps(metadata), track_id),
            )
            db.conn.commit()


def _enrich_artist_via_llm(db: Database, artist, classifier) -> None:
    """Enrich artist using MusicBrainz lookup for genres, LLM only as fallback."""
    import json
    import musicbrainzngs

    musicbrainzngs.set_useragent("tuneshift", "1.0", "https://github.com/alistardust/dotfiles")

    genres: list[str] = []
    mb_artist_id: str | None = None

    # Try MusicBrainz first (real data, not hallucinated)
    try:
        results = musicbrainzngs.search_artists(artist=artist.name, limit=3)
        artists_found = results.get("artist-list", [])
        if artists_found:
            best = artists_found[0]
            mb_artist_id = best.get("id")
            # Get tags (genres) from MB
            mb_tags = best.get("tag-list", [])
            genres = [t["name"] for t in mb_tags if int(t.get("count", 0)) > 0]

            # If no tags on search result, fetch full artist for tags
            if not genres and mb_artist_id:
                full = musicbrainzngs.get_artist_by_id(mb_artist_id, includes=["tags"])
                mb_tags = full.get("artist", {}).get("tag-list", [])
                genres = [t["name"] for t in mb_tags if int(t.get("count", 0)) > 0]
    except (musicbrainzngs.MusicBrainzError, OSError, KeyError):
        pass

    update_fields: dict = {
        "enrichment_sources": ["musicbrainz"] if genres else [],
        "enriched_at": "auto",
    }

    if genres:
        update_fields["genres"] = genres
    if mb_artist_id:
        update_fields["mb_artist_id"] = mb_artist_id

    # If MusicBrainz didn't return genres, fall back to LLM (less reliable)
    if not genres and classifier and classifier.available:
        prompt = (
            f'What genre(s) is the musical artist "{artist.name}"? '
            f'Return ONLY a JSON array of genre strings. Be specific. '
            f'Example: ["pop", "boyband", "teen pop"] or ["country", "country pop"]. '
            f'If unsure, return ["unknown"].'
        )
        try:
            response = classifier._backend.complete(prompt, classifier._model, max_tokens=100)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(response)
            if isinstance(parsed, list) and parsed and parsed != ["unknown"]:
                update_fields["genres"] = parsed
                update_fields["enrichment_sources"] = ["llm_fallback"]
        except (json.JSONDecodeError, OSError, RuntimeError, ValueError):
            pass

    db.update_artist(artist.id, **update_fields)


def _auto_reorder(db: Database, playlist_id: int) -> None:
    """Trigger auto-reorder if the playlist has it enabled."""
    row = db.conn.execute(
        "SELECT auto_reorder, reorder_arc FROM playlists WHERE id = ?",
        (playlist_id,),
    ).fetchone()
    if row and row[0]:
        from tuneshift.sequencer.optimizer import sequence_playlist
        arc = row[1] or "wave"
        sequence_playlist(db, playlist_id, arc=arc)
