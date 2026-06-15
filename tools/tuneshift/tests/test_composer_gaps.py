from tuneshift.composer.gap_analyzer import analyze_composition_gaps
from tuneshift.composer.models import EnhancedSection, SectionAssignments, TransitionType
from tuneshift.sequencer.metadata import TrackMetadata


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


def _section(
    name: str,
    *,
    capacity: int,
    min_tracks: int = 1,
    implied_intensity: float = 0.5,
    implied_stance: str | None = None,
    mood: list[str] | None = None,
    transition_in: TransitionType = TransitionType.GRADUAL,
    transition_out: TransitionType = TransitionType.GRADUAL,
) -> EnhancedSection:
    return EnhancedSection(
        name=name,
        start_position=1,
        end_position=capacity,
        description=f"{name} section",
        implied_intensity=implied_intensity,
        implied_stance=implied_stance,
        capacity=capacity,
        min_tracks=min_tracks,
        mood=mood or [],
        transition_in=transition_in,
        transition_out=transition_out,
    )


def test_underfilled_section_detection() -> None:
    section = _section("BUILD", capacity=4, min_tracks=2, implied_intensity=0.8)
    assignments = SectionAssignments(
        assignments={"BUILD": [_track(1), _track(2), _track(3)]},
        misfits=[],
        unassigned=[],
    )

    gaps = analyze_composition_gaps(assignments, [section])

    gap = next(gap for gap in gaps if gap.gap_type == "empty_slot")
    assert gap.section_name == "BUILD"
    assert gap.severity < 0.8


def test_no_gap_when_section_is_full() -> None:
    section = _section("OPENING", capacity=2, min_tracks=2)
    assignments = SectionAssignments(
        assignments={"OPENING": [_track(1, energy=0.2), _track(2, energy=0.4)]},
        misfits=[],
        unassigned=[],
    )

    gaps = analyze_composition_gaps(assignments, [section])

    assert gaps == []


def test_critical_gap_below_min_tracks() -> None:
    section = _section("WRATH", capacity=4, min_tracks=3, implied_intensity=0.9)
    assignments = SectionAssignments(
        assignments={"WRATH": [_track(1, energy=0.9)]},
        misfits=[],
        unassigned=[],
    )

    gaps = analyze_composition_gaps(assignments, [section])

    gap = next(gap for gap in gaps if gap.gap_type == "empty_slot")
    assert gap.severity >= 0.8
    assert "1/3" in gap.description


def test_transition_gap_for_collapse() -> None:
    collapse = _section(
        "COLLAPSE",
        capacity=1,
        transition_out=TransitionType.COLLAPSE,
    )
    aftermath = _section("AFTERMATH", capacity=1)
    assignments = SectionAssignments(
        assignments={
            "COLLAPSE": [_track(1, energy=0.8, energy_arc_within="surging")],
            "AFTERMATH": [_track(2, energy=0.2)],
        },
        misfits=[],
        unassigned=[],
    )

    gaps = analyze_composition_gaps(assignments, [collapse, aftermath])

    gap = next(gap for gap in gaps if gap.gap_type == "transition_gap")
    assert gap.section_name == "COLLAPSE"
    assert "collapse" in gap.description.lower()


def test_monotony_detection() -> None:
    section = _section("MID", capacity=3)
    assignments = SectionAssignments(
        assignments={
            "MID": [
                _track(1, energy=0.50),
                _track(2, energy=0.54),
                _track(3, energy=0.57),
            ]
        },
        misfits=[],
        unassigned=[],
    )

    gaps = analyze_composition_gaps(assignments, [section])

    gap = next(gap for gap in gaps if gap.gap_type == "monotony")
    assert gap.severity > 0.4


def test_fill_spec_generation() -> None:
    section = _section(
        "ASCENT",
        capacity=3,
        min_tracks=2,
        implied_intensity=0.7,
        implied_stance="defiant",
        mood=["urgent", "glowing"],
        transition_out=TransitionType.BUILD,
    )
    assignments = SectionAssignments(
        assignments={"ASCENT": [_track(1)]},
        misfits=[],
        unassigned=[],
    )

    gaps = analyze_composition_gaps(assignments, [section])

    gap = next(gap for gap in gaps if gap.gap_type == "empty_slot")
    assert gap.fill_spec is not None
    assert gap.fill_spec.section_name == "ASCENT"
    assert gap.fill_spec.mood == ["urgent", "glowing"]
    assert gap.fill_spec.stance == "defiant"
    assert "build" in gap.fill_spec.keywords
