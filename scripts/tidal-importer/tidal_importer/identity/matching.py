"""Fuzzy matching for track identity resolution using rapidfuzz."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

_REMASTER_RE = re.compile(
    r"\s*[\(\[]\s*"
    r"(?:\d{4}\s*)?"
    r"(?:Remastered|Remaster|Deluxe Edition|Deluxe|Mono|Stereo|"
    r"Expanded Edition|Expanded|Anniversary|Bonus Track|Super Deluxe)"
    r"[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_FEAT_RE = re.compile(
    r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring)\s+[^\)\]]*[\)\]]",
    re.IGNORECASE,
)
_FEAT_INLINE_RE = re.compile(
    r"\s+(?:feat\.?|ft\.?|featuring)\s+.+$",
    re.IGNORECASE,
)
_THE_PREFIX_RE = re.compile(r"^the\s+", re.IGNORECASE)


def normalize_title_for_search(title: str) -> str:
    """Normalize a title for fuzzy comparison."""
    title = _REMASTER_RE.sub("", title)
    title = _FEAT_RE.sub("", title)
    title = _FEAT_INLINE_RE.sub("", title)
    return title.strip().casefold()


def normalize_artist_for_search(artist: str) -> str:
    """Normalize an artist name for search. Strips 'The', 'feat.', etc."""
    artist = _FEAT_INLINE_RE.sub("", artist)
    artist = _FEAT_RE.sub("", artist)
    artist = _THE_PREFIX_RE.sub("", artist)
    artist = artist.replace("&", "and")
    return artist.strip().casefold()


def match_title(query: str, candidate: str) -> float:
    """Score how well two titles match. Returns 0.0-1.0."""
    q = normalize_title_for_search(query)
    c = normalize_title_for_search(candidate)
    return fuzz.token_set_ratio(q, c) / 100.0


def duration_matches(
    reference_ms: int | None,
    candidate_ms: int | None,
    tolerance_ms: int = 10000,
) -> bool:
    """Check if two durations are within tolerance."""
    if reference_ms is None or candidate_ms is None:
        return True
    return abs(reference_ms - candidate_ms) <= tolerance_ms
