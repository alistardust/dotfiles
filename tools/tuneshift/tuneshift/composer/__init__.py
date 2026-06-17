"""Narrative playlist composer package."""

from tuneshift.composer.gap_analyzer import analyze_composition_gaps
from tuneshift.composer.matcher import match_tracks_to_sections
from tuneshift.composer.models import (
    Candidate,
    ComposeResult,
    EnhancedSection,
    GapReport,
    GapSpec,
    MisfitTrack,
    PlaylistConcept,
    ReviewFinding,
    SectionAssignments,
    TransitionType,
)
from tuneshift.composer.parser import parse_enhanced_narrative
from tuneshift.composer.reviewer import review_composition
from tuneshift.composer.sequencer import sequence_sections
from tuneshift.sequencer.metadata import TrackMetadata


def compose_playlist(
    tracks: list[TrackMetadata],
    narrative: str,
    concept: PlaylistConcept | None = None,
) -> ComposeResult:
    """Run the end-to-end narrative composition pipeline."""
    tracklist = [t.title for t in tracks]
    sections = parse_enhanced_narrative(narrative, tracklist=tracklist)
    assignments = match_tracks_to_sections(tracks, sections, concept=concept)
    gaps = analyze_composition_gaps(assignments, sections)
    ordered = sequence_sections(assignments, sections)
    findings = review_composition(ordered, assignments, sections, concept=concept)
    return ComposeResult(
        ordered_tracks=ordered,
        assignments=assignments,
        gaps=gaps,
        review_findings=findings,
    )

__all__ = [
    "Candidate",
    "ComposeResult",
    "EnhancedSection",
    "GapReport",
    "GapSpec",
    "MisfitTrack",
    "PlaylistConcept",
    "ReviewFinding",
    "SectionAssignments",
    "TransitionType",
    "compose_playlist",
]
