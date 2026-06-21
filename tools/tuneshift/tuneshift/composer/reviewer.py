"""Review composed playlists for section integrity and transition quality."""

from __future__ import annotations

import re

from tuneshift.composer.models import (
    EnhancedSection,
    PlaylistConcept,
    ReviewFinding,
    SectionAssignments,
    TransitionType,
)
from tuneshift.models import Artist
from tuneshift.sequencer.metadata import TrackMetadata

# Pattern matchers for common hard/soft rules
_ARTIST_MUST_BE_RE = re.compile(r"artist must be (\w+)", re.IGNORECASE)
_NO_GENRE_RE = re.compile(r"no (\w+)", re.IGNORECASE)

# "queer" is an umbrella: any of these tags satisfies "artist must be queer"
_QUEER_UMBRELLA = frozenset({
    "queer", "gay", "lesbian", "bisexual", "trans", "nonbinary",
    "pansexual", "genderqueer", "genderfluid", "intersex", "asexual",
    "two-spirit", "questioning",
})


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


def _check_rule_against_artist(rule: str, artist: Artist) -> bool | None:
    """Check if an artist satisfies a rule. Returns True/False/None (can't determine)."""
    match = _ARTIST_MUST_BE_RE.match(rule)
    if match:
        required_tag = match.group(1).casefold()

        # "queer" is an umbrella: any LGBTQ+ tag satisfies it
        if required_tag == "queer":
            if artist.tags:
                artist_tags_lower = {t.casefold() for t in artist.tags}
                if artist_tags_lower & _QUEER_UMBRELLA:
                    return True
            # Check identity dict for sexuality/gender_identity
            if artist.identity:
                identity_values = " ".join(str(v) for v in artist.identity.values()).casefold()
                if any(term in identity_values for term in _QUEER_UMBRELLA):
                    return True
                if artist.identity_confidence == "confirmed":
                    return False
            if not artist.tags and not artist.identity:
                return None
            return False

        # Specific tag check (e.g., "artist must be trans")
        if not artist.tags:
            if artist.identity:
                identity_values = " ".join(str(v) for v in artist.identity.values()).casefold()
                if required_tag in identity_values:
                    return True
                if artist.identity_confidence == "confirmed":
                    return False
            return None
        return required_tag in [t.casefold() for t in artist.tags]
    return None  # rule pattern not recognized


def _review_concept_compliance(
    tracks: list[TrackMetadata],
    concept: PlaylistConcept,
    artist_lookup: dict[str, Artist],
) -> list[ReviewFinding]:
    """Check tracks against concept hard_rules and soft_rules."""
    findings: list[ReviewFinding] = []

    for track in tracks:
        artist_key = track.artist.casefold() if track.artist else ""
        artist = artist_lookup.get(artist_key)

        for rule in concept.hard_rules:
            if artist is None:
                findings.append(ReviewFinding(
                    category="concept_violation",
                    description=(
                        f'HARD: "{track.title}" by {track.artist} - '
                        f'Rule: "{rule}" - artist not in library, cannot verify'
                    ),
                    severity=0.5,
                    section_name=None,
                ))
                continue

            result = _check_rule_against_artist(rule, artist)
            if result is False:
                findings.append(ReviewFinding(
                    category="concept_violation",
                    description=(
                        f'HARD: "{track.title}" by {track.artist} - '
                        f'Rule: "{rule}" - FAILS '
                        f'(tags: {artist.tags}, confidence: {artist.identity_confidence})'
                    ),
                    severity=1.0,
                    section_name=None,
                ))
            elif result is None:
                findings.append(ReviewFinding(
                    category="concept_violation",
                    description=(
                        f'UNKNOWN: "{track.title}" by {track.artist} - '
                        f'Rule: "{rule}" - artist not enriched, cannot verify'
                    ),
                    severity=0.3,
                    section_name=None,
                ))

        for rule in concept.soft_rules:
            # Soft rules checked against track vibes/themes
            rule_words = set(re.findall(r"[a-z]+", rule.casefold()))
            track_words = set()
            for group in (track.vibes, track.themes):
                for item in group:
                    track_words.update(re.findall(r"[a-z]+", item.casefold()))
            if track.lyrical_subject:
                track_words.update(re.findall(r"[a-z]+", track.lyrical_subject.casefold()))

            # Check for contradiction: sad/dark in a happy/celebration playlist
            contradictions = {
                ("celebration", "joy", "pride", "happy", "upbeat"): {"sad", "depressing", "heartbreak", "grief", "mourning"},
            }
            for positive_set, negative_set in contradictions.items():
                if rule_words & set(positive_set) and track_words & negative_set:
                    findings.append(ReviewFinding(
                        category="soft_rule_mismatch",
                        description=(
                            f'"{track.title}" by {track.artist} - '
                            f'vibes [{", ".join(track.vibes)}] may not fit '
                            f'playlist mood: "{rule}"'
                        ),
                        severity=0.5,
                        section_name=None,
                    ))

    return findings


def _review_section_fitness(
    assignments: SectionAssignments,
    sections: list[EnhancedSection],
) -> list[ReviewFinding]:
    """Score each track against its assigned section's mood/intensity/stance."""
    findings: list[ReviewFinding] = []

    for section in sections:
        tracks = assignments.assignments.get(section.name, [])
        for track in tracks:
            score = 0.0
            checks = 0

            # Stance alignment
            if section.implied_stance and track.narrator_stance:
                checks += 1
                if track.narrator_stance.casefold() == section.implied_stance.casefold():
                    score += 1.0
                else:
                    score += 0.2

            # Intensity alignment
            if section.implied_intensity is not None:
                track_intensity = track.emotional_intensity or track.energy or 0.5
                checks += 1
                score += max(0.0, 1.0 - abs(track_intensity - section.implied_intensity))

            # Mood overlap
            if section.mood and track.vibes:
                checks += 1
                section_moods = {m.casefold() for m in section.mood}
                track_vibes = {v.casefold() for v in track.vibes}
                overlap = section_moods & track_vibes
                score += len(overlap) / max(len(section_moods), 1)

            if checks == 0:
                continue

            fitness = score / checks
            if fitness < 0.25:
                findings.append(ReviewFinding(
                    category="section_misfit",
                    description=(
                        f'"{track.title}" by {track.artist} - '
                        f'fitness {fitness:.2f} in {section.name} '
                        f'(section wants: {section.implied_stance or "any"} / '
                        f'{", ".join(section.mood) if section.mood else "any mood"})'
                    ),
                    severity=0.7,
                    section_name=section.name,
                ))

    return findings


def review_composition(
    ordered_tracks: list[TrackMetadata],
    assignments: SectionAssignments,
    sections: list[EnhancedSection],
    concept: PlaylistConcept | None = None,
    artist_lookup: dict[str, Artist] | None = None,
) -> list[ReviewFinding]:
    """Review section integrity, transition quality, and concept compliance."""
    findings = _review_section_integrity(ordered_tracks, assignments, sections)
    findings.extend(_review_transition_quality(assignments, sections))

    if sections:
        findings.extend(_review_section_fitness(assignments, sections))

    if concept and concept.has_hard_rules:
        findings.extend(_review_concept_compliance(
            ordered_tracks, concept, artist_lookup or {}
        ))
    elif concept and concept.soft_rules:
        findings.extend(_review_concept_compliance(
            ordered_tracks, concept, artist_lookup or {}
        ))

    return findings


def review_playlist(
    tracks: list[TrackMetadata],
    concept: PlaylistConcept | None = None,
    artist_lookup: dict[str, Artist] | None = None,
) -> list[ReviewFinding]:
    """Review a playlist for concept compliance without requiring narrative/sections.

    Use this for non-narrative playlists (e.g., Fruit Salad) where the composer
    pipeline isn't applicable but concept rules still need checking.
    """
    findings: list[ReviewFinding] = []
    if concept:
        findings.extend(_review_concept_compliance(
            tracks, concept, artist_lookup or {}
        ))
    return findings
