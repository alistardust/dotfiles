"""Platform metadata enrichment: fetch rich catalog data from Tidal."""

from __future__ import annotations

import json
import sys

from tuneshift.db import Database


def enrich_playlist_from_tidal(
    db: Database, playlist_id: int, refresh: bool = False, stale_days: int = 30
) -> tuple[int, int]:
    """Fetch Tidal metadata for all tracks on a playlist.

    Returns (enriched_count, skipped_count).
    """
    from tuneshift.platforms.tidal import TidalClient

    client = TidalClient()
    if not client.load_session():
        print("Not logged in to Tidal. Run: tuneshift login tidal", file=sys.stderr)
        return 0, 0

    tracks = db.get_playlist_tracks(playlist_id)
    enriched = 0
    skipped = 0

    for i, track in enumerate(tracks):
        print(f"  [{i + 1}/{len(tracks)}] {track.title} - {track.artist}...", end="", flush=True)

        # Get platform mapping
        mapping = db.get_platform_mapping(track.id, "tidal")
        if not mapping or not mapping.platform_track_id:
            print(" skip (no Tidal mapping)")
            skipped += 1
            continue

        # Check if already fetched (and not stale)
        if not refresh:
            existing = db.get_track_platform_metadata(track.id, "tidal")
            if existing:
                print(" skip (cached)")
                skipped += 1
                continue

        # Fetch from Tidal
        try:
            meta = _fetch_tidal_track_metadata(client, mapping.platform_track_id)
            if meta:
                db.upsert_track_platform_metadata(
                    track.id, "tidal", mapping.platform_track_id, **meta
                )
                enriched += 1
                qualities = meta.get("audio_qualities", [])
                atmos = "ATMOS" if "DOLBY_ATMOS" in (qualities if isinstance(qualities, list) else []) else ""
                print(f" ok ({meta.get('release_year', '?')}) {atmos}")
            else:
                print(" no data")
                skipped += 1
        except (OSError, RuntimeError, ValueError) as exc:
            print(f" error ({exc})")
            skipped += 1

    return enriched, skipped


def _fetch_tidal_track_metadata(client, platform_track_id: str) -> dict | None:
    """Fetch metadata for a single track from Tidal."""
    try:
        track = client._session.track(int(platform_track_id))
        if not track:
            return None

        # Audio qualities
        audio_qualities = []
        if hasattr(track, "audio_quality"):
            audio_qualities.append(track.audio_quality)
        if hasattr(track, "audio_modes") and track.audio_modes:
            audio_qualities.extend(track.audio_modes)

        # Album info (need full album for release date)
        album = track.album if hasattr(track, "album") else None
        release_year = None
        release_date = None
        album_name = None
        if album:
            album_name = album.name
            try:
                full_album = client._session.album(album.id)
                if full_album.release_date:
                    release_date = str(full_album.release_date.date())
                    release_year = full_album.release_date.year
            except (OSError, RuntimeError, AttributeError):
                pass

        # Artist genres (fetch from artist if available)
        genres = []
        if hasattr(track, "artist") and track.artist:
            try:
                artist_obj = client._session.artist(track.artist.id)
                if hasattr(artist_obj, "roles") and artist_obj.roles:
                    genres = [r.category for r in artist_obj.roles if hasattr(r, "category")]
            except (OSError, RuntimeError, AttributeError):
                pass

        return {
            "release_year": release_year,
            "release_date": release_date,
            "genres": genres,
            "audio_qualities": audio_qualities,
            "album_name": album_name,
            "album_type": None,  # Would need separate album endpoint
            "explicit": getattr(track, "explicit", None),
            "duration_ms": getattr(track, "duration", None) * 1000 if getattr(track, "duration", None) else None,
            "popularity": getattr(track, "popularity", None),
            "raw_metadata": json.dumps({
                "id": platform_track_id,
                "audio_quality": getattr(track, "audio_quality", None),
                "audio_modes": getattr(track, "audio_modes", None),
            }),
        }
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        return None


def derive_tags(db: Database, track_id: int) -> list[str]:
    """Derive tags from platform metadata for a track."""
    meta = db.get_track_platform_metadata(track_id, "tidal")
    if not meta:
        return []

    new_tags: list[str] = []

    # Atmos
    qualities = meta.get("audio_qualities", [])
    if isinstance(qualities, list) and "DOLBY_ATMOS" in qualities:
        new_tags.append("atmos-available")

    # Decade
    year = meta.get("release_year")
    if year:
        decade = (year // 10) * 10
        new_tags.append(f"{decade}s")

    # Album type
    album_type = meta.get("album_type")
    if album_type and album_type != "album":
        new_tags.append(album_type)

    # Explicit
    if meta.get("explicit"):
        new_tags.append("explicit")

    # Apply tags
    for tag in new_tags:
        db.add_track_tag(track_id, tag, source="derived")

    return new_tags


def analyze_playlist(db: Database, playlist_id: int) -> dict:
    """Compute playlist analysis from platform metadata."""
    tracks = db.get_playlist_tracks(playlist_id)
    total = len(tracks)

    years: list[int] = []
    genres_counter: dict[str, int] = {}
    atmos_count = 0
    lossless_count = 0
    tag_counter: dict[str, int] = {}

    for track in tracks:
        meta = db.get_track_platform_metadata(track.id, "tidal")
        if meta:
            if meta.get("release_year"):
                years.append(meta["release_year"])
            qualities = meta.get("audio_qualities", [])
            if isinstance(qualities, list):
                if "DOLBY_ATMOS" in qualities:
                    atmos_count += 1
                if any(q in qualities for q in ("LOSSLESS", "HI_RES_LOSSLESS", "HI_RES")):
                    lossless_count += 1
            genres = meta.get("genres", [])
            if isinstance(genres, list):
                for g in genres:
                    genres_counter[g] = genres_counter.get(g, 0) + 1

        # Track tags
        tags = db.get_track_tags(track.id)
        for t in tags:
            tag_counter[t] = tag_counter.get(t, 0) + 1

    # Era breakdown
    era = ""
    if years:
        min_year, max_year = min(years), max(years)
        if max_year - min_year <= 5:
            era = f"{min_year}-{max_year}"
        else:
            from collections import Counter
            decade_counts = Counter((y // 10) * 10 for y in years)
            era = ", ".join(f"{d}s ({c}/{len(years)})" for d, c in decade_counts.most_common(3))

    # Top genres
    top_genres = sorted(genres_counter.items(), key=lambda x: -x[1])[:5]

    # Top tags
    top_tags = sorted(tag_counter.items(), key=lambda x: -x[1])[:10]

    return {
        "total_tracks": total,
        "enriched_tracks": len(years),
        "era": era,
        "top_genres": top_genres,
        "atmos_pct": (atmos_count / total * 100) if total else 0,
        "lossless_pct": (lossless_count / total * 100) if total else 0,
        "top_tags": top_tags,
    }
