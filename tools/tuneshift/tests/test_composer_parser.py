from tuneshift.composer.models import TransitionType
from tuneshift.composer.parser import (
    _extract_track_mentions,
    _fuzzy_match_track,
    parse_enhanced_narrative,
)

NARRATIVE = """OPENING (1-2): Gentle introduction, setting the scene with vulnerable introspection.
BUILD (3-8): Rising tension, discovering identity. Builds from quiet realization to active claiming.
TURN (9-10): The shift - from internal to external. Sharp cut into defiance.
WRATH (11-18): Fury and defiance. Unrelenting anger. Required: Transgender Dysphoria Blues.
EXHALE (19): The collapse after the storm. Drone and quiet.
COMEBACK (20): Future starts now. Build back up.
BECOMING (21-25): Triumphant self-possession. Empowerment anthem territory.
ANTHEM (26): True Trans Soul Rebel closes the set. Required: True Trans Soul Rebel."""

# The REAL Trans Wrath narrative (parenthetical track mentions in prose)
REAL_NARRATIVE = """OPENING (1-2): The setup. A Southern preacher's sermon on motherhood, then the bright facade of American normalcy that's already rotting underneath.

BUILD (3-8): Vulnerability, finding self. Dysphoria named quietly, a plea against abandonment, surviving transition ("I got my name... I didn't crumple and die"), difficult love, and faith curdling into disillusionment.

TURN (9-10): Dread. Wendy Carlos's Shining theme signals something has shifted. Revolution Lover ignites the fuse.

WRATH (11-18): Fury. Naming the pain directly (Transgender Dysphoria Blues), then seduction-as-annihilation (Gibson Girl), patriarchal indictment (Violent Men), total refusal (Black Me Out), identity as constructed weapon (Faceshopping), unapologetic swagger (Dang), chaotic defiance (Hollywood Baby), campy menace (There Will Be Blood).

EXHALE (19): Punish. Seven minutes of drone and shame and collapse. The body after the storm.

COMEBACK (20): Future Starts Now. The door kicks back open.

BECOMING (21-25): Empowerment. The body affirmed (Body Was Made), the self declared (I Am Her), permission to feel (It's Okay to Cry), transcendence (Immaterial), inevitability (We're from the Future).

ANTHEM (26): True Trans Soul Rebel. Fist in the air. Crowd singing along. "Does God bless your transsexual heart?" """

REAL_TRACKLIST = [
    "Family Tree (Intro)",
    "American Teenager",
    "This Is Home",
    "Hope There's Someone",
    "100 Summers",
    "Nettles",
    "Daughter",
    "Sun Bleached Flies",
    "Main Title (The Shining)",
    "Revolution Lover",
    "Transgender Dysphoria Blues",
    "Gibson Girl",
    "Violent Men",
    "Black Me Out",
    "Faceshopping",
    "Dang",
    "Hollywood Baby",
    "There Will Be Blood",
    "Punish",
    "Future Starts Now",
    "Body Was Made",
    "I Am Her",
    "It's Okay to Cry",
    "Immaterial",
    "G.L.O.S.S. (We're from the Future)",
    "True Trans Soul Rebel",
]


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


# --- Tests for parenthetical track extraction (the real format) ---


def test_fuzzy_match_exact() -> None:
    assert _fuzzy_match_track("Gibson Girl", REAL_TRACKLIST) == "Gibson Girl"


def test_fuzzy_match_substring() -> None:
    # "We're from the Future" should match "G.L.O.S.S. (We're from the Future)"
    result = _fuzzy_match_track("We're from the Future", REAL_TRACKLIST)
    assert result == "G.L.O.S.S. (We're from the Future)"


def test_fuzzy_match_no_false_positive_on_partial_overlap() -> None:
    # "I Am Her" should NOT match "I Am Here" (substring but extends into word)
    tracklist = ["I Am Here", "I Am Her"]
    result = _fuzzy_match_track("I Am Her", tracklist)
    assert result == "I Am Her"


def test_fuzzy_match_no_match() -> None:
    assert _fuzzy_match_track("Nonexistent Song Title", REAL_TRACKLIST) is None


def test_extract_track_mentions_from_wrath_section() -> None:
    description = (
        "Fury. Naming the pain directly (Transgender Dysphoria Blues), "
        "then seduction-as-annihilation (Gibson Girl), patriarchal indictment "
        "(Violent Men), total refusal (Black Me Out), identity as constructed "
        "weapon (Faceshopping), unapologetic swagger (Dang), chaotic defiance "
        "(Hollywood Baby), campy menace (There Will Be Blood)."
    )
    mentions = _extract_track_mentions(description, REAL_TRACKLIST)
    assert "Transgender Dysphoria Blues" in mentions
    assert "Gibson Girl" in mentions
    assert "Violent Men" in mentions
    assert "Black Me Out" in mentions
    assert "Faceshopping" in mentions
    assert "Dang" in mentions
    assert "Hollywood Baby" in mentions
    assert "There Will Be Blood" in mentions
    assert len(mentions) == 8


def test_extract_track_mentions_from_becoming_section() -> None:
    description = (
        "Empowerment. The body affirmed (Body Was Made), "
        "the self declared (I Am Her), permission to feel (It's Okay to Cry), "
        "transcendence (Immaterial), inevitability (We're from the Future)."
    )
    mentions = _extract_track_mentions(description, REAL_TRACKLIST)
    assert "Body Was Made" in mentions
    assert "I Am Her" in mentions
    assert "It's Okay to Cry" in mentions
    assert "Immaterial" in mentions
    assert "G.L.O.S.S. (We're from the Future)" in mentions
    assert len(mentions) == 5


def test_extract_skips_non_track_parens() -> None:
    # "(Intro)" is in _NON_TRACK_PARENS, but "Family Tree (Intro)" as a
    # track title should still be matchable when mentioned as the full name
    description = "A quiet start (intro) before the storm."
    mentions = _extract_track_mentions(description, REAL_TRACKLIST)
    assert mentions == []


def test_extract_skips_quoted_lyrics() -> None:
    # Quoted text in parens that doesn't match a track title
    description = 'Surviving transition ("I got my name... I didn\'t crumple and die").'
    mentions = _extract_track_mentions(description, REAL_TRACKLIST)
    assert mentions == []


def test_real_narrative_full_parse_with_tracklist() -> None:
    """The critical integration test: parse the REAL narrative with the REAL tracklist."""
    sections = parse_enhanced_narrative(REAL_NARRATIVE, tracklist=REAL_TRACKLIST)
    by_name = {s.name: s for s in sections}

    # WRATH should have 8 tracks pinned from parenthetical mentions
    assert len(by_name["WRATH"].required_tracks) == 8
    assert "Transgender Dysphoria Blues" in by_name["WRATH"].required_tracks
    assert "Gibson Girl" in by_name["WRATH"].required_tracks
    assert "There Will Be Blood" in by_name["WRATH"].required_tracks

    # BECOMING should have 5 tracks
    assert len(by_name["BECOMING"].required_tracks) == 5
    assert "Body Was Made" in by_name["BECOMING"].required_tracks
    assert "G.L.O.S.S. (We're from the Future)" in by_name["BECOMING"].required_tracks

    # Sections without parenthetical mentions should have empty required_tracks
    assert by_name["OPENING"].required_tracks == []

    # EXHALE, COMEBACK, ANTHEM have bare prose mentions (sentence-start titles)
    assert by_name["EXHALE"].required_tracks == ["Punish"]
    assert by_name["COMEBACK"].required_tracks == ["Future Starts Now"]
    assert by_name["ANTHEM"].required_tracks == ["True Trans Soul Rebel"]

    # TURN has Revolution Lover as a bare mention
    assert "Revolution Lover" in by_name["TURN"].required_tracks


def test_real_narrative_without_tracklist_extracts_nothing() -> None:
    """Without a tracklist, parenthetical mentions are not extracted."""
    sections = parse_enhanced_narrative(REAL_NARRATIVE)
    by_name = {s.name: s for s in sections}
    # No Required: annotations in the real narrative, so all empty
    assert by_name["WRATH"].required_tracks == []
    assert by_name["BECOMING"].required_tracks == []


def test_prose_mention_at_sentence_start() -> None:
    """Bare track titles at sentence boundaries are detected."""
    description = "Punish. Seven minutes of drone and shame."
    tracklist = ["Punish", "Some Other Track", "Seven"]
    from tuneshift.composer.parser import _extract_prose_track_mentions

    # "Punish" starts a sentence; "Seven" is mid-sentence (< 4 chars anyway)
    found = _extract_prose_track_mentions(description, tracklist, set())
    assert "Punish" in found


def test_prose_mention_skips_mid_sentence() -> None:
    """Titles that appear mid-sentence are not extracted (false positive risk)."""
    description = "The fury of Gibson Girl echoes through."
    tracklist = ["Gibson Girl"]
    from tuneshift.composer.parser import _extract_prose_track_mentions

    found = _extract_prose_track_mentions(description, tracklist, set())
    assert found == []


def test_prose_mention_skips_short_titles() -> None:
    """Titles shorter than 4 chars are skipped to avoid false positives."""
    description = "Fly. That was unexpected."
    tracklist = ["Fly"]
    from tuneshift.composer.parser import _extract_prose_track_mentions

    # "Fly" is 3 chars, too short to match as bare prose mention
    found = _extract_prose_track_mentions(description, tracklist, set())
    assert found == []


def test_prose_mention_after_colon() -> None:
    """Titles after ': ' are detected (section description continuation)."""
    description = "The door kicks back open: Future Starts Now is the anthem."
    tracklist = ["Future Starts Now"]
    from tuneshift.composer.parser import _extract_prose_track_mentions

    found = _extract_prose_track_mentions(description, tracklist, set())
    assert "Future Starts Now" in found
