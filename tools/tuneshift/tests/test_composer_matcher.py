from tuneshift.composer.matcher import match_tracks_to_sections
from tuneshift.composer.models import EnhancedSection, PlaylistConcept
from tuneshift.sequencer.metadata import TrackMetadata


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


def test_match_tracks_to_sections_without_concept_assigns_all_tracks() -> None:
    sections = [
        EnhancedSection("OPENING", 1, 1, "Gentle intro", 0.2, "vulnerable", 1),
        EnhancedSection("WRATH", 2, 2, "Fury and defiance", 0.9, "defiant", 1),
    ]
    tracks = [
        _track(1, emotional_intensity=0.2, narrator_stance="vulnerable", vibes=["gentle"]),
        _track(2, emotional_intensity=0.9, narrator_stance="defiant", vibes=["fury"]),
    ]
    result = match_tracks_to_sections(tracks, sections, None)
    assigned_ids = {
        track.track_id
        for section_tracks in result.assignments.values()
        for track in section_tracks
    }
    assert assigned_ids == {1, 2}
    assert result.unassigned == []


def test_match_tracks_to_sections_pins_required_tracks() -> None:
    sections = [
        EnhancedSection(
            "WRATH",
            1,
            2,
            "Fury and defiance",
            0.9,
            "defiant",
            2,
            required_tracks=["Transgender Dysphoria Blues"],
        )
    ]
    tracks = [
        _track(1, title="Transgender Dysphoria Blues", emotional_intensity=0.9),
        _track(2, title="Other Song", emotional_intensity=0.8),
    ]
    result = match_tracks_to_sections(tracks, sections, PlaylistConcept(theme="trans rage"))
    assert result.assignments["WRATH"][0].title == "Transgender Dysphoria Blues"


def test_match_tracks_to_sections_does_not_duplicate_required_track() -> None:
    sections = [
        EnhancedSection(
            "WRATH",
            1,
            2,
            "Fury and defiance",
            0.9,
            "defiant",
            2,
            required_tracks=["Pinned Song"],
        )
    ]
    tracks = [
        _track(1, title="Pinned Song", emotional_intensity=0.9, narrator_stance="defiant"),
        _track(2, title="Backup", emotional_intensity=0.8, narrator_stance="defiant"),
    ]
    result = match_tracks_to_sections(tracks, sections, PlaylistConcept(theme="rage"))
    assigned_ids = [track.track_id for track in result.assignments["WRATH"]]
    assert assigned_ids.count(1) == 1


def test_match_tracks_to_sections_prefers_high_intensity_tracks_for_intense_sections() -> None:
    sections = [
        EnhancedSection("OPENING", 1, 2, "Gentle and quiet", 0.2, "vulnerable", 2, mood=["peaceful"]),
        EnhancedSection("WRATH", 3, 4, "Fury and defiance", 0.95, "defiant", 2, mood=["fury", "defiant"]),
    ]
    tracks = [
        _track(1, emotional_intensity=0.1, narrator_stance="vulnerable", vibes=["peaceful"]),
        _track(2, emotional_intensity=0.2, narrator_stance="vulnerable", vibes=["gentle"]),
        _track(3, emotional_intensity=0.95, narrator_stance="defiant", vibes=["fury"]),
        _track(4, emotional_intensity=0.85, narrator_stance="angry", vibes=["defiant"]),
    ]
    result = match_tracks_to_sections(tracks, sections, PlaylistConcept(theme="transformation"))
    wrath_ids = {track.track_id for track in result.assignments["WRATH"]}
    assert wrath_ids == {3, 4}


def test_match_tracks_to_sections_flags_misfits() -> None:
    sections = [
        EnhancedSection("WRATH", 1, 1, "Fury and defiance", 0.95, "defiant", 1, mood=["fury", "defiant"])
    ]
    tracks = [
        _track(1, emotional_intensity=0.05, narrator_stance="peaceful", vibes=["calm"], themes=["rest"])
    ]
    result = match_tracks_to_sections(tracks, sections, PlaylistConcept(theme="anger"))
    assert len(result.misfits) == 1
    assert result.misfits[0].track.track_id == 1
    assert result.misfits[0].fitness_score < 0.3
