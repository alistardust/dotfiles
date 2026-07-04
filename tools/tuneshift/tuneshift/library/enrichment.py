"""Async track enrichment invoked by the resolution worker (AC-D7).

This is the enrichment that used to run *inline* on every ``add`` (track vibe/
theme classification + artist genre lookup). Library-first (AC-D7) forbids
blocking the add path on MusicBrainz/LLM calls, so this work is deferred: the
resolution worker calls :func:`enrich_track` after a track resolves, out of the
interactive path.

Scope note (spec §14 ownership): this is *sequencer classification + artist
genre* enrichment, already owned by this codebase. It is distinct from the
enrichment spec's ``get_track_metadata``/``derive_tags`` capture, which remains
that spec's concern.
"""

from __future__ import annotations

import json
import logging

from tuneshift.db import Database

logger = logging.getLogger(__name__)


def enrich_track(db: Database, track_id: int, artist_name: str) -> None:
    """Classify a track and enrich its artist. Runs out-of-band; never fatal.

    Uses the search-grounded pipeline (MusicBrainz for artist genres, LLM as
    fallback, grounded classifier for track vibes/themes).
    """
    from tuneshift.enrichment.pipeline import classify_track_grounded
    from tuneshift.sequencer.classifier import TrackClassifier

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
            track.title,
            track.artist,
            artist_genres=artist_genres,
            classifier=classifier if classifier.available else None,
        )
        if result:
            metadata.update(result)
            db.conn.execute(
                "UPDATE tracks SET metadata = ? WHERE id = ?",
                (json.dumps(metadata), track_id),
            )
            db.conn.commit()


def _enrich_artist_via_llm(db: Database, artist, classifier) -> None:
    """Enrich artist using MusicBrainz lookup for genres, LLM only as fallback."""
    import musicbrainzngs

    from tuneshift.enrichment.retry import RetryConfig, retry_api_call

    musicbrainzngs.set_useragent(
        "tuneshift", "1.0", "https://github.com/alistardust/dotfiles"
    )

    genres: list[str] = []
    mb_artist_id: str | None = None

    # Retry on 503/network errors. The musicbrainzngs library handles 1 req/s
    # pacing internally; this adds backoff for sustained overload.
    mb_config = RetryConfig(max_retries=3, base_delay=2.0)

    # Try MusicBrainz first (real data, not hallucinated)
    try:
        results = retry_api_call(
            musicbrainzngs.search_artists,
            artist=artist.name,
            limit=3,
            config=mb_config,
        )
        artists_found = results.get("artist-list", [])
        if artists_found:
            best = artists_found[0]
            mb_artist_id = best.get("id")
            # Get tags (genres) from MB
            mb_tags = best.get("tag-list", [])
            genres = [t["name"] for t in mb_tags if int(t.get("count", 0)) > 0]

            # If no tags on search result, fetch full artist for tags
            if not genres and mb_artist_id:
                full = retry_api_call(
                    musicbrainzngs.get_artist_by_id,
                    mb_artist_id,
                    includes=["tags"],
                    config=mb_config,
                )
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
            f"Return ONLY a JSON array of genre strings. Be specific. "
            f'Example: ["pop", "boyband", "teen pop"] or ["country", "country pop"]. '
            f'If unsure, return ["unknown"].'
        )
        try:
            response = classifier._backend.complete(
                prompt, classifier._model, max_tokens=100
            )
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
