"""Transition-aware sequencing for composed narrative sections."""

from __future__ import annotations

from tuneshift.composer.models import (
    EnhancedSection,
    SectionAssignments,
    TransitionType,
)
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.scoring import resolve_weights, score_pair


def sequence_sections(
    assignments: SectionAssignments,
    sections: list[EnhancedSection],
    weights: dict[str, float] | None = None,
) -> list[TrackMetadata]:
    """Sequence tracks within sections, then optimize section boundaries."""
    resolved_weights = resolve_weights(weights, None, None)
    ordered_by_section: dict[str, list[TrackMetadata]] = {}

    for section in sections:
        tracks = list(assignments.assignments.get(section.name, []))
        ordered_by_section[section.name] = _order_within_section(
            tracks,
            section,
            resolved_weights,
        )

    for index in range(len(sections) - 1):
        current = sections[index]
        nxt = sections[index + 1]
        current_tracks = ordered_by_section[current.name]
        next_tracks = ordered_by_section[nxt.name]
        if not current_tracks or not next_tracks:
            continue

        boundary_style = _resolve_transition_style(current, nxt)
        current_tracks = _select_closer(current_tracks, boundary_style)
        ordered_by_section[current.name] = current_tracks

        next_tracks = _select_opener(
            next_tracks,
            boundary_style,
            current_tracks[-1],
            resolved_weights,
        )
        ordered_by_section[nxt.name] = next_tracks

    ordered: list[TrackMetadata] = []
    for section in sections:
        ordered.extend(ordered_by_section[section.name])

    ordered.extend(assignments.unassigned)
    return ordered


def _order_within_section(
    tracks: list[TrackMetadata],
    section: EnhancedSection,
    weights: dict[str, float],
) -> list[TrackMetadata]:
    if len(tracks) < 2:
        return tracks

    if section.transition_out is TransitionType.BUILD:
        return sorted(tracks, key=_energy_value)

    if section.transition_out is TransitionType.COLLAPSE:
        return sorted(tracks, key=_energy_value, reverse=True)

    return _greedy_order(tracks, weights)


def _greedy_order(
    tracks: list[TrackMetadata],
    weights: dict[str, float],
) -> list[TrackMetadata]:
    if len(tracks) < 2:
        return tracks

    remaining = list(tracks)
    start = max(
        remaining,
        key=lambda track: _average_neighbor_score(track, remaining, weights),
    )
    ordered = [start]
    remaining.remove(start)

    while remaining:
        current = ordered[-1]
        next_track = max(
            remaining,
            key=lambda candidate: score_pair(current, candidate, weights),
        )
        ordered.append(next_track)
        remaining.remove(next_track)

    return ordered


def _average_neighbor_score(
    track: TrackMetadata,
    candidates: list[TrackMetadata],
    weights: dict[str, float],
) -> float:
    scores = [
        score_pair(track, candidate, weights)
        for candidate in candidates
        if candidate.track_id != track.track_id
    ]
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _select_closer(
    tracks: list[TrackMetadata],
    transition_type: TransitionType,
) -> list[TrackMetadata]:
    if len(tracks) < 2:
        return tracks

    closer_index = len(tracks) - 1
    if transition_type in {TransitionType.SHARP_CUT, TransitionType.BUILD}:
        closer_index = max(range(len(tracks)), key=lambda index: _energy_value(tracks[index]))
    elif transition_type is TransitionType.COLLAPSE:
        closer_index = max(
            range(len(tracks)),
            key=lambda index: _collapse_readiness(tracks[index]),
        )

    return _move_track(tracks, closer_index, len(tracks) - 1)


def _select_opener(
    tracks: list[TrackMetadata],
    transition_type: TransitionType,
    previous_closer: TrackMetadata,
    weights: dict[str, float],
) -> list[TrackMetadata]:
    if len(tracks) < 2:
        return tracks

    opener_index = 0
    if transition_type is TransitionType.SHARP_CUT:
        opener_index = max(
            range(len(tracks)),
            key=lambda index: _contrast_score(previous_closer, tracks[index], weights),
        )
    elif transition_type is TransitionType.COLLAPSE:
        opener_index = min(range(len(tracks)), key=lambda index: _energy_value(tracks[index]))
    else:
        opener_index = min(
            range(len(tracks)),
            key=lambda index: _contrast_score(previous_closer, tracks[index], weights),
        )

    return _move_track(tracks, opener_index, 0)


def _resolve_transition_style(
    current: EnhancedSection,
    nxt: EnhancedSection,
) -> TransitionType:
    if current.transition_out is not TransitionType.GRADUAL:
        return current.transition_out
    return nxt.transition_in


def _move_track(
    tracks: list[TrackMetadata],
    from_index: int,
    to_index: int,
) -> list[TrackMetadata]:
    updated = list(tracks)
    track = updated.pop(from_index)
    updated.insert(to_index, track)
    return updated


def _contrast_score(
    a: TrackMetadata,
    b: TrackMetadata,
    weights: dict[str, float],
) -> float:
    if a.energy is not None and b.energy is not None:
        return abs(a.energy - b.energy)
    return 1.0 - score_pair(a, b, weights)


def _collapse_readiness(track: TrackMetadata) -> float:
    fade_bonus = 0.35 if _is_fading(track) else 0.0
    return (1.0 - _energy_value(track)) + fade_bonus


def _is_fading(track: TrackMetadata) -> bool:
    markers = ("fade", "fading", "descending", "falling", "decay")
    arc = (track.energy_arc_within or "").lower()
    closing = (track.closes_with or "").lower()
    return any(marker in arc or marker in closing for marker in markers)


def _energy_value(track: TrackMetadata) -> float:
    if track.energy is not None:
        return max(0.0, min(1.0, track.energy))
    if track.emotional_intensity is not None:
        return max(0.0, min(1.0, track.emotional_intensity))
    return 0.5
