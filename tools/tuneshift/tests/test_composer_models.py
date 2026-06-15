from tuneshift.composer import (
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
from tuneshift.sequencer.metadata import TrackMetadata


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


def test_playlist_concept_has_hard_rules() -> None:
    concept = PlaylistConcept(theme="identity", hard_rules=["must include closer"])
    assert concept.has_hard_rules is True
    assert PlaylistConcept(theme="identity").has_hard_rules is False


def test_enhanced_section_defaults() -> None:
    section = EnhancedSection(
        name="OPENING",
        start_position=1,
        end_position=2,
        description="Gentle start",
        implied_intensity=0.2,
        implied_stance="vulnerable",
        capacity=2,
    )
    assert section.transition_in is TransitionType.GRADUAL
    assert section.transition_out is TransitionType.GRADUAL
    assert section.required_tracks == []
    assert section.min_tracks == 1


def test_gap_and_candidate_models_construct() -> None:
    gap = GapReport(
        gap_type="empty_slot",
        section_name="BUILD",
        description="Need more upward motion",
        severity=0.8,
        fill_spec=GapSpec(section_name="BUILD", mood=["defiant"]),
    )
    candidate = Candidate(
        title="Song",
        artist="Artist",
        source="library",
        fitness_score=0.91,
        track_id=42,
    )
    assert gap.fill_spec is not None
    assert gap.fill_spec.mood == ["defiant"]
    assert candidate.track_id == 42


def test_compose_result_holds_nested_models() -> None:
    track = _track(1, narrator_stance="defiant")
    assignments = SectionAssignments(
        assignments={"WRATH": [track]},
        misfits=[
            MisfitTrack(
                track=track,
                section_name="WRATH",
                fitness_score=0.2,
                explanation="Too calm",
            )
        ],
        unassigned=[],
    )
    result = ComposeResult(
        ordered_tracks=[track],
        assignments=assignments,
        gaps=[GapReport("concept_gap", "WRATH", "Missing anthem", 0.6)],
        review_findings=[ReviewFinding("flow", "Abrupt ending", 0.5, "WRATH")],
    )
    assert result.assignments.assignments["WRATH"][0].track_id == 1
    assert result.assignments.misfits[0].explanation == "Too calm"
    assert result.review_findings[0].section_name == "WRATH"
    assert result.candidates == {}
