"""Track scoring and confidence classification.

Byte-parity note: this is the legacy scoring surface moved verbatim from the
former ``matching.py``. The Distance engine (Chunk 2.3+) will back these
functions while keeping the golden-parity snapshots green; until then the
integer contributions here are the frozen ground truth.
"""
from difflib import SequenceMatcher

from tuneshift.matching.normalize import (
    _ACOUSTIC_RE,
    _COMPILATION_RE,
    _DELUXE_RE,
    _INSTRUMENTAL_RE,
    _KARAOKE_RE,
    _LIVE_RE,
    _RADIO_EDIT_RE,
    _REMASTER_RE,
    _REMIX_RE,
    _TRIBUTE_RE,
    normalize_artist,
    normalize_title,
)


def score_match(
    source_title: str | object,
    source_artist: str | object,
    source_album: str | None = None,
    result_title: str | None = None,
    result_artist: str | None = None,
    result_album: str | None = None,
) -> int:
    """Score a search result against source metadata. Returns 0-100."""
    canonical = None
    candidate = None
    if result_title is None and result_artist is None and result_album is None:
        canonical = source_title
        candidate = source_artist
        if not all(hasattr(obj, attr) for obj, attr in (
            (canonical, "title"),
            (canonical, "artist"),
            (candidate, "title"),
            (candidate, "artist"),
            (candidate, "album"),
        )):
            raise TypeError("score_match requires either 6 fields or track-like objects")
        source_title = canonical.title
        source_artist = canonical.artist
        source_album = canonical.album
        result_title = candidate.title
        result_artist = candidate.artist
        result_album = candidate.album

    if result_title is None or result_artist is None or result_album is None:
        raise TypeError("score_match requires complete candidate metadata")

    score = 0

    norm_src_title = normalize_title(source_title)
    norm_res_title = normalize_title(result_title)
    if norm_src_title and norm_res_title:
        if norm_src_title == norm_res_title:
            score += 50
        else:
            ratio = SequenceMatcher(None, norm_src_title, norm_res_title).ratio()
            if ratio > 0.85:
                score += 30
            elif ratio >= 0.70:
                score += 15

    norm_src_artist = normalize_artist(source_artist)
    norm_res_artist = normalize_artist(result_artist)
    if norm_src_artist and norm_res_artist:
        if norm_src_artist == norm_res_artist:
            score += 30
        else:
            ratio = SequenceMatcher(None, norm_src_artist, norm_res_artist).ratio()
            if ratio > 0.85:
                score += 25
            elif ratio > 0.70:
                score += 15
            elif ratio > 0.50:
                # Ambiguous zone: moderate penalty (probably different artist)
                score -= 15
            else:
                # Different artist: heavy penalty proportional to dissimilarity
                score -= int(30 * (1.0 - ratio * 2))

    if source_album:
        norm_src_album = normalize_title(source_album)
        norm_res_album = normalize_title(result_album)
        if norm_src_album == norm_res_album:
            score += 20
        elif norm_src_album and norm_res_album:
            ratio = SequenceMatcher(None, norm_src_album, norm_res_album).ratio()
            if ratio >= 0.75:
                score += 10

    if canonical is not None and candidate is not None:
        canonical_isrc = getattr(canonical, "isrc", None)
        candidate_isrc = getattr(candidate, "isrc", None)
        if canonical_isrc and candidate_isrc and canonical_isrc.upper() == candidate_isrc.upper():
            score = min(100, score + 15)

    return min(100, score)


def version_penalty(title: str, album: str) -> int:
    """Return a penalty for undesirable track versions.

    Penalties (cumulative):
    - Karaoke: 50 (always rejected)
    - Instrumental: 50 (always rejected)
    - Live: 20
    - Remix: 20
    - Tribute/cover: 20
    - Radio edit: 20
    - Compilation: 15
    - Acoustic/stripped: 10
    - Remaster: 10
    - Deluxe edition: 5
    """
    combined = f"{title} {album}"
    penalty = 0

    if _KARAOKE_RE.search(combined):
        penalty += 50
    if _INSTRUMENTAL_RE.search(combined):
        penalty += 50
    if _LIVE_RE.search(combined):
        penalty += 20
    if _REMIX_RE.search(combined):
        penalty += 20
    if _TRIBUTE_RE.search(combined):
        penalty += 20
    if _RADIO_EDIT_RE.search(combined):
        penalty += 20
    if _COMPILATION_RE.search(combined):
        penalty += 15
    if _ACOUSTIC_RE.search(combined):
        penalty += 10
    if _REMASTER_RE.search(combined):
        penalty += 10
    if _DELUXE_RE.search(combined):
        penalty += 5

    return penalty


def duration_penalty(
    candidate_duration: int | None,
    reference_duration: int | None = None,
    all_durations: list[int] | None = None,
) -> int:
    """Penalize tracks significantly longer OR shorter than expected.

    Returns 0-20 penalty.
    """
    if candidate_duration is None:
        return 0

    if reference_duration is None and all_durations:
        valid = [d for d in all_durations if d and d > 60]
        if valid:
            reference_duration = min(valid)

    if reference_duration is None or reference_duration < 60:
        return 0

    ratio = candidate_duration / reference_duration

    # Too long
    if ratio > 2.0:
        return 20
    if ratio > 1.6:
        return 15
    if ratio > 1.4:
        return 10

    # Too short
    if ratio < 0.5:
        return 20
    if ratio < 0.65:
        return 15
    if ratio < 0.75:
        return 10

    return 0


def duration_proximity_bonus(
    candidate_duration: int | None,
    canonical_duration: int | None,
) -> int:
    """Bonus 0-10 for duration proximity to canonical track.

    Rewards candidates whose duration closely matches what we expect.
    """
    if not candidate_duration or not canonical_duration:
        return 0
    if canonical_duration < 30:
        return 0
    diff_pct = abs(candidate_duration - canonical_duration) / canonical_duration
    if diff_pct < 0.05:
        return 10
    if diff_pct < 0.15:
        return 5
    return 0


def score_match_with_version(
    source_title: str,
    source_artist: str,
    source_album: str | None,
    result_title: str,
    result_artist: str,
    result_album: str,
    result_duration: int | None = None,
    reference_duration: int | None = None,
    all_durations: list[int] | None = None,
) -> int:
    """Score a search result with version preference applied.

    Combines similarity scoring from score_match with a penalty for
    undesirable versions (live, remix, compilation, etc.) and a duration
    penalty for extended mixes.
    """
    base = score_match(
        source_title, source_artist, source_album,
        result_title, result_artist, result_album,
    )
    penalty = version_penalty(result_title, result_album)
    dur_pen = duration_penalty(result_duration, reference_duration, all_durations)
    return max(0, min(100, base - penalty - dur_pen))


def classify_results(scores: list[int]) -> str:
    """Classify match confidence.

    Returns 'high', 'ambiguous', or 'not_found'.
    High: top >= 80 AND second-best < 70 (clear gap).
    Ambiguous: top >= 50 but no clear gap.
    Not found: top < 50 or no results.
    """
    if not scores:
        return "not_found"
    top = max(scores)
    if top < 50:
        return "not_found"
    sorted_desc = sorted(scores, reverse=True)
    second = sorted_desc[1] if len(sorted_desc) > 1 else 0
    if top >= 80 and second < 70:
        return "high"
    return "ambiguous"
