from tuneshift.composer import compose_playlist
from tuneshift.composer.models import PlaylistConcept
from tuneshift.sequencer.metadata import TrackMetadata

NARRATIVE = """OPENING (1-2): Gentle vulnerable introduction.
BUILD (3-5): Rising tension, building defiance.
WRATH (6-8): Fury and defiance. Unrelenting. Required: Rage Song.
EXHALE (9): Collapse after the storm.
ANTHEM (10): Triumphant closer."""


def _track(track_id: int, title: str, **kwargs) -> TrackMetadata:
    defaults = {"artist": f"Artist {track_id}"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, title=title, **defaults)


def _full_track_set() -> list[TrackMetadata]:
    return [
        _track(1, "Soft Start", emotional_intensity=0.15, narrator_stance="vulnerable", vibes=["gentle"]),
        _track(2, "Tender Static", emotional_intensity=0.25, narrator_stance="vulnerable", vibes=["introspective"]),
        _track(3, "Spark", emotional_intensity=0.45, narrator_stance="defiant", vibes=["rising", "tension"]),
        _track(4, "Pressure Rise", emotional_intensity=0.58, narrator_stance="defiant", vibes=["building"]),
        _track(5, "Match Head", emotional_intensity=0.72, narrator_stance="defiant", vibes=["defiance"]),
        _track(6, "Rage Song", emotional_intensity=0.96, narrator_stance="defiant", vibes=["fury"]),
        _track(7, "Break Teeth", emotional_intensity=0.92, narrator_stance="defiant", vibes=["wrath"]),
        _track(8, "No Retreat", emotional_intensity=0.86, narrator_stance="defiant", vibes=["unrelenting"]),
        _track(
            9,
            "After the Fire",
            emotional_intensity=0.2,
            narrator_stance="peaceful",
            vibes=["collapse"],
            closes_with="fade",
            energy_arc_within="descending",
        ),
        _track(10, "Victory Cry", emotional_intensity=0.88, narrator_stance="triumphant", vibes=["anthem"]),
    ]


def test_compose_playlist_places_tracks_in_expected_sections() -> None:
    result = compose_playlist(_full_track_set(), NARRATIVE)

    assert {track.track_id for track in result.assignments.assignments["OPENING"]} == {1, 2}
    assert {track.track_id for track in result.assignments.assignments["BUILD"]} == {3, 4, 5}
    assert {track.track_id for track in result.assignments.assignments["WRATH"]} == {6, 7, 8}
    assert result.assignments.assignments["WRATH"][0].title == "Rage Song"
    assert {track.track_id for track in result.assignments.assignments["EXHALE"]} == {9}
    assert {track.track_id for track in result.assignments.assignments["ANTHEM"]} == {10}


def test_compose_playlist_detects_gaps_with_fewer_tracks() -> None:
    result = compose_playlist(_full_track_set()[:7], NARRATIVE)

    assert result.gaps
    assert any(gap.section_name in {"WRATH", "EXHALE", "ANTHEM"} for gap in result.gaps)


def test_compose_playlist_accepts_concept_and_returns_review_list() -> None:
    concept = PlaylistConcept(
        theme="transformation",
        hard_rules=["keep the collapse after the peak"],
        soft_rules=["end triumphant"],
    )

    result = compose_playlist(_full_track_set(), NARRATIVE, concept=concept)

    assert isinstance(result.review_findings, list)
    assert len(result.ordered_tracks) == 10
