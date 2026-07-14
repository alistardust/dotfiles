"""Classify a concept rule into an enforcement kind, and parse era/year ranges.

Pure and I/O-free so it is trivially testable. The router lets ``review`` send
each rule to the right enforcer instead of only recognizing
``artist must be <tag>``.
"""

from __future__ import annotations

import enum
import re

_ARTIST_MUST_BE_RE = re.compile(r"artist must be \w+", re.IGNORECASE)
# A YYYY-YYYY / YYYY to YYYY / YYYY and YYYY range.
_YEAR_RANGE_RE = re.compile(
    r"\b((?:19|20)\d{2})\b\s*(?:-|to|through|and)\s*\b((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_DECADE_RE = re.compile(r"\b((?:19|20)\d0)s\b", re.IGNORECASE)
_SINGLE_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
# Words that signal a lone year is meant as an era/release constraint.
_ERA_HINT_RE = re.compile(
    r"\b(release[ds]?|era|year|decade|before|after|from|since|in|between)\b",
    re.IGNORECASE,
)


class RuleKind(enum.Enum):
    """The enforcement path a concept rule takes."""

    ARTIST_TAG = "artist_tag"
    ERA = "era"
    THEMATIC = "thematic"


def parse_era(text: str) -> tuple[int, int] | None:
    """Parse an inclusive ``(lo, hi)`` year range from a rule/era string, or None.

    Conservative on purpose: a lone 4-digit number is treated as an era only when
    an era hint word ("released", "year", "decade", ...) is present, so ordinary
    numbers in prose rules are not misread as year constraints.
    """
    if not text:
        return None
    m = _YEAR_RANGE_RE.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (min(lo, hi), max(lo, hi))
    d = _DECADE_RE.search(text)
    if d:
        base = int(d.group(1))
        return (base, base + 9)
    years = _SINGLE_YEAR_RE.findall(text)
    if len(years) == 1 and _ERA_HINT_RE.search(text):
        year = int(years[0])
        return (year, year)
    return None


def classify_rule(rule: str) -> RuleKind:
    """Route a rule to its enforcement kind.

    ``artist must be <tag>`` keeps its exact existing form; a rule carrying a
    year range/decade is an era rule; everything else is thematic (LLM-judged).
    """
    stripped = (rule or "").strip()
    if _ARTIST_MUST_BE_RE.match(stripped):
        return RuleKind.ARTIST_TAG
    if parse_era(stripped) is not None:
        return RuleKind.ERA
    return RuleKind.THEMATIC
