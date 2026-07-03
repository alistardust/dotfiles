"""Track scoring and confidence classification.

The public functions here are the historical scoring surface. They are now
*backed by the shared matching engine* (`penalties`, `engine`, `confidence`)
rather than carrying their own arithmetic, but they preserve byte-for-byte
parity with the previous implementation — the golden-parity snapshots are the
contract. ``score_track_match`` is the new engine-native entry point that
returns a full :class:`~tuneshift.matching.engine.Distance` for callers that
want the distance, breakdown and recommendation (not just an integer).
"""
from __future__ import annotations

from tuneshift.matching.confidence import classify_scores
from tuneshift.matching.engine import Distance
from tuneshift.matching.normalize import (
    normalize_artist,
    normalize_title,
    strip_album_from_title,
)
from tuneshift.matching.penalties import (
    DEFAULT_WEIGHTS,
    Weights,
    album_signal,
    artist_signal,
    duration_signal,
    isrc_signal,
    source_aware_version_signals,
    title_signal,
    version_signals,
)


def score_match(
    source_title: str | object,
    source_artist: str | object,
    source_album: str | None = None,
    result_title: str | None = None,
    result_artist: str | None = None,
    result_album: str | None = None,
    weights: Weights = DEFAULT_WEIGHTS,
) -> int:
    """Score a search result against source metadata. Returns 0-100.

    Accepts either six explicit fields or, when the three result fields are all
    omitted, two track-like objects (``source_title`` = canonical,
    ``source_artist`` = candidate); the object form additionally applies the
    ISRC bonus.
    """
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

    title = title_signal(normalize_title(source_title), normalize_title(result_title), weights)
    artist = artist_signal(normalize_artist(source_artist), normalize_artist(result_artist), weights)
    album = album_signal(
        normalize_title(source_album or ""),
        normalize_title(result_album),
        weights,
        source_present=bool(source_album),
    )
    score = title.points + artist.points + album.points

    if canonical is not None and candidate is not None:
        isrc = isrc_signal(getattr(canonical, "isrc", None), getattr(candidate, "isrc", None), weights)
        score = min(100, score + isrc.points)

    return min(100, score)


def version_penalty(title: str, album: str, weights: Weights = DEFAULT_WEIGHTS) -> int:
    """Return the cumulative penalty for undesirable track versions (>= 0)."""
    return -sum(s.points for s in version_signals(title, album, weights))


def duration_penalty(
    candidate_duration: int | None,
    reference_duration: int | None = None,
    all_durations: list[int] | None = None,
    weights: Weights = DEFAULT_WEIGHTS,
) -> int:
    """Penalize tracks significantly longer OR shorter than expected (0-20)."""
    return -duration_signal(candidate_duration, reference_duration, all_durations, weights).points


def duration_proximity_bonus(
    candidate_duration: int | None,
    canonical_duration: int | None,
) -> int:
    """Bonus 0-10 for duration proximity to canonical track.

    Rewards candidates whose duration closely matches what we expect. This is a
    positive corroboration signal (not a penalty) applied by callers on top of
    the base score, so it is kept distinct from the engine penalties.
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
    weights: Weights = DEFAULT_WEIGHTS,
    *,
    prefer: frozenset[str] = frozenset(),
    avoid: frozenset[str] = frozenset(),
) -> int:
    """Score a search result with source-aware version + duration penalties.

    The base similarity score (with its 0-100 clamp) is computed first, then the
    source-aware recording verdict and duration penalties are subtracted. A
    ``REJECT`` verdict (wrong recording, or a censored/clean take for an explicit
    source) floors the score to 0 so the candidate cannot be auto-selected;
    ``SUBSTITUTE`` (a fallback recording, e.g. the studio master when a live take
    was requested) down-ranks it but keeps it findable. ``prefer``/``avoid`` are
    recording-class sets from the effective per-playlist preferences.
    """
    # Drop an album-name parenthetical that a source has appended to the title
    # (e.g. "Femininomenon (The Rise and Fall of a Midwest Princess)") before
    # scoring, on both sides, so the corruption does not tank title similarity.
    source_title = strip_album_from_title(source_title, source_album)
    result_title = strip_album_from_title(result_title, result_album)
    base = score_match(
        source_title, source_artist, source_album,
        result_title, result_artist, result_album,
        weights,
    )
    vsignals = source_aware_version_signals(
        source_title, source_album or "", result_title, result_album,
        prefer=prefer, avoid=avoid, weights=weights,
    )
    penalty = -sum(s.points for s in vsignals)
    dur_pen = duration_penalty(result_duration, reference_duration, all_durations, weights)
    return max(0, min(100, base - penalty - dur_pen))


def score_track_match(
    source: object,
    candidate: object,
    *,
    weights: Weights = DEFAULT_WEIGHTS,
    all_durations: list[int] | None = None,
    prefer: frozenset[str] = frozenset(),
    avoid: frozenset[str] = frozenset(),
) -> Distance:
    """Engine-native track scorer: build the full Distance for one candidate.

    ``source`` and ``candidate`` are track-like objects exposing ``title``,
    ``artist``, ``album``, ``isrc`` and ``duration_seconds``. Returns a
    :class:`Distance` accumulating title/artist/album/isrc/version/duration
    signals — callers derive ``.total`` (distance), ``.breakdown`` and a
    recommendation. The version signal is *source-aware* (see
    :func:`source_aware_version_signals`): it compares the candidate's recording
    class to the source's, so a live source matches a live take instead of being
    penalised for it. ``prefer``/``avoid`` are recording-class preference sets.
    """
    src_title = getattr(source, "title", "") or ""
    src_album = getattr(source, "album", None)
    cand_title = getattr(candidate, "title", "") or ""
    cand_album = getattr(candidate, "album", None) or ""
    # Drop an album-name parenthetical appended to either title before scoring.
    src_title = strip_album_from_title(src_title, src_album)
    cand_title = strip_album_from_title(cand_title, cand_album)
    distance = Distance()
    distance.add(title_signal(
        normalize_title(src_title),
        normalize_title(cand_title),
        weights,
    ))
    distance.add(artist_signal(
        normalize_artist(getattr(source, "artist", "") or ""),
        normalize_artist(getattr(candidate, "artist", "") or ""),
        weights,
    ))
    distance.add(album_signal(
        normalize_title(src_album or ""),
        normalize_title(cand_album),
        weights,
        source_present=bool(src_album),
    ))
    distance.add(isrc_signal(
        getattr(source, "isrc", None),
        getattr(candidate, "isrc", None),
        weights,
    ))
    distance.extend(source_aware_version_signals(
        src_title, src_album or "", cand_title, cand_album,
        prefer=prefer, avoid=avoid, weights=weights,
    ))
    distance.add(duration_signal(
        getattr(candidate, "duration_seconds", None),
        getattr(source, "duration_seconds", None),
        all_durations,
        weights,
    ))
    return distance


def classify_results(scores: list[int]) -> str:
    """Classify match confidence. Returns 'high', 'ambiguous', or 'not_found'.

    Delegates to :func:`tuneshift.matching.confidence.classify_scores` so there
    is a single confidence implementation.
    """
    return classify_scores(scores)
