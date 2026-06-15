from tuneshift.composer.models import EnhancedSection, SectionAssignments, TransitionType
from tuneshift.composer.reviewer import review_composition
from tuneshift.sequencer.metadata import TrackMetadata


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": f"A{track_id}"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


def _section(
    name: str,
    start: int,
    end: int,
    *,
    required_tracks: list[str] | None = None,
    transition_out: TransitionType = TransitionType.GRADUAL,
    transition_in: TransitionType = TransitionType.GRADUAL,
) -> EnhancedSection:
    return EnhancedSection(
        name=name,
        start_position=start,
        end_position=end,
        description=f"{name} section",
        implied_intensity=0.5,
        implied_stance=None,
        capacity=end - start + 1,
        required_tracks=required_tracks or [],
        transition_out=transition_out,
        transition_in=transition_in,
    )


def test_review_detects_required_track_outside_section() -> None:
    opener = _track(1, title="Quiet Intro", energy=0.2)
    required = _track(2, title="Rage Song", energy=0.9)
    sections = [
        _section("OPENING", 1, 1),
        _section("WRATH", 2, 2, required_tracks=["Rage Song"]),
    ]
    assignments = SectionAssignments(
        assignments={"OPENING": [required], "WRATH": [opener]},
        misfits=[],
        unassigned=[],
    )

    findings = review_composition([opener, required], assignments, sections)

    assert any(finding.category == "section_integrity" for finding in findings)


def test_review_allows_good_sharp_cut_boundary() -> None:
    first = _track(1, title="Burn", energy=0.95)
    second = _track(2, title="Aftershock", energy=0.1)
    sections = [
        _section("IMPACT", 1, 1, transition_out=TransitionType.SHARP_CUT),
        _section("RELEASE", 2, 2),
    ]
    assignments = SectionAssignments(
        assignments={"IMPACT": [first], "RELEASE": [second]},
        misfits=[],
        unassigned=[],
    )

    findings = review_composition([first, second], assignments, sections)

    assert not any(finding.category == "transition_quality" for finding in findings)
