"""Pairwise transition scoring with weighted dimensions."""

from tuneshift.sequencer.metadata import TrackMetadata


def jaccard(set_a: list[str], set_b: list[str]) -> float:
    """Jaccard similarity between two tag lists."""
    if not set_a and not set_b:
        return 0.0
    a = set(set_a)
    b = set(set_b)
    intersection = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return intersection / union


def theme_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score thematic or vibe similarity."""
    themes_sim = jaccard(a.themes, b.themes)
    vibes_sim = jaccard(a.vibes, b.vibes)
    era_sim = jaccard(a.era_mood, b.era_mood)
    return 0.40 * themes_sim + 0.40 * vibes_sim + 0.20 * era_sim


def energy_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score energy and valence continuity."""
    if a.energy is None or b.energy is None:
        return 0.5
    energy_delta = abs(a.energy - b.energy)
    valence_delta = abs((a.valence or 0.5) - (b.valence or 0.5))
    return max(0.0, 1.0 - 0.6 * energy_delta - 0.4 * valence_delta)


def instrumentation_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score instrumentation and texture similarity."""
    instrument_overlap = jaccard(a.instruments, b.instruments)

    density_map = {"sparse": 0, "mid": 1, "dense": 2}
    density_a = density_map.get(a.density or "mid", 1)
    density_b = density_map.get(b.density or "mid", 1)
    density_diff = abs(density_a - density_b)
    if density_diff == 0:
        density_score_value = 1.0
    elif density_diff == 1:
        density_score_value = 0.6
    else:
        density_score_value = 0.2

    acousticness_a = a.acousticness if a.acousticness is not None else 0.5
    acousticness_b = b.acousticness if b.acousticness is not None else 0.5
    acousticness_score = 1.0 - abs(acousticness_a - acousticness_b)

    return (
        0.40 * instrument_overlap
        + 0.35 * density_score_value
        + 0.25 * acousticness_score
    )


def bpm_score(
    bpm_a: float | None,
    bpm_b: float | None,
    tolerance: float = 0.175,
) -> float:
    """Score BPM proximity."""
    if bpm_a is None or bpm_b is None:
        return 0.5
    if bpm_a == 0 or bpm_b == 0:
        return 0.5

    ratio = max(bpm_a, bpm_b) / min(bpm_a, bpm_b)
    if 1.9 < ratio < 2.1:
        return 0.9

    delta = abs(bpm_a - bpm_b)
    avg_bpm = (bpm_a + bpm_b) / 2
    return max(0.0, 1.0 - delta / (avg_bpm * tolerance))


def mode_score(
    mode_a: int | None,
    mode_b: int | None,
    valence_a: float | None = None,
    valence_b: float | None = None,
) -> float:
    """Score mode compatibility."""
    if mode_a is None or mode_b is None:
        return 0.5
    if mode_a == mode_b:
        return 1.0
    if mode_a == 0 and mode_b == 1:
        if (valence_a or 0.5) < 0.4 and (valence_b or 0.5) < 0.4:
            return 0.7
    return 0.5


def key_score(camelot_a: str | None, camelot_b: str | None) -> float:
    """Score key compatibility via Camelot wheel."""
    if not camelot_a or not camelot_b:
        return 0.5
    try:
        num_a = int(camelot_a[:-1])
        letter_a = camelot_a[-1]
        num_b = int(camelot_b[:-1])
        letter_b = camelot_b[-1]
    except (ValueError, IndexError):
        return 0.5

    if num_a == num_b and letter_a == letter_b:
        return 1.0
    num_dist = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
    if num_dist == 1 and letter_a == letter_b:
        return 1.0
    if num_a == num_b and letter_a != letter_b:
        return 1.0
    if num_dist == 2:
        return 0.7
    if num_dist == 3:
        return 0.4
    return max(0.0, 1.0 - num_dist / 6.0)


def duration_score(
    duration_ms_a: int | None,
    duration_ms_b: int | None,
) -> float:
    """Score duration proximity for fallback sequencing."""
    if duration_ms_a is None or duration_ms_b is None:
        return 0.5
    if duration_ms_a <= 0 or duration_ms_b <= 0:
        return 0.5

    delta = abs(duration_ms_a - duration_ms_b)
    avg_duration = (duration_ms_a + duration_ms_b) / 2
    tolerance = max(avg_duration * 0.35, 30000.0)
    return max(0.0, 1.0 - delta / tolerance)


def _has_dimension_data(track: TrackMetadata, dimension: str) -> bool:
    """Check if a track has data for a scoring dimension."""
    if dimension == "themes":
        return len(track.themes) > 0 or len(track.vibes) > 0
    if dimension == "energy":
        return track.energy is not None
    if dimension == "instrumentation":
        return len(track.instruments) > 0 or track.acousticness is not None
    if dimension == "bpm":
        return track.bpm is not None
    if dimension == "mode":
        return track.mode is not None
    if dimension == "key":
        return track.camelot_code is not None
    return False


def score_pair(
    a: TrackMetadata,
    b: TrackMetadata,
    weights: dict[str, float],
) -> float:
    """Compute a weighted transition score between two tracks."""
    applicable: dict[str, float] = {}
    for dimension, weight in weights.items():
        if _has_dimension_data(a, dimension) and _has_dimension_data(b, dimension):
            applicable[dimension] = weight

    if not applicable:
        return duration_score(a.duration_ms, b.duration_ms)

    total = sum(applicable.values())
    normalized = {key: value / total for key, value in applicable.items()}

    score = 0.0
    for dimension, weight in normalized.items():
        if dimension == "themes":
            score += weight * theme_score(a, b)
        elif dimension == "energy":
            score += weight * energy_score(a, b)
        elif dimension == "instrumentation":
            score += weight * instrumentation_score(a, b)
        elif dimension == "bpm":
            score += weight * bpm_score(a.bpm, b.bpm)
        elif dimension == "mode":
            score += weight * mode_score(a.mode, b.mode, a.valence, b.valence)
        elif dimension == "key":
            score += weight * key_score(a.camelot_code, b.camelot_code)

    return score
