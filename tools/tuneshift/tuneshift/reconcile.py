"""Track reconciliation: match canonical tracks to platform-specific IDs."""
import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from tuneshift.db import Database
from tuneshift.matching import (
    classify_album_results,
    classify_artist_results,
    classify_results,
    duration_proximity_bonus,
    edition_cost,
    is_remaster,
    normalize_title,
    preference_sort_bias,
    resolve_preferences,
    score_album_match,
    score_artist_match,
    score_match_with_version,
)
from tuneshift.models import AlbumResult, ArtistResult, PlatformMapping, TrackResult

logger = logging.getLogger(__name__)

# Operational/platform errors that mean "this strategy could not produce
# results" and should degrade to the next strategy. OSError covers
# ConnectionError, TimeoutError, and requests.RequestException (which subclasses
# IOError/OSError); RuntimeError covers not-logged-in and retry exhaustion;
# ValueError covers response parsing failures. Programming errors
# (AttributeError, TypeError, KeyError, IndexError, ...) are intentionally NOT
# caught so genuine bugs propagate instead of silently becoming not_found.
_PLATFORM_ERRORS = (RuntimeError, OSError, ValueError)


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


# --- Album/artist selection helpers (shared scorers, no blind [0]) ---


def _rank_albums(track, albums: list[AlbumResult]) -> list[tuple[float, AlbumResult]]:
    """Rank candidate albums by match distance (best/smallest first)."""
    scored = [
        (
            score_album_match(
                track.album, track.artist, album,
                source_track_count=None, source_year=None,
            ).total,
            album,
        )
        for album in albums
    ]
    scored.sort(key=lambda pair: pair[0])
    return scored


def _acceptable_albums(track, albums: list[AlbumResult]) -> list[AlbumResult]:
    """Return candidate albums whose best match is not classified not_found.

    Preserves ranking order and drops the trailing candidates only once the
    classifier rejects the whole pool (empty -> []).
    """
    ranked = _rank_albums(track, albums)
    if not ranked:
        return []
    if classify_album_results([d for d, _ in ranked]) == "not_found":
        return []
    return [album for _, album in ranked]


def _best_artist(track, artists: list[ArtistResult]) -> ArtistResult | None:
    """Pick the best-matching artist, or None if none is acceptable."""
    if not artists:
        return None
    scored = sorted(
        ((score_artist_match(track.artist, a).total, a) for a in artists),
        key=lambda pair: pair[0],
    )
    if classify_artist_results([d for d, _ in scored]) == "not_found":
        return None
    return scored[0][1]


# --- Strategy functions ---


def _strategy_album_lookup(track, client) -> list[TrackResult]:
    """Search for the album, get tracklists of the best-matching candidates."""
    if not track.album:
        return []
    try:
        query = f"{track.album} {track.artist}"
        albums: list[AlbumResult] = client.search_album(query, limit=5)
        results: list[TrackResult] = []
        for album in _acceptable_albums(track, albums)[:3]:
            tracklist = client.get_album_tracks(album.platform_id)
            results.extend(tracklist)
        return results
    except _PLATFORM_ERRORS as exc:
        logger.warning("album_lookup strategy failed: %s", exc)
        return []


def _strategy_album_tracklist(track, client) -> list[TrackResult]:
    """Search for the album, then fetch the best candidate's tracklist."""
    if not track.album:
        return []
    try:
        query = f"{track.album} {track.artist}"
        albums: list[AlbumResult] = client.search_album(query, limit=5)
        if not albums:
            # Fallback: album name only
            albums = client.search_album(track.album, limit=5)

        acceptable = _acceptable_albums(track, albums)
        if not acceptable:
            return []

        best_album = acceptable[0]
        return client.get_album_tracks(best_album.platform_id)
    except _PLATFORM_ERRORS as exc:
        logger.warning("album_tracklist strategy failed: %s", exc)
        return []



def _strategy_isrc(track, client) -> list[TrackResult]:
    """Direct ISRC lookup."""
    if not track.isrc:
        return []
    try:
        result = client.search_isrc(track.isrc)
        return [result] if result else []
    except _PLATFORM_ERRORS as exc:
        logger.warning("isrc strategy failed: %s", exc)
        return []


def _strategy_title_artist(track, client) -> list[TrackResult]:
    """Standard title + artist text search."""
    try:
        return client.search_track(f"{track.title} {track.artist}", limit=10)
    except _PLATFORM_ERRORS as exc:
        logger.warning("title_artist strategy failed: %s", exc)
        return []


def _strategy_title_only(track, client) -> list[TrackResult]:
    """Broader title-only search."""
    try:
        return client.search_track(track.title, limit=10)
    except _PLATFORM_ERRORS as exc:
        logger.warning("title_only strategy failed: %s", exc)
        return []


def _strategy_album_in_query(track, client) -> list[TrackResult]:
    """Search with title + album name."""
    if not track.album:
        return []
    try:
        return client.search_track(f"{track.title} {track.album}", limit=10)
    except _PLATFORM_ERRORS as exc:
        logger.warning("album_in_query strategy failed: %s", exc)
        return []


def _strategy_artist_browse(track, client) -> list[TrackResult]:
    """Browse the best-matching artist's discography for the right album."""
    if not track.album:
        return []
    try:
        artists: list[ArtistResult] = client.search_artist(track.artist, limit=3)
        artist = _best_artist(track, artists)
        if artist is None:
            return []
        albums: list[AlbumResult] = client.get_artist_albums(artist.platform_id, limit=20)
        acceptable = _acceptable_albums(track, albums)
        if not acceptable:
            return []
        return client.get_album_tracks(acceptable[0].platform_id)
    except _PLATFORM_ERRORS as exc:
        logger.warning("artist_browse strategy failed: %s", exc)
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
    playlist_id: int | None = None,
) -> ReconcileResult:
    """Reconcile a canonical track to a platform ID using multi-strategy cascade.

    When ``playlist_id`` is given, per-playlist version preferences cascade over
    the account-wide defaults and bias candidate ordering. With no configured
    preferences (or ``playlist_id=None``) the cascade resolves to the built-in
    defaults, which is a strict no-op — identical to the pre-preferences
    behaviour.
    """
    track = db.get_track(track_id)
    if track is None:
        return ReconcileResult(confidence="not_found")

    platform_name = client.platform_name

    prefs = resolve_preferences(
        db.get_global_preferences(),
        db.get_preferences(playlist_id) if playlist_id is not None else None,
        None,
    )

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

        # Short-circuit: only on ISRC match (score 100). Never short-circuit
        # on text matches because a later strategy might find a better version.
        if threshold is not None and threshold >= 100 and all_candidates:
            top_score = _quick_top_score(track, all_candidates)
            if top_score >= threshold:
                break

    if not all_candidates:
        return ReconcileResult(confidence="not_found")

    # Score all candidates uniformly
    all_durations = [r.duration_seconds for r in all_candidates if r.duration_seconds]
    scored: list[tuple[int, int, TrackResult]] = []  # (score, edition_penalty, result)
    for r in all_candidates:
        s = score_match_with_version(
            track.title, track.artist, track.album,
            r.title, r.artist, r.album,
            result_duration=r.duration_seconds,
            reference_duration=track.duration_seconds,
            all_durations=all_durations,
        )
        s = min(100, s + duration_proximity_bonus(r.duration_seconds, track.duration_seconds))
        ed = edition_cost(r.album or "")
        scored.append((s, ed, r))

    # Sort by score descending, then by edition preference (standard preferred).
    # Per-playlist preferences bias only the ordering; the reported score and
    # confidence are untouched. With default preferences the bias is 0, so the
    # ordering is byte-identical to the pre-preferences behaviour.
    scored.sort(
        key=lambda x: (
            -(x[0] + preference_sort_bias(x[2].album or "", prefs)),
            x[1],
        )
    )
    scores = [s for s, _, _ in scored]
    confidence = classify_results(scores)

    if confidence == "not_found":
        return ReconcileResult(confidence="not_found", alternatives=[r for _, _, r in scored[:3]])

    best_score, _, best_result = scored[0]
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
        alternatives=[r for _, _, r in scored[1:4]],
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
