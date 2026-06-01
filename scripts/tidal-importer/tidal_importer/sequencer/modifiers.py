"""Context-aware scoring modifiers for the sequence optimizer.

Each modifier returns a float multiplier (~0.3-1.3) that adjusts the base
pairwise similarity score based on recent sequence history and narrative intent.
"""
from collections import Counter
from dataclasses import dataclass, field

from tidal_importer.sequencer.cache import TrackMetadata


SCORE_FLOOR = 0.05


@dataclass
class SequenceContext:
    """Running state tracked during greedy sequence construction."""

    recent_tracks: list[TrackMetadata] = field(default_factory=list)
    seen_artists: dict[str, int] = field(default_factory=dict)  # artist -> last position
    recent_themes: Counter = field(default_factory=Counter)  # theme/vibe -> count in window
    recent_energies: list[float] = field(default_factory=list)
    position: int = 0
    total: int = 0
    narrative_mode: str = "river"
    context_window: int = 5

    def advance(self, track: TrackMetadata) -> None:
        """Update context after placing a track."""
        self.recent_tracks.append(track)
        if len(self.recent_tracks) > self.context_window:
            self.recent_tracks = self.recent_tracks[-self.context_window:]

        self.seen_artists[track.artist] = self.position

        # Update theme bag (sliding window)
        self.recent_themes = Counter()
        for t in self.recent_tracks:
            for tag in t.themes + t.vibes:
                self.recent_themes[tag] += 1

        energy = track.energy if track.energy is not None else 0.5
        self.recent_energies.append(energy)
        if len(self.recent_energies) > self.context_window:
            self.recent_energies = self.recent_energies[-self.context_window:]

        self.position += 1


def artist_recency_penalty(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Penalize candidates whose artist appeared recently.

    Aggressive decay curve that counteracts inflated base scores caused by
    identical classification data for same-artist tracks. The penalty must
    be strong enough to overcome a ~0.95 base score vs ~0.5 for different
    artists.
    """
    if candidate.artist not in context.seen_artists:
        return 1.0

    last_pos = context.seen_artists[candidate.artist]
    distance = context.position - last_pos

    if distance <= 0:
        return 0.10 * strength + (1.0 - strength)

    decay_table = {1: 0.10, 2: 0.15, 3: 0.25, 4: 0.40, 5: 0.55, 6: 0.70, 7: 0.82, 8: 0.90, 9: 0.95}
    raw_penalty = decay_table.get(distance, 1.0)

    # Blend toward 1.0 based on strength (strength=0 means no penalty)
    return raw_penalty * strength + 1.0 * (1.0 - strength)


def artist_variety_bonus(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Bonus for artists not yet heard in the playlist."""
    if candidate.artist not in context.seen_artists:
        return 1.0 + 0.12 * strength
    return 1.0


def subgenre_staleness_penalty(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Penalize if candidate's themes/vibes overlap heavily with recent window."""
    if not context.recent_themes:
        return 1.0

    candidate_tags = set(candidate.themes + candidate.vibes)
    if not candidate_tags:
        return 1.0

    # What fraction of candidate's tags are already saturating the window?
    window_size = len(context.recent_tracks) or 1
    saturation = 0.0
    for tag in candidate_tags:
        # A tag appearing in every recent track = fully saturated
        saturation += context.recent_themes.get(tag, 0) / window_size

    # Normalize by number of candidate tags
    avg_saturation = saturation / len(candidate_tags)

    # Penalty kicks in above 0.6 saturation
    if avg_saturation <= 0.6:
        return 1.0

    penalty = 1.0 - 0.3 * ((avg_saturation - 0.6) / 0.4)
    penalty = max(0.7, penalty)
    return penalty * strength + 1.0 * (1.0 - strength)


def era_diversity_bonus(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Bonus for tracks from a different era than recent tracks."""
    if not context.recent_tracks or not candidate.era_mood:
        return 1.0

    recent_eras: set[str] = set()
    for t in context.recent_tracks:
        recent_eras.update(t.era_mood)

    if not recent_eras:
        return 1.0

    candidate_eras = set(candidate.era_mood)
    overlap = len(candidate_eras & recent_eras)
    total_candidate = len(candidate_eras) or 1

    # If candidate brings entirely new eras, bonus
    novelty = 1.0 - (overlap / total_candidate)
    if novelty > 0.5:
        return 1.0 + 0.08 * strength
    return 1.0


def energy_monotony_penalty(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Penalize tracks that continue an energy flatline."""
    if len(context.recent_energies) < 3:
        return 1.0

    # Check variance of recent energies
    mean = sum(context.recent_energies) / len(context.recent_energies)
    variance = sum((e - mean) ** 2 for e in context.recent_energies) / len(context.recent_energies)

    # Low variance = monotone
    if variance > 0.02:
        return 1.0  # enough variation, no penalty

    # How close is candidate energy to the flatline mean?
    candidate_energy = candidate.energy if candidate.energy is not None else 0.5
    deviation_from_mean = abs(candidate_energy - mean)

    if deviation_from_mean > 0.15:
        # Candidate breaks the flatline: bonus
        return 1.0 + 0.1 * strength
    else:
        # Candidate continues the flatline: penalty
        return (0.85) * strength + 1.0 * (1.0 - strength)


def narrative_arc_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Narrative-mode-specific modifier.

    - river: penalizes stagnation and jarring jumps
    - chapter: after similar run, boosts contrast
    - dj_set: penalizes deviation from arc energy target
    """
    mode = context.narrative_mode

    if mode == "river":
        return _river_modifier(candidate, context, strength)
    elif mode == "chapter":
        return _chapter_modifier(candidate, context, strength)
    elif mode == "dj_set":
        return _dj_set_modifier(candidate, context, strength)
    return 1.0


def _river_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float,
) -> float:
    """River: reward gradual drift, penalize stagnation or jarring jumps."""
    if not context.recent_tracks:
        return 1.0

    current = context.recent_tracks[-1]

    # Compute theme drift from current track
    current_tags = set(current.themes + current.vibes)
    candidate_tags = set(candidate.themes + candidate.vibes)

    if not current_tags or not candidate_tags:
        return 1.0

    overlap = len(current_tags & candidate_tags)
    union = len(current_tags | candidate_tags)
    similarity = overlap / union if union > 0 else 0.5

    # Sweet spot: 0.3-0.7 similarity (gradual drift)
    if 0.3 <= similarity <= 0.7:
        return 1.0 + 0.05 * strength  # small bonus for gradual drift
    elif similarity > 0.9:
        return (0.9) * strength + 1.0 * (1.0 - strength)  # too similar (stagnation)
    elif similarity < 0.1:
        return (0.9) * strength + 1.0 * (1.0 - strength)  # too jarring
    return 1.0


def _chapter_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float,
) -> float:
    """Chapter: after N similar tracks in a row, boost contrast."""
    if len(context.recent_tracks) < 3:
        return 1.0

    # Check if recent tracks are all very similar (a "chapter")
    recent_tags_list = [set(t.themes + t.vibes) for t in context.recent_tracks[-3:]]
    if not all(recent_tags_list):
        return 1.0

    # Pairwise jaccard among recent 3
    similarities = []
    for i in range(len(recent_tags_list)):
        for j in range(i + 1, len(recent_tags_list)):
            a, b = recent_tags_list[i], recent_tags_list[j]
            union = len(a | b)
            if union > 0:
                similarities.append(len(a & b) / union)

    avg_sim = sum(similarities) / len(similarities) if similarities else 0.0

    candidate_tags = set(candidate.themes + candidate.vibes)
    last_tags = recent_tags_list[-1]
    union = len(candidate_tags | last_tags)
    cand_sim = len(candidate_tags & last_tags) / union if union > 0 else 0.5

    if avg_sim > 0.7:
        # We've been in a chapter too long: boost contrast
        if cand_sim < 0.4:
            return 1.0 + 0.15 * strength  # contrast bonus
        elif cand_sim > 0.7:
            return (0.85) * strength + 1.0 * (1.0 - strength)  # penalty for more of the same
    return 1.0


def _dj_set_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float,
) -> float:
    """DJ set: reward tracks that fit the energy arc at this position."""
    import math

    if context.total <= 1:
        return 1.0

    frac = context.position / max(context.total - 1, 1)
    # Wave-shaped target: builds, peaks at 60%, winds down
    target_energy = 0.5 + 0.3 * math.sin(2 * math.pi * frac)

    candidate_energy = candidate.energy if candidate.energy is not None else 0.5
    deviation = abs(candidate_energy - target_energy)

    if deviation < 0.15:
        return 1.0 + 0.05 * strength
    elif deviation > 0.35:
        return (0.85) * strength + 1.0 * (1.0 - strength)
    return 1.0


def score_candidate(
    candidate: TrackMetadata,
    current: TrackMetadata,
    context: SequenceContext,
    base_score: float,
    penalty_strengths: dict[str, float] | None = None,
) -> float:
    """Apply all context modifiers to a base pairwise score.

    penalty_strengths keys: artist_recency, artist_variety, subgenre_staleness,
                           era_diversity, energy_monotony, narrative_arc
    Values are 0.0-1.0 strength multipliers (default 1.0 for all).
    """
    strengths = penalty_strengths or {}

    # Cap inflated base scores from identical classification data (same artist)
    # When two tracks share an artist, their classification similarity is artificial
    # (populated from the same artist-level heuristics). Deflate to a neutral score.
    effective_base = base_score
    if candidate.artist == current.artist:
        effective_base = min(base_score, 0.55)

    modifiers = [
        artist_recency_penalty(candidate, context, strengths.get("artist_recency", 1.0)),
        artist_variety_bonus(candidate, context, strengths.get("artist_variety", 1.0)),
        subgenre_staleness_penalty(candidate, context, strengths.get("subgenre_staleness", 1.0)),
        era_diversity_bonus(candidate, context, strengths.get("era_diversity", 1.0)),
        energy_monotony_penalty(candidate, context, strengths.get("energy_monotony", 1.0)),
        narrative_arc_modifier(candidate, context, strengths.get("narrative_arc", 1.0)),
    ]

    product = 1.0
    for m in modifiers:
        product *= m

    result = effective_base * product
    return max(result, SCORE_FLOOR)
