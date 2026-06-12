"""Playlist intent inference from track metadata."""
from collections import Counter
from dataclasses import dataclass, field

from tuneshift.sequencer.metadata import TrackMetadata


@dataclass
class PlaylistIntent:
    """Inferred narrative intent for a playlist."""

    dominant_themes: list[str] = field(default_factory=list)
    emotional_range: tuple[float, float] = (0.0, 1.0)
    tonal_center: str = ""
    sonic_palette: list[str] = field(default_factory=list)
    climax_candidates: list[int] = field(default_factory=list)
    suggested_arc: str = "narrative"
    chapter_boundaries: list[int] = field(default_factory=list)


def infer_intent(tracks: list[TrackMetadata]) -> PlaylistIntent:
    """Analyze track metadata to determine playlist narrative intent."""
    if not tracks:
        return PlaylistIntent()

    theme_counter: Counter[str] = Counter()
    for t in tracks:
        for tag in t.themes + t.vibes:
            theme_counter[tag] += 1
    dominant_themes = [tag for tag, _ in theme_counter.most_common(5)]

    intensities = [t.emotional_intensity for t in tracks if t.emotional_intensity is not None]
    if intensities:
        emotional_range = (min(intensities), max(intensities))
    else:
        emotional_range = (0.0, 1.0)

    stance_counter: Counter[str] = Counter()
    for t in tracks:
        if t.narrator_stance:
            stance_counter[t.narrator_stance] += 1
    tonal_center = stance_counter.most_common(1)[0][0] if stance_counter else ""

    texture_counter: Counter[str] = Counter()
    for t in tracks:
        if t.sonic_texture:
            texture_counter[t.sonic_texture] += 1
    sonic_palette = [tex for tex, _ in texture_counter.most_common(3)]

    if len(tracks) <= 3:
        n_climax = 1
    elif len(tracks) <= 5:
        n_climax = min(2, len(tracks))
    elif len(tracks) <= 15:
        n_climax = max(2, len(tracks) // 7)
    else:
        n_climax = max(2, len(tracks) // 10)
    
    sorted_by_intensity = sorted(
        [(t.track_id, t.emotional_intensity or 0.0) for t in tracks],
        key=lambda x: x[1],
        reverse=True,
    )
    climax_candidates = [tid for tid, _ in sorted_by_intensity[:n_climax]]

    chapter_boundaries = _detect_chapters(tracks)

    intensity_spread = emotional_range[1] - emotional_range[0]
    suggested_arc = "narrative" if intensity_spread > 0.4 else "wave"

    return PlaylistIntent(
        dominant_themes=dominant_themes,
        emotional_range=emotional_range,
        tonal_center=tonal_center,
        sonic_palette=sonic_palette,
        climax_candidates=climax_candidates,
        suggested_arc=suggested_arc,
        chapter_boundaries=chapter_boundaries,
    )


def _detect_chapters(tracks: list[TrackMetadata], window: int = 3) -> list[int]:
    """Detect chapter boundaries by sliding window Jaccard similarity drop."""
    if len(tracks) < 4:
        return []
    
    effective_window = min(window, len(tracks) // 2)
    if effective_window < 1:
        return []

    boundaries: list[int] = []
    for i in range(effective_window, len(tracks) - effective_window + 1):
        left_tags: set[str] = set()
        for t in tracks[i - effective_window:i]:
            left_tags.update(t.themes + t.vibes)
        right_tags: set[str] = set()
        for t in tracks[i:min(i + effective_window, len(tracks))]:
            right_tags.update(t.themes + t.vibes)

        if not left_tags and not right_tags:
            continue
        union = len(left_tags | right_tags)
        if union == 0:
            continue
        similarity = len(left_tags & right_tags) / union
        if similarity < 0.3:
            if not boundaries or i - boundaries[-1] >= effective_window:
                boundaries.append(i)

    return boundaries
