"""Track reconciliation: match canonical tracks to platform-specific IDs."""
from dataclasses import dataclass, field

from tuneshift.db import Database
from tuneshift.matching import normalize_title, normalize_artist, score_match, score_match_with_version, classify_results, is_remaster
from tuneshift.models import TrackResult, PlatformMapping


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


def reconcile_track(
    db: Database,
    track_id: int,
    client: object,
    force: bool = False,
    cached_mapping: PlatformMapping | None = None,
) -> ReconcileResult:
    """Reconcile a canonical track to a platform ID.

    Checks cache first, then searches by ISRC, then by title+artist.
    """
    track = db.get_track(track_id)
    if track is None:
        return ReconcileResult(confidence="not_found")

    platform_name = client.platform_name  # type: ignore[attr-defined]

    if not force:
        mapping = cached_mapping or db.get_platform_mapping(track_id, platform_name)

        # Identity resolution shortcut: resolved tracks can reuse an existing mapping.
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

        # Check cached mapping
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

    # Search by ISRC first (highest confidence)
    if track.isrc:
        isrc_result = client.search_isrc(track.isrc)  # type: ignore[attr-defined]
        if isrc_result:
            is_div = _check_divergence(track.album, isrc_result.album)
            div_note = f"ISRC match but album differs: {isrc_result.album}" if is_div else None
            return ReconcileResult(
                platform_track_id=isrc_result.platform_id,
                platform_title=isrc_result.title,
                platform_artist=isrc_result.artist,
                platform_album=isrc_result.album,
                score=100,
                confidence="high",
                is_divergent=is_div,
                divergence_note=div_note,
            )

    # Search by title + artist
    query = f"{track.title} {track.artist}"
    results: list[TrackResult] = client.search_track(query, limit=10)  # type: ignore[attr-defined]

    if not results:
        return ReconcileResult(confidence="not_found")

    # Score each result with version preference
    scored: list[tuple[int, TrackResult]] = []
    for r in results:
        s = score_match_with_version(
            track.title, track.artist, track.album,
            r.title, r.artist, r.album,
        )
        scored.append((s, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    scores = [s for s, _ in scored]
    confidence = classify_results(scores)

    if confidence == "not_found":
        return ReconcileResult(confidence="not_found", alternatives=[r for _, r in scored[:3]])

    best_score, best_result = scored[0]
    is_div = _check_divergence(track.album, best_result.album)
    div_note = f"Version differs: {best_result.album}" if is_div else None

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
    )


def _check_divergence(source_album: str | None, result_album: str) -> bool:
    """Check if the result is a different version/remaster."""
    if not source_album:
        return False
    norm_src = normalize_title(source_album)
    norm_res = normalize_title(result_album)
    if norm_src == norm_res:
        return False
    # If one is a remaster and the other isn't, it's divergent
    if is_remaster(result_album) != is_remaster(source_album or ""):
        return True
    # If normalized titles are very different, it's divergent
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, norm_src, norm_res).ratio()
    return ratio < 0.7
