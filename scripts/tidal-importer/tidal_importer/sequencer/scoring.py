"""Pairwise transition scoring with weighted dimensions."""
from tidal_importer.sequencer.cache import TrackMetadata


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
    """Score thematic/vibe similarity (0.0-1.0)."""
    themes_sim = jaccard(a.themes, b.themes)
    vibes_sim = jaccard(a.vibes, b.vibes)
    era_sim = jaccard(a.era_mood, b.era_mood)
    return 0.40 * themes_sim + 0.40 * vibes_sim + 0.20 * era_sim


def energy_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score energy/valence continuity (0.0-1.0)."""
    if a.energy is None or b.energy is None:
        return 0.5
    energy_delta = abs(a.energy - b.energy)
    valence_delta = abs((a.valence or 0.5) - (b.valence or 0.5))
    return max(0.0, 1.0 - 0.6 * energy_delta - 0.4 * valence_delta)


def instrumentation_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score instrumentation/texture similarity (0.0-1.0)."""
    instrument_overlap = jaccard(a.instruments, b.instruments)

    # Density scoring
    density_map = {"sparse": 0, "mid": 1, "dense": 2}
    d_a = density_map.get(a.density or "mid", 1)
    d_b = density_map.get(b.density or "mid", 1)
    density_diff = abs(d_a - d_b)
    if density_diff == 0:
        density_s = 1.0
    elif density_diff == 1:
        density_s = 0.6
    else:
        density_s = 0.2

    # Acousticness delta
    ac_a = a.acousticness if a.acousticness is not None else 0.5
    ac_b = b.acousticness if b.acousticness is not None else 0.5
    acousticness_s = 1.0 - abs(ac_a - ac_b)

    return 0.40 * instrument_overlap + 0.35 * density_s + 0.25 * acousticness_s


def bpm_score(bpm_a: float | None, bpm_b: float | None, tolerance: float = 0.175) -> float:
    """Score BPM proximity (0.0-1.0). Symmetric."""
    if bpm_a is None or bpm_b is None:
        return 0.5
    if bpm_a == 0 or bpm_b == 0:
        return 0.5

    # Check halftime/doubletime
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
    """Score mode compatibility (0.0-1.0)."""
    if mode_a is None or mode_b is None:
        return 0.5
    if mode_a == mode_b:
        return 1.0
    # Resolution bonus: minor -> major with both low valence
    if mode_a == 0 and mode_b == 1:
        if (valence_a or 0.5) < 0.4 and (valence_b or 0.5) < 0.4:
            return 0.7
    return 0.5


# Camelot wheel: number (1-12) + letter (A=minor, B=major)
def key_score(camelot_a: str | None, camelot_b: str | None) -> float:
    """Score key compatibility via Camelot wheel (0.0-1.0)."""
    if not camelot_a or not camelot_b:
        return 0.5
    try:
        num_a = int(camelot_a[:-1])
        letter_a = camelot_a[-1]
        num_b = int(camelot_b[:-1])
        letter_b = camelot_b[-1]
    except (ValueError, IndexError):
        return 0.5

    # Same position, same letter
    if num_a == num_b and letter_a == letter_b:
        return 1.0
    # Adjacent number, same letter
    num_dist = min(abs(num_a - num_b), 12 - abs(num_a - num_b))
    if num_dist == 1 and letter_a == letter_b:
        return 1.0
    # Same number, different letter (relative major/minor)
    if num_a == num_b and letter_a != letter_b:
        return 1.0
    # Score by distance
    if num_dist == 2:
        return 0.7
    if num_dist == 3:
        return 0.4
    return max(0.0, 1.0 - num_dist / 6.0)


def _has_dimension_data(track: TrackMetadata, dimension: str) -> bool:
    """Check if a track has data for a scoring dimension."""
    if dimension == "themes":
        return len(track.themes) > 0 or len(track.vibes) > 0
    elif dimension == "energy":
        return track.energy is not None
    elif dimension == "instrumentation":
        return len(track.instruments) > 0 or track.acousticness is not None
    elif dimension == "bpm":
        return track.bpm is not None
    elif dimension == "mode":
        return track.mode is not None
    elif dimension == "key":
        return track.camelot_code is not None
    return False


def score_pair(
    a: TrackMetadata,
    b: TrackMetadata,
    weights: dict[str, float],
) -> float:
    """Compute weighted transition score between two tracks.

    Dimensions with missing data are excluded and weights renormalized.
    Returns 0.0-1.0.
    """
    applicable: dict[str, float] = {}
    for dim, weight in weights.items():
        if _has_dimension_data(a, dim) and _has_dimension_data(b, dim):
            applicable[dim] = weight

    if not applicable:
        return 0.5  # no data: neutral

    total = sum(applicable.values())
    normalized = {k: v / total for k, v in applicable.items()}

    score = 0.0
    for dim, w in normalized.items():
        if dim == "themes":
            score += w * theme_score(a, b)
        elif dim == "energy":
            score += w * energy_score(a, b)
        elif dim == "instrumentation":
            score += w * instrumentation_score(a, b)
        elif dim == "bpm":
            score += w * bpm_score(a.bpm, b.bpm)
        elif dim == "mode":
            score += w * mode_score(a.mode, b.mode, a.valence, b.valence)
        elif dim == "key":
            score += w * key_score(a.camelot_code, b.camelot_code)

    return score
