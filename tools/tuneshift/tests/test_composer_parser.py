from tuneshift.composer.models import TransitionType
from tuneshift.composer.parser import parse_enhanced_narrative

NARRATIVE = """OPENING (1-2): Gentle introduction, setting the scene with vulnerable introspection.
BUILD (3-8): Rising tension, discovering identity. Builds from quiet realization to active claiming.
TURN (9-10): The shift - from internal to external. Sharp cut into defiance.
WRATH (11-18): Fury and defiance. Unrelenting anger. Required: Transgender Dysphoria Blues.
EXHALE (19): The collapse after the storm. Drone and quiet.
COMEBACK (20): Future starts now. Build back up.
BECOMING (21-25): Triumphant self-possession. Empowerment anthem territory.
ANTHEM (26): True Trans Soul Rebel closes the set. Required: True Trans Soul Rebel."""


def test_parse_enhanced_narrative_parses_all_sections() -> None:
    sections = parse_enhanced_narrative(NARRATIVE)
    assert [section.name for section in sections] == [
        "OPENING",
        "BUILD",
        "TURN",
        "WRATH",
        "EXHALE",
        "COMEBACK",
        "BECOMING",
        "ANTHEM",
    ]


def test_parse_enhanced_narrative_positions_and_capacity() -> None:
    sections = parse_enhanced_narrative(NARRATIVE)
    assert sections[0].start_position == 1
    assert sections[0].end_position == 2
    assert sections[0].capacity == 2
    assert sections[3].capacity == 8
    assert sections[-1].capacity == 1


def test_parse_enhanced_narrative_extracts_moods() -> None:
    sections = {section.name: section for section in parse_enhanced_narrative(NARRATIVE)}
    assert "vulnerable" in sections["OPENING"].mood
    assert "fury" in sections["WRATH"].mood
    assert "defiant" in sections["WRATH"].mood
    assert "triumphant" in sections["BECOMING"].mood
    assert "peaceful" in sections["EXHALE"].mood


def test_parse_enhanced_narrative_infers_transitions() -> None:
    sections = {section.name: section for section in parse_enhanced_narrative(NARRATIVE)}
    assert sections["TURN"].transition_out is TransitionType.SHARP_CUT
    assert sections["BUILD"].transition_out is TransitionType.BUILD
    assert sections["EXHALE"].transition_in is TransitionType.COLLAPSE
    assert sections["OPENING"].transition_out is TransitionType.GRADUAL


def test_parse_enhanced_narrative_extracts_required_tracks() -> None:
    sections = {section.name: section for section in parse_enhanced_narrative(NARRATIVE)}
    assert sections["WRATH"].required_tracks == ["Transgender Dysphoria Blues"]
    assert sections["ANTHEM"].required_tracks == ["True Trans Soul Rebel"]


def test_parse_enhanced_narrative_estimates_intensity_and_stance() -> None:
    sections = {section.name: section for section in parse_enhanced_narrative(NARRATIVE)}
    assert sections["WRATH"].implied_intensity > 0.8
    assert sections["EXHALE"].implied_intensity < 0.4
    assert sections["OPENING"].implied_stance == "vulnerable"
    assert sections["TURN"].implied_stance == "defiant"
    assert sections["BECOMING"].implied_stance == "triumphant"


def test_parse_enhanced_narrative_handles_empty_input() -> None:
    assert parse_enhanced_narrative("") == []
    assert parse_enhanced_narrative(None) == []


def test_parse_enhanced_narrative_extracts_required_artists() -> None:
    sections = parse_enhanced_narrative(
        "ALLY (1): Needs a feature. Required artist: Against Me!."
    )
    assert sections[0].required_artists == ["Against Me!"]
