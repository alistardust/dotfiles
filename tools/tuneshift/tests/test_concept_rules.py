"""Concept rule-type router + era parser (Task 1)."""

from tuneshift.composer.rules import RuleKind, classify_rule, parse_era


def test_classify_artist_tag_rule():
    assert classify_rule("artist must be pop") is RuleKind.ARTIST_TAG


def test_classify_era_rule():
    assert classify_rule("released 1993-2003") is RuleKind.ERA
    assert classify_rule("1990s only") is RuleKind.ERA


def test_classify_thematic_rule():
    assert classify_rule("not about wanting a man") is RuleKind.THEMATIC


def test_parse_era_year_range():
    assert parse_era("released 1993-2003") == (1993, 2003)
    assert parse_era("1990s") == (1990, 1999)
    assert parse_era("between 1980 and 1989") == (1980, 1989)


def test_parse_era_none_when_absent():
    assert parse_era("not about wanting a man") is None


def test_parse_era_lone_year_needs_hint():
    # A bare 4-digit number without an era hint is not an era (avoid catching
    # song titles or unrelated numbers).
    assert parse_era("1999") is None
    assert parse_era("released in 1999") == (1999, 1999)
