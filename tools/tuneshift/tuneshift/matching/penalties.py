"""Configurable named penalties — the beets-style scoring primitives.

Each scoring signal (title, artist, album, isrc, version keywords, duration)
is expressed as a :class:`SignalPenalty` carrying two projections of the same
judgement:

* ``penalty`` (0.0-1.0) and ``weight`` — the *distance* view: 0.0 = perfect,
  1.0 = worst; distance = Σ(penalty·weight) / Σweight (see ``engine.py``).
* ``points`` — the *legacy-score* view: the exact signed integer this signal
  contributed under the historical additive scorer, so the split preserves
  byte-for-byte parity with ``score_match`` / ``score_match_with_version``.

All magic numbers live in :class:`Weights`; its defaults reproduce the current
scorer exactly. Callers can pass a customised ``Weights`` (or per-playlist
preferences, later) without touching this code.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from tuneshift.matching.similarity import ratio


@dataclass(frozen=True)
class VersionWeights:
    """Point penalties for undesirable version keywords (all cumulative)."""

    karaoke: int = 50
    instrumental: int = 50
    live: int = 20
    remix: int = 20
    tribute: int = 20
    radio_edit: int = 20
    compilation: int = 15
    acoustic: int = 10
    remaster: int = 10
    deluxe: int = 5


@dataclass(frozen=True)
class Weights:
    """All tunable magic numbers. Defaults == the historical scorer."""

    # Title bonus tiers (ratio thresholds are exclusive/inclusive as noted).
    title_exact: int = 50
    title_high: int = 30            # ratio > title_high_ratio
    title_mid: int = 15             # ratio >= title_mid_ratio
    title_high_ratio: float = 0.85
    title_mid_ratio: float = 0.70

    # Artist bonus/penalty tiers.
    artist_exact: int = 30
    artist_high: int = 25           # ratio > artist_high_ratio
    artist_mid: int = 15            # ratio > artist_mid_ratio
    artist_low_penalty: int = 15    # ratio > artist_low_ratio -> -artist_low_penalty
    artist_heavy_base: int = 30     # else -> -int(base * (1 - 2*ratio))
    artist_high_ratio: float = 0.85
    artist_mid_ratio: float = 0.70
    artist_low_ratio: float = 0.50

    # Album bonus tiers (only scored when a source album is present).
    album_exact: int = 20
    album_high: int = 10            # ratio >= album_high_ratio
    album_high_ratio: float = 0.75

    # ISRC exact-match bonus.
    isrc_bonus: int = 15

    # Duration band penalties (require a reference >= duration_ref_floor).
    duration_ref_floor: int = 60
    duration_long_max: int = 20     # ratio > 2.0
    duration_long_high: int = 15    # ratio > 1.6
    duration_long_mid: int = 10     # ratio > 1.4
    duration_short_max: int = 20    # ratio < 0.5
    duration_short_high: int = 15   # ratio < 0.65
    duration_short_mid: int = 10    # ratio < 0.75

    version: VersionWeights = field(default_factory=VersionWeights)

    def with_overrides(self, **kwargs: object) -> "Weights":
        """Return a copy with the given top-level fields replaced."""
        return replace(self, **kwargs)


DEFAULT_WEIGHTS = Weights()


@dataclass(frozen=True)
class SignalPenalty:
    """One scoring signal, in both the distance and legacy-score projections.

    ``points`` is the exact signed integer the signal contributes to the
    legacy 0-100 score. ``penalty`` (0.0-1.0) and ``weight`` drive the
    normalized distance model.
    """

    name: str
    points: int
    penalty: float
    weight: int


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _bonus_penalty(points: int, budget: int) -> float:
    """Normalized penalty for a *bonus* signal: full budget -> 0, none -> 1."""
    if budget <= 0:
        return 0.0
    return _clamp01(1.0 - points / budget)


def title_signal(source_title: str, result_title: str, weights: Weights = DEFAULT_WEIGHTS) -> SignalPenalty:
    """Score title similarity. Empty on either side yields no signal."""
    budget = weights.title_exact
    if not source_title or not result_title:
        return SignalPenalty("title", 0, 1.0, budget)
    if source_title == result_title:
        points = weights.title_exact
    else:
        r = ratio(source_title, result_title)
        if r > weights.title_high_ratio:
            points = weights.title_high
        elif r >= weights.title_mid_ratio:
            points = weights.title_mid
        else:
            points = 0
    return SignalPenalty("title", points, _bonus_penalty(points, budget), budget)


def artist_signal(source_artist: str, result_artist: str, weights: Weights = DEFAULT_WEIGHTS) -> SignalPenalty:
    """Score artist similarity. Empty on either side yields no signal."""
    budget = weights.artist_exact
    if not source_artist or not result_artist:
        return SignalPenalty("artist", 0, 1.0, budget)
    if source_artist == result_artist:
        points = weights.artist_exact
    else:
        r = ratio(source_artist, result_artist)
        if r > weights.artist_high_ratio:
            points = weights.artist_high
        elif r > weights.artist_mid_ratio:
            points = weights.artist_mid
        elif r > weights.artist_low_ratio:
            points = -weights.artist_low_penalty
        else:
            points = -int(weights.artist_heavy_base * (1.0 - r * 2))
    return SignalPenalty("artist", points, _bonus_penalty(points, budget), budget)


def album_signal(
    source_album: str | None,
    result_album: str | None,
    weights: Weights = DEFAULT_WEIGHTS,
    *,
    source_present: bool = True,
) -> SignalPenalty:
    """Score album similarity.

    ``source_present`` mirrors the legacy scorer's gate on the *raw* source
    album being truthy: when False the signal is neutral (no source album to
    compare). When True, inputs are expected already normalized and equal
    strings score an exact match (including the empty/empty case, preserving
    legacy behavior for albums whose names are pure edition tags).
    """
    budget = weights.album_exact
    if not source_present:
        return SignalPenalty("album", 0, 0.0, budget)
    src = source_album or ""
    res = result_album or ""
    if src == res:
        points = weights.album_exact
    elif src and res:
        points = weights.album_high if ratio(src, res) >= weights.album_high_ratio else 0
    else:
        points = 0
    return SignalPenalty("album", points, _bonus_penalty(points, budget), budget)


def isrc_signal(source_isrc: str | None, result_isrc: str | None, weights: Weights = DEFAULT_WEIGHTS) -> SignalPenalty:
    """Exact-ISRC bonus. No signal unless both ISRCs are present and equal."""
    budget = weights.isrc_bonus
    if source_isrc and result_isrc and source_isrc.upper() == result_isrc.upper():
        return SignalPenalty("isrc", weights.isrc_bonus, 0.0, budget)
    return SignalPenalty("isrc", 0, 1.0, budget)


# Keyword -> (VersionWeights attribute, regex attribute in matching.normalize).
_VERSION_KEYWORDS: tuple[tuple[str, str, str], ...] = (
    ("karaoke", "karaoke", "_KARAOKE_RE"),
    ("instrumental", "instrumental", "_INSTRUMENTAL_RE"),
    ("live", "live", "_LIVE_RE"),
    ("remix", "remix", "_REMIX_RE"),
    ("tribute", "tribute", "_TRIBUTE_RE"),
    ("radio_edit", "radio_edit", "_RADIO_EDIT_RE"),
    ("compilation", "compilation", "_COMPILATION_RE"),
    ("acoustic", "acoustic", "_ACOUSTIC_RE"),
    ("remaster", "remaster", "_REMASTER_RE"),
    ("deluxe", "deluxe", "_DELUXE_RE"),
)


def version_signals(title: str, album: str, weights: Weights = DEFAULT_WEIGHTS) -> list[SignalPenalty]:
    """Return one penalty signal per undesirable version keyword present.

    Each keyword is an independent penalty (fully present -> penalty 1.0,
    weighted by its point cost). Summed ``points`` equal the legacy
    ``version_penalty``.
    """
    from tuneshift.matching import normalize as _norm

    combined = f"{title} {album}"
    signals: list[SignalPenalty] = []
    for name, attr, regex_name in _VERSION_KEYWORDS:
        regex = getattr(_norm, regex_name)
        if regex.search(combined):
            cost = getattr(weights.version, attr)
            signals.append(SignalPenalty(f"version:{name}", -cost, 1.0, cost))
    return signals


def duration_signal(
    candidate_duration: int | None,
    reference_duration: int | None = None,
    all_durations: list[int] | None = None,
    weights: Weights = DEFAULT_WEIGHTS,
) -> SignalPenalty:
    """Penalize durations far from the expected reference.

    Mirrors the legacy tiered bands. ``penalty`` is normalized against the
    maximum band (20) so a full band -> 1.0.
    """
    max_band = max(weights.duration_long_max, weights.duration_short_max)
    if candidate_duration is None:
        return SignalPenalty("duration", 0, 0.0, max_band)

    if reference_duration is None and all_durations:
        valid = [d for d in all_durations if d and d > weights.duration_ref_floor]
        if valid:
            reference_duration = min(valid)

    if reference_duration is None or reference_duration < weights.duration_ref_floor:
        return SignalPenalty("duration", 0, 0.0, max_band)

    r = candidate_duration / reference_duration
    if r > 2.0:
        cost = weights.duration_long_max
    elif r > 1.6:
        cost = weights.duration_long_high
    elif r > 1.4:
        cost = weights.duration_long_mid
    elif r < 0.5:
        cost = weights.duration_short_max
    elif r < 0.65:
        cost = weights.duration_short_high
    elif r < 0.75:
        cost = weights.duration_short_mid
    else:
        cost = 0

    penalty = _clamp01(cost / max_band) if max_band > 0 else 0.0
    return SignalPenalty("duration", -cost, penalty, max_band)
