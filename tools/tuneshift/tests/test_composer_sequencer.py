from tuneshift.composer.models import EnhancedSection, SectionAssignments, TransitionType
from tuneshift.composer.sequencer import sequence_sections
from tuneshift.models import PlaylistPin
from tuneshift.sequencer.metadata import TrackMetadata


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": f"A{track_id}"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


def _section(
    name: str,
    *,
    capacity: int,
    transition_in: TransitionType = TransitionType.GRADUAL,
    transition_out: TransitionType = TransitionType.GRADUAL,
) -> EnhancedSection:
    return EnhancedSection(
        name=name,
        start_position=1,
        end_position=capacity,
        description=f"{name} section",
        implied_intensity=0.5,
        implied_stance=None,
        capacity=capacity,
        transition_in=transition_in,
        transition_out=transition_out,
    )


def test_preserves_section_order() -> None:
    opening = _section("OPENING", capacity=2)
    closer = _section("CLOSER", capacity=1)
    assignments = SectionAssignments(
        assignments={
            "OPENING": [_track(1, energy=0.3), _track(2, energy=0.4)],
            "CLOSER": [_track(3, energy=0.8)],
        },
        misfits=[],
        unassigned=[],
    )

    ordered = sequence_sections(assignments, [opening, closer])

    assert [track.track_id for track in ordered] == [1, 2, 3]


def test_unassigned_appended_at_end() -> None:
    opening = _section("OPENING", capacity=1)
    assignments = SectionAssignments(
        assignments={"OPENING": [_track(1, energy=0.3)]},
        misfits=[],
        unassigned=[_track(9, energy=0.9), _track(10, energy=0.1)],
    )

    ordered = sequence_sections(assignments, [opening])

    assert [track.track_id for track in ordered[-2:]] == [9, 10]


def test_build_section_trends_upward() -> None:
    build = _section("BUILD", capacity=3, transition_out=TransitionType.BUILD)
    assignments = SectionAssignments(
        assignments={
            "BUILD": [
                _track(1, energy=0.8),
                _track(2, energy=0.2),
                _track(3, energy=0.5),
            ]
        },
        misfits=[],
        unassigned=[],
    )

    ordered = sequence_sections(assignments, [build])

    assert [track.track_id for track in ordered] == [2, 3, 1]


def test_sharp_cut_maximizes_contrast_at_boundary() -> None:
    impact = _section("IMPACT", capacity=2, transition_out=TransitionType.SHARP_CUT)
    release = _section("RELEASE", capacity=3)
    assignments = SectionAssignments(
        assignments={
            "IMPACT": [
                _track(1, energy=0.3),
                _track(2, energy=0.95),
            ],
            "RELEASE": [
                _track(3, energy=0.85),
                _track(4, energy=0.1),
                _track(5, energy=0.75),
            ],
        },
        misfits=[],
        unassigned=[],
    )

    ordered = sequence_sections(assignments, [impact, release])

    ordered_ids = [track.track_id for track in ordered]
    assert ordered_ids[1] == 2
    assert ordered_ids[2] == 4
    assert set(ordered_ids) == {1, 2, 3, 4, 5}


# --- Pin support tests ---


def test_opener_pin_moves_track_to_first() -> None:
    sec_a = _section("A", capacity=2)
    sec_b = _section("B", capacity=2)
    assignments = SectionAssignments(
        assignments={
            "A": [_track(1, energy=0.3), _track(2, energy=0.4)],
            "B": [_track(3, energy=0.5), _track(4, energy=0.6)],
        },
        misfits=[],
        unassigned=[],
    )
    pins = [PlaylistPin(playlist_id=1, track_id=3, pin_type="opener")]

    ordered = sequence_sections(assignments, [sec_a, sec_b], pins=pins)

    assert ordered[0].track_id == 3


def test_closer_pin_moves_track_to_last() -> None:
    sec_a = _section("A", capacity=2)
    sec_b = _section("B", capacity=2)
    assignments = SectionAssignments(
        assignments={
            "A": [_track(1, energy=0.3), _track(2, energy=0.4)],
            "B": [_track(3, energy=0.5), _track(4, energy=0.6)],
        },
        misfits=[],
        unassigned=[],
    )
    pins = [PlaylistPin(playlist_id=1, track_id=1, pin_type="closer")]

    ordered = sequence_sections(assignments, [sec_a, sec_b], pins=pins)

    assert ordered[-1].track_id == 1


def test_opener_and_closer_pins_together() -> None:
    sec = _section("ALL", capacity=4)
    assignments = SectionAssignments(
        assignments={
            "ALL": [_track(1), _track(2), _track(3), _track(4)],
        },
        misfits=[],
        unassigned=[],
    )
    pins = [
        PlaylistPin(playlist_id=1, track_id=3, pin_type="opener"),
        PlaylistPin(playlist_id=1, track_id=1, pin_type="closer"),
    ]

    ordered = sequence_sections(assignments, [sec], pins=pins)

    assert ordered[0].track_id == 3
    assert ordered[-1].track_id == 1


def test_adjacent_group_keeps_tracks_together() -> None:
    sec = _section("ALL", capacity=5)
    assignments = SectionAssignments(
        assignments={
            "ALL": [_track(1), _track(2), _track(3), _track(4), _track(5)],
        },
        misfits=[],
        unassigned=[],
    )
    pins = [
        PlaylistPin(playlist_id=1, track_id=4, pin_type="anchor", group_id="grp", group_order=0),
        PlaylistPin(playlist_id=1, track_id=2, pin_type="anchor", group_id="grp", group_order=1),
    ]

    ordered = sequence_sections(assignments, [sec], pins=pins)

    ids = [t.track_id for t in ordered]
    idx_4 = ids.index(4)
    idx_2 = ids.index(2)
    assert idx_2 == idx_4 + 1


def test_opener_with_adjacent_group() -> None:
    """Opener pin + adjacent group: opener first, group member immediately after."""
    sec = _section("ALL", capacity=4)
    assignments = SectionAssignments(
        assignments={
            "ALL": [_track(1), _track(2), _track(3), _track(4)],
        },
        misfits=[],
        unassigned=[],
    )
    pins = [
        PlaylistPin(playlist_id=1, track_id=1, pin_type="opener"),
        PlaylistPin(playlist_id=1, track_id=2, pin_type="anchor", group_id="opener", group_order=1),
    ]

    ordered = sequence_sections(assignments, [sec], pins=pins)

    # Opener at position 0, adjacent group member at position 1
    assert ordered[0].track_id == 1
    assert ordered[1].track_id == 2
