"""Review composed playlists for section integrity and transition quality."""

from __future__ import annotations

from tuneshift.composer.models import (
    EnhancedSection,
    PlaylistConcept,
    ReviewFinding,
    SectionAssignments,
    TransitionType,
)
from tuneshift.sequencer.metadata import TrackMetadata


def _energy_value(track: TrackMetadata) -> float:
    if track.energy is not None:
        return max(0.0, min(1.0, track.energy))
    if track.emotional_intensity is not None:
        return max(0.0, min(1.0, track.emotional_intensity))
    return 0.5


def _resolve_transition_type(
    current: EnhancedSection,
    nxt: EnhancedSection,
) -> TransitionType:
    if current.transition_out is not TransitionType.GRADUAL:
        return current.transition_out
    return nxt.transition_in


def _score_transition(
    transition_type: TransitionType,
    last_track: TrackMetadata,
    first_track: TrackMetadata,
) -> float:
    last_energy = _energy_value(last_track)
    first_energy = _energy_value(first_track)
    energy_delta = abs(last_energy - first_energy)

    if transition_type is TransitionType.SHARP_CUT:
        return min(1.0, energy_delta * 2)
    if transition_type is TransitionType.COLLAPSE:
        if last_energy > first_energy:
            return min(1.0, (last_energy - first_energy) * 2)
        return 0.2
    if transition_type is TransitionType.BUILD:
        if first_energy >= last_energy:
            return 1.0
        return max(0.3, 1.0 - energy_delta)
    if transition_type is TransitionType.GRADUAL:
        return max(0.0, 1.0 - energy_delta * 2)
    return max(0.0, 1.0 - energy_delta * 3)


def _review_section_integrity(
    ordered_tracks: list[TrackMetadata],
    assignments: SectionAssignments,
    sections: list[EnhancedSection],
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    positions = {track.track_id: index + 1 for index, track in enumerate(ordered_tracks)}

    for section in sections:
        for required_title in section.required_tracks:
            assigned_tracks = assignments.assignments.get(section.name, [])
            if not any(track.title.casefold() == required_title.casefold() for track in assigned_tracks):
                findings.append(
                    ReviewFinding(
                        category="section_integrity",
                        description=(
                            f'{section.name} does not contain required track "{required_title}" '
                            "in its assignment."
                        ),
                        severity=1.0,
                        section_name=section.name,
                    )
                )
                continue

            matching = [
                track
                for track in ordered_tracks
                if track.title.casefold() == required_title.casefold()
            ]
            if not matching:
                findings.append(
                    ReviewFinding(
                        category="section_integrity",
                        description=f'{section.name} is missing required track "{required_title}".',
                        severity=1.0,
                        section_name=section.name,
                    )
                )
                continue

            for track in matching:
                position = positions[track.track_id]
                if section.start_position <= position <= section.end_position:
                    break
            else:
                findings.append(
                    ReviewFinding(
                        category="section_integrity",
                        description=(
                            f'"{required_title}" falls outside the declared {section.name} '
                            "section range."
                        ),
                        severity=0.8,
                        section_name=section.name,
                    )
                )

    return findings


def _review_transition_quality(
    assignments: SectionAssignments,
    sections: list[EnhancedSection],
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []

    for index in range(len(sections) - 1):
        current = sections[index]
        nxt = sections[index + 1]
        current_tracks = assignments.assignments.get(current.name, [])
        next_tracks = assignments.assignments.get(nxt.name, [])
        if not current_tracks or not next_tracks:
            continue

        transition_type = _resolve_transition_type(current, nxt)
        quality = _score_transition(transition_type, current_tracks[-1], next_tracks[0])
        if quality >= 0.4:
            continue

        findings.append(
            ReviewFinding(
                category="transition_quality",
                description=(
                    f"{current.name} to {nxt.name} has weak {transition_type.value} "
                    f"boundary quality ({quality:.2f})."
                ),
                severity=1.0 - quality,
                section_name=current.name,
            )
        )

    return findings


def review_composition(
    ordered_tracks: list[TrackMetadata],
    assignments: SectionAssignments,
    sections: list[EnhancedSection],
    concept: PlaylistConcept | None = None,
) -> list[ReviewFinding]:
    """Review the section integrity and boundary quality of a composition."""
    del concept
    findings = _review_section_integrity(ordered_tracks, assignments, sections)
    findings.extend(_review_transition_quality(assignments, sections))
    return findings
