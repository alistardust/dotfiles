"""Curation scoring engine: rate each track's contribution to the playlist."""

import statistics
from collections.abc import Callable

from tuneshift.curation.context import PlaylistContext
from tuneshift.sequencer.metadata import TrackMetadata


def _word_similarity(word1: str, word2: str) -> float:
    """Check semantic similarity between two words (handles synonyms and stems)."""
    w1, w2 = word1.lower(), word2.lower()
    if w1 == w2:
        return 1.0
    # Synonym groups
    synonyms = {
        "fury": {"rage", "wrath", "anger", "fury"},
        "rage": {"fury", "wrath", "anger", "rage"},
        "wrath": {"fury", "rage", "anger", "wrath"},
        "anger": {"fury", "rage", "wrath", "anger"},
        "defiant": {"defiance", "defiant"},
        "defiance": {"defiant", "defiance"},
        "empowerment": {"power", "empower", "empowerment"},
        "power": {"empowerment", "empower", "power"},
        "empower": {"empowerment", "power", "empower"},
        "trans": {"transgender", "trans"},
        "transgender": {"trans", "transgender"},
    }
    if w1 in synonyms and w2 in synonyms[w1]:
        return 0.85
    # Simple stem matching (suffix removal)
    if len(w1) > 3 and len(w2) > 3 and (w1.startswith(w2[:3]) or w2.startswith(w1[:3])):
        return 0.6
    return 0.0


def score_narrative_fit(
    track: TrackMetadata,
    ctx: PlaylistContext,
    pool: list,  # noqa: ARG001 - uniform scorer signature (dispatch table)
    selected: list | None = None,  # noqa: ARG001 - uniform scorer signature
) -> float | None:
    """Score how well this track serves the narrative goal.

    Returns ``None`` when there is nothing to judge, rather than a neutral
    0.5. An abstention is excluded from the mean; a 0.5 is a vote, and six
    dimensions voting 0.5 drown out the one dimension that has data.
    """
    if not ctx.goal and not ctx.narrative_sections:
        return None
    if not track.lyrical_subject and not track.themes:
        return None
    # Keyword overlap between goal text and track classification
    goal_words = set(ctx.goal.lower().split()) if ctx.goal else set()
    section_words = set()
    for section in ctx.narrative_sections:
        section_words.update(section.get("description", "").lower().split())
        section_words.add(section.get("name", "").lower())

    target_words = goal_words | section_words
    track_words = set()
    if track.lyrical_subject:
        track_words.add(track.lyrical_subject.lower())
    if track.narrator_stance:
        track_words.add(track.narrator_stance.lower())
    if track.themes:
        track_words.update(t.lower() for t in track.themes)

    if not target_words or not track_words:
        return None

    # Compute similarity between all word pairs
    total_similarity = 0.0
    max_similarities = 0
    for tword in track_words:
        max_sim = max(
            (_word_similarity(tword, gword) for gword in target_words), default=0.0
        )
        total_similarity += max_sim
        if max_sim > 0:
            max_similarities += 1

    base_score = total_similarity / max(len(track_words), 1) if track_words else 0.0

    # Boost for high emotional intensity when goal implies intensity
    intensity_boost = 0.0
    intensity_words = {"fury", "rage", "wrath", "defiance", "empowerment", "anger"}
    if target_words & intensity_words and track.emotional_intensity:
        intensity_boost = track.emotional_intensity * 0.2

    return min(1.0, base_score + intensity_boost)


def score_mood_contribution(
    track: TrackMetadata,
    ctx: PlaylistContext,
    pool: list,  # noqa: ARG001 - uniform scorer signature (dispatch table)
    selected: list | None = None,  # noqa: ARG001 - uniform scorer signature
) -> float | None:
    """Score how well this track contributes to the mood profile.

    Abstains when the playlist has no mood profile or the track is
    unclassified.
    """
    if not ctx.mood_profile:
        return None
    if not track.vibes and track.emotional_intensity is None:
        return None
    # Simple: check if track vibes overlap with mood_profile keywords
    mood_words = set()
    for _key, val in ctx.mood_profile.items():
        if isinstance(val, str):
            mood_words.add(val.lower())
    track_vibes = set(v.lower() for v in (track.vibes or []))
    if not mood_words or not track_vibes:
        return None
    overlap = len(mood_words & track_vibes) / max(len(mood_words), 1)
    return min(1.0, 0.3 + overlap * 0.7)


def score_sonic_role(
    track: TrackMetadata,
    ctx: PlaylistContext,  # noqa: ARG001 - uniform scorer signature (dispatch table)
    pool: list,
    selected: list | None = None,
) -> float | None:
    """Score the sonic diversity contribution of this track.

    Measured against the selection as it is built, so a texture only counts as
    distinctive while nothing like it has been kept.
    """
    if not track.sonic_texture and not track.instruments:
        return None
    company = pool if selected is None else selected
    other_textures = [getattr(t, "sonic_texture", None) for t in company if t != track]
    if track.sonic_texture and track.sonic_texture not in other_textures:
        return 0.7
    return 0.5


def _centre(values: list[float]) -> float | None:
    """The median of the values present, or None when there are none.

    The median rather than the mean, because a sparse loud tail drags a mean
    far enough up the scale to rank the tail above the playlist's own core.
    """
    return statistics.median(values) if values else None


def score_energy_role(
    track: TrackMetadata,
    ctx: PlaylistContext,  # noqa: ARG001 - uniform scorer signature (dispatch table)
    pool: list,
    selected: list | None = None,  # noqa: ARG001 - uniform scorer signature
) -> float | None:
    """Score how close this track sits to the playlist's energetic centre.

    Proximity, not rarity. A playlist whose mass sits in a narrow band is
    defined by that band, so scoring by scarcity would reward the outliers and
    cut the core, inverting the thing the playlist was curated for.

    The centre is taken from the whole pool rather than the surviving
    selection, so it does not drift as tracks are cut: the playlist's
    character is fixed by what was collected, not by what trimming has
    happened to leave behind.
    """
    if track.energy is None:
        return None
    centre_energy = _centre([t.energy for t in pool if t.energy is not None])
    if centre_energy is None:
        return None

    weighted = [(0.6, abs(track.energy - centre_energy))]
    centre_valence = _centre([t.valence for t in pool if t.valence is not None])
    if track.valence is not None and centre_valence is not None:
        weighted.append((0.4, abs(track.valence - centre_valence)))

    # Normalised by the weight actually used, so a track with no valence is
    # scored on the same scale as one that has it.
    penalty = sum(w * d for w, d in weighted) / sum(w for w, _ in weighted)
    return max(0.0, 1.0 - penalty)


def score_uniqueness(
    track: TrackMetadata,
    ctx: PlaylistContext,  # noqa: ARG001 - uniform scorer signature (dispatch table)
    pool: list,
    selected: list | None = None,
) -> float | None:
    """Score how unique this track is relative to the rest of the playlist."""
    if not track.themes and not track.vibes:
        return None
    track_signature = set(track.themes or []) | set(track.vibes or [])
    if not track_signature:
        return None
    company = pool if selected is None else selected
    similarities = []
    for other in company:
        if other == track:
            continue
        other_sig = set(getattr(other, "themes", None) or []) | set(
            getattr(other, "vibes", None) or []
        )
        if other_sig:
            overlap = len(track_signature & other_sig) / max(
                len(track_signature | other_sig), 1
            )
            similarities.append(overlap)
    if not similarities:
        return 0.8  # Only track = very unique
    avg_similarity = sum(similarities) / len(similarities)
    return 1.0 - avg_similarity


def score_redundancy(
    track: TrackMetadata,
    ctx: PlaylistContext,  # noqa: ARG001 - uniform scorer signature (dispatch table)
    pool: list,
    selected: list | None = None,
) -> float | None:
    """Score artist redundancy, counted against the selection as it is built.

    Counted against the whole pool this is a per-artist constant, which is how
    it came to decide trim on its own: every other dimension returned a
    constant, so ranking collapsed onto artist scarcity. Counted against the
    selection, cutting an artist's weakest track eases the pressure on the
    rest, which is what a listener means by "too much of one artist".

    This dimension only penalises. An artist who is not yet represented draws
    an abstention rather than a maximal score, because scoring it 1.0 would
    make a track with no classification data at all outrank a well-described
    one on the strength of having an unused artist name.

    High means not redundant.
    """
    company = pool if selected is None else selected
    artist_count = sum(
        1
        for t in company
        if getattr(t, "artist", "") == track.artist
        and getattr(t, "track_id", None) != track.track_id
    )
    if artist_count == 0:
        return None
    return 1.0 / (1.0 + artist_count)


CurationScorer = Callable[
    [TrackMetadata, PlaylistContext, list, list | None], float | None
]

CURATION_SCORERS: dict[str, CurationScorer] = {
    "narrative_fit": score_narrative_fit,
    "mood_contribution": score_mood_contribution,
    "sonic_role": score_sonic_role,
    "energy_role": score_energy_role,
    "uniqueness": score_uniqueness,
    "redundancy": score_redundancy,
}


def score_track_contribution(
    track: TrackMetadata,
    ctx: PlaylistContext,
    pool: list,
    selected: list | None = None,
) -> dict[str, float | None]:
    """Score a track across all curation dimensions.

    ``pool`` is the full candidate set and fixes the playlist's energetic
    centre. ``selected`` is what has been kept so far and is what the
    comparative dimensions measure against; it defaults to the pool, which is
    the right reading for analysis of a playlist that already exists.

    A dimension with nothing to judge returns ``None`` rather than a neutral
    score. Callers must exclude those from any average.
    """
    return {
        name: scorer(track, ctx, pool, selected)
        for name, scorer in CURATION_SCORERS.items()
    }


def mean_contribution(scores: dict[str, float | None]) -> float:
    """Average the dimensions that had something to say.

    Abstentions are excluded rather than averaged in as 0.5, which would pull
    every track toward the middle and compress the ranking into noise. A track
    no dimension could judge scores 0.5, which ties it with its peers instead
    of ranking it arbitrarily.
    """
    present = [v for v in scores.values() if v is not None]
    if not present:
        return 0.5
    return sum(present) / len(present)
