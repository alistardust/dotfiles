"""Track reconciliation: match canonical tracks to platform-specific IDs."""
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from tuneshift.db import Database
from tuneshift.matching import (
    classify_results,
    duration_proximity_bonus,
    is_remaster,
    normalize_title,
    score_match_with_version,
)
from tuneshift.models import AlbumResult, ArtistResult, PlatformMapping, TrackResult


@dataclass
class ReconcileResult:
    """Result of reconciling a track against a platform."""

    platform_track_id: str = ""
    platform_title: str = ""
    platform_artist: str = ""
    platform_album: str = ""
    score: int = 0
    confidence: str = "not_found"
    is_divergent: bool = False
    divergence_note: str | None = None
    alternatives: list[TrackResult] = field(default_factory=list)
    from_cache: bool = False
    match_type: str = ""


# --- Strategy functions ---


def _strategy_album_lookup(track, client) -> list[TrackResult]:
    """Search for the album, get its tracklist."""
    if not track.album:
        return []
    try:
        query = f"{track.album} {track.artist}"
        albums: list[AlbumResult] = client.search_album(query, limit=5)
        albums = sorted(albums, key=lambda a: _edition_score(a.title))
        results: list[TrackResult] = []
        for album in albums[:3]:
            tracklist = client.get_album_tracks(album.platform_id)
            results.extend(tracklist)
        return results
    except Exception:
        return []


def _strategy_album_tracklist(track, client) -> list[TrackResult]:
    """Search for album, then fetch its tracklist for title matching."""
    if not track.album:
        return []
    try:
        # Search for the album on platform
        albums: list[AlbumResult] = client.search_album(track.album, limit=5)
        if not albums:
            return []

        # Sort by edition preference (prefer standard editions)
        albums = sorted(albums, key=lambda a: _edition_score(a.title))

        # Get tracklist from the best album
        best_album = albums[0]
        tracklist = client.get_album_tracks(best_album.platform_id)

        return tracklist
    except Exception:
        return []



def _strategy_isrc(track, client) -> list[TrackResult]:
    """Direct ISRC lookup."""
    if not track.isrc:
        return []
    try:
        result = client.search_isrc(track.isrc)
        return [result] if result else []
    except Exception:
        return []


def _strategy_title_artist(track, client) -> list[TrackResult]:
    """Standard title + artist text search."""
    try:
        return client.search_track(f"{track.title} {track.artist}", limit=10)
    except Exception:
        return []


def _strategy_title_only(track, client) -> list[TrackResult]:
    """Broader title-only search."""
    try:
        return client.search_track(track.title, limit=10)
    except Exception:
        return []


def _strategy_album_in_query(track, client) -> list[TrackResult]:
    """Search with title + album name."""
    if not track.album:
        return []
    try:
        return client.search_track(f"{track.title} {track.album}", limit=10)
    except Exception:
        return []


def _strategy_artist_browse(track, client) -> list[TrackResult]:
    """Browse artist discography for the right album."""
    if not track.album:
        return []
    try:
        artists: list[ArtistResult] = client.search_artist(track.artist, limit=3)
        if not artists:
            return []
        albums: list[AlbumResult] = client.get_artist_albums(artists[0].platform_id, limit=20)
        for album in albums:
            if _album_name_matches(album.title, track.album):
                return client.get_album_tracks(album.platform_id)
        return []
    except Exception:
        return []


# Strategy execution order with short-circuit thresholds
_STRATEGIES = [
    (_strategy_isrc, 100),
    (_strategy_title_artist, 90),
    (_strategy_album_tracklist, None),
    (_strategy_album_lookup, 90),
    (_strategy_title_only, None),
    (_strategy_album_in_query, None),
    (_strategy_artist_browse, None),
]


def reconcile_track(
    db: Database,
    track_id: int,
    client: object,
    force: bool = False,
    cached_mapping: PlatformMapping | None = None,
) -> ReconcileResult:
    """Reconcile a canonical track to a platform ID using multi-strategy cascade."""
    track = db.get_track(track_id)
    if track is None:
        return ReconcileResult(confidence="not_found")

    platform_name = client.platform_name

    # Cache/mapping checks
    if not force:
        mapping = cached_mapping or db.get_platform_mapping(track_id, platform_name)
        tier, _, _ = db.get_resolution_state(track_id)
        if tier is not None and mapping is not None:
            if mapping.status == "unavailable":
                return ReconcileResult(confidence="not_found", from_cache=True)
            return ReconcileResult(
                platform_track_id=mapping.platform_track_id,
                score=mapping.match_score or 100,
                confidence="high",
                is_divergent=mapping.is_divergent,
                divergence_note=mapping.divergence_note,
                from_cache=True,
            )
        if mapping and mapping.user_approved:
            if mapping.status == "unavailable":
                return ReconcileResult(confidence="not_found", from_cache=True)
            return ReconcileResult(
                platform_track_id=mapping.platform_track_id,
                score=mapping.match_score or 100,
                confidence="high",
                is_divergent=mapping.is_divergent,
                divergence_note=mapping.divergence_note,
                from_cache=True,
            )

    # Multi-strategy candidate collection with strategy tracking
    all_candidates: list[TrackResult] = []
    candidate_strategies: dict[str, str] = {}  # platform_id -> strategy_name
    seen_ids: set[str] = set()

    for strategy_fn, threshold in _STRATEGIES:
        new_candidates = strategy_fn(track, client)
        strategy_name = strategy_fn.__name__.replace("_strategy_", "")
        for c in new_candidates:
            if c.platform_id not in seen_ids:
                seen_ids.add(c.platform_id)
                all_candidates.append(c)
                candidate_strategies[c.platform_id] = strategy_name

        # Short-circuit check
        if threshold is not None and all_candidates:
            top_score = _quick_top_score(track, all_candidates)
            if top_score >= threshold:
                break

    if not all_candidates:
        return ReconcileResult(confidence="not_found")

    # Score all candidates uniformly
    all_durations = [r.duration_seconds for r in all_candidates if r.duration_seconds]
    scored: list[tuple[int, TrackResult]] = []
    for r in all_candidates:
        s = score_match_with_version(
            track.title, track.artist, track.album,
            r.title, r.artist, r.album,
            result_duration=r.duration_seconds,
            reference_duration=track.duration_seconds,
            all_durations=all_durations,
        )
        s = min(100, s + duration_proximity_bonus(r.duration_seconds, track.duration_seconds))
        scored.append((s, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    scores = [s for s, _ in scored]
    confidence = classify_results(scores)

    if confidence == "not_found":
        return ReconcileResult(confidence="not_found", alternatives=[r for _, r in scored[:3]])

    best_score, best_result = scored[0]
    is_div = _check_divergence(track.album, best_result.album)
    div_note = f"Version differs: {best_result.album}" if is_div else None

    # Duration sanity check
    if (
        track.duration_seconds
        and best_result.duration_seconds
        and best_result.duration_seconds > track.duration_seconds * 1.6
    ):
        is_div = True
        div_note = (
            f"Duration suspicious: "
            f"{best_result.duration_seconds}s vs expected ~{track.duration_seconds}s"
        )

    # Artist mismatch check: if best result has a completely different artist, flag it
    from tuneshift.matching import normalize_artist as _norm_artist
    from difflib import SequenceMatcher as _SM
    src_artist_norm = _norm_artist(track.artist)
    res_artist_norm = _norm_artist(best_result.artist) if best_result.artist else ""
    if src_artist_norm and res_artist_norm:
        artist_ratio = _SM(None, src_artist_norm, res_artist_norm).ratio()
        if artist_ratio < 0.4:
            is_div = True
            div_note = (
                f"Artist mismatch: expected \"{track.artist}\", "
                f"got \"{best_result.artist}\""
            )

    match_type = candidate_strategies.get(best_result.platform_id, "")

    return ReconcileResult(
        platform_track_id=best_result.platform_id,
        platform_title=best_result.title,
        platform_artist=best_result.artist,
        platform_album=best_result.album,
        score=best_score,
        confidence=confidence,
        is_divergent=is_div,
        divergence_note=div_note,
        alternatives=[r for _, r in scored[1:4]],
        match_type=match_type,
    )


def _quick_top_score(track, candidates: list[TrackResult]) -> int:
    """Quick score check for short-circuit decision."""
    best = 0
    for c in candidates:
        s = score_match_with_version(
            track.title, track.artist, track.album,
            c.title, c.artist, c.album,
            result_duration=c.duration_seconds,
            reference_duration=track.duration_seconds,
        )
        s = min(100, s + duration_proximity_bonus(c.duration_seconds, track.duration_seconds))
        if s > best:
            best = s
    return best


def _edition_score(album_name: str) -> int:
    """Lower score = preferred. Standard editions score 0."""
    name_lower = album_name.lower()
    score = 0
    if "deluxe" in name_lower:
        score += 10
    if "expanded" in name_lower:
        score += 10
    if "anniversary" in name_lower:
        score += 5
    if "special edition" in name_lower:
        score += 5
    if "remaster" in name_lower:
        score += 2
    return score


def _album_name_matches(platform_album: str, canonical_album: str) -> bool:
    """Check if a platform album name matches the canonical album."""
    norm_platform = normalize_title(platform_album)
    norm_canonical = normalize_title(canonical_album)
    if not norm_platform or not norm_canonical:
        return False
    if norm_platform == norm_canonical:
        return True
    return SequenceMatcher(None, norm_platform, norm_canonical).ratio() >= 0.75


def _check_divergence(source_album: str | None, result_album: str) -> bool:
    """Check if the result is a different version/remaster."""
    if not source_album:
        return False
    norm_src = normalize_title(source_album)
    norm_res = normalize_title(result_album)
    if norm_src == norm_res:
        return False
    if is_remaster(result_album) != is_remaster(source_album or ""):
        return True
    ratio = SequenceMatcher(None, norm_src, norm_res).ratio()
    return ratio < 0.7
