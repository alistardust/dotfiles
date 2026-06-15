"""Enhanced parser for composer narrative sections."""

from __future__ import annotations

import re

from tuneshift.composer.models import EnhancedSection, TransitionType
from tuneshift.sequencer.narrative_parser import _SECTION_PATTERN

_MOOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fury": ("fury", "wrath", "rage", "anger", "storm", "unrelenting"),
    "defiant": ("defiant", "defiance", "claiming", "rebel", "resist", "fight"),
    "vulnerable": (
        "vulnerable",
        "introspection",
        "introspective",
        "gentle",
        "quiet realization",
        "tender",
    ),
    "triumphant": (
        "triumphant",
        "empowerment",
        "empower",
        "anthem",
        "victory",
        "self-possession",
    ),
    "peaceful": ("peaceful", "quiet", "calm", "drone", "still", "exhale", "gentle"),
}

_HIGH_INTENSITY_WORDS = frozenset(
    {
        "fury",
        "wrath",
        "rage",
        "anger",
        "unrelenting",
        "defiance",
        "defiant",
        "anthem",
        "triumphant",
        "empowerment",
        "sharp",
    }
)
_LOW_INTENSITY_WORDS = frozenset(
    {
        "gentle",
        "quiet",
        "drone",
        "collapse",
        "aftermath",
        "still",
        "peaceful",
        "vulnerable",
        "intro",
        "introspection",
    }
)

_REQUIRED_TRACK_RE = re.compile(r"required:\s*([^.;]+)", re.IGNORECASE)
_REQUIRED_ARTIST_RE = re.compile(r"required artist:\s*([^.;]+)", re.IGNORECASE)


def _extract_moods(description: str) -> list[str]:
    text = description.lower()
    moods: list[str] = []
    for mood, keywords in _MOOD_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            moods.append(mood)
    return moods


def _estimate_intensity(name: str, description: str) -> float:
    text = f"{name} {description}".lower()
    words = re.findall(r"[a-z']+", text)
    high_hits = sum(1 for word in words if word in _HIGH_INTENSITY_WORDS)
    low_hits = sum(1 for word in words if word in _LOW_INTENSITY_WORDS)
    intensity = 0.5 + (high_hits * 0.12) - (low_hits * 0.1)
    return max(0.1, min(1.0, intensity))


def _estimate_stance(name: str, description: str) -> str | None:
    text = f"{name} {description}".lower()
    if any(word in text for word in ("defiant", "defiance", "rebel", "fight", "claiming")):
        return "defiant"
    if any(word in text for word in ("triumphant", "victory", "anthem", "empowerment", "self-possession")):
        return "triumphant"
    if any(word in text for word in ("vulnerable", "introspection", "gentle", "quiet realization")):
        return "vulnerable"
    if any(word in text for word in ("peaceful", "still", "calm", "drone")):
        return "peaceful"
    return None


def _infer_transition_in(description: str) -> TransitionType:
    text = description.lower()
    if "collapse" in text or "aftermath" in text:
        return TransitionType.COLLAPSE
    if "sharp cut" in text:
        return TransitionType.SHARP_CUT
    if "sustain" in text or "holds" in text:
        return TransitionType.SUSTAIN
    return TransitionType.GRADUAL


def _infer_transition_out(description: str) -> TransitionType:
    text = description.lower()
    if "sharp cut" in text:
        return TransitionType.SHARP_CUT
    if "builds" in text or "build back up" in text or "build up" in text or "rising tension" in text:
        return TransitionType.BUILD
    if "sustain" in text or "holds" in text:
        return TransitionType.SUSTAIN
    return TransitionType.GRADUAL


def _section_concept(description: str) -> str | None:
    cleaned = _REQUIRED_TRACK_RE.sub("", description)
    cleaned = _REQUIRED_ARTIST_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or None


def parse_enhanced_narrative(narrative: str | None) -> list[EnhancedSection]:
    """Parse structured narrative text into enhanced composer sections."""
    if not narrative:
        return []

    sections: list[EnhancedSection] = []
    for match in _SECTION_PATTERN.finditer(narrative):
        name = match.group(1)
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        description = match.group(4).strip()
        sections.append(
            EnhancedSection(
                name=name,
                start_position=start,
                end_position=end,
                description=description,
                implied_intensity=_estimate_intensity(name, description),
                implied_stance=_estimate_stance(name, description),
                capacity=end - start + 1,
                mood=_extract_moods(description),
                transition_in=_infer_transition_in(description),
                transition_out=_infer_transition_out(description),
                required_tracks=[item.strip() for item in _REQUIRED_TRACK_RE.findall(description)],
                required_artists=[item.strip() for item in _REQUIRED_ARTIST_RE.findall(description)],
                section_concept=_section_concept(description),
            )
        )

    return sections
