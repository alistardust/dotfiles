import pytest
from tuneshift.sequencer.narrative_parser import parse_narrative, NarrativeSection


class TestParseNarrative:
    def test_parses_trans_wrath_narrative(self) -> None:
        narrative = """OPENING (1-2): The setup. A Southern preacher's sermon.
WRATH (11-18): Fury. Naming the pain directly.
ANTHEM (26): True Trans Soul Rebel. Fist in the air."""
        sections = parse_narrative(narrative)
        assert len(sections) == 3
        assert sections[0].name == "OPENING"
        assert sections[0].start_position == 1
        assert sections[0].end_position == 2
        assert sections[1].name == "WRATH"
        assert sections[1].implied_intensity > 0.7
        assert sections[2].name == "ANTHEM"
        assert sections[2].capacity == 1

    def test_handles_single_position_section(self) -> None:
        narrative = "EXHALE (19): Seven minutes of drone."
        sections = parse_narrative(narrative)
        assert sections[0].start_position == 19
        assert sections[0].end_position == 19
        assert sections[0].capacity == 1

    def test_handles_empty_narrative(self) -> None:
        assert parse_narrative("") == []
        assert parse_narrative(None) == []

    def test_capacity_matches_range(self) -> None:
        narrative = "BUILD (3-8): Vulnerability."
        sections = parse_narrative(narrative)
        assert sections[0].capacity == 6  # positions 3,4,5,6,7,8

    def test_implied_intensity_mapping(self) -> None:
        narrative = """OPENING (1-2): Setup.
BUILD (3-8): Growing.
WRATH (11-18): FURY AND RAGE.
EXHALE (19): Collapse.
ANTHEM (26): Victory."""
        sections = parse_narrative(narrative)
        # WRATH should be high intensity (fury keywords)
        wrath = [s for s in sections if s.name == "WRATH"][0]
        assert wrath.implied_intensity > 0.7
        # EXHALE should be low intensity
        exhale = [s for s in sections if s.name == "EXHALE"][0]
        assert exhale.implied_intensity < 0.4
