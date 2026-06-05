"""Matching utilities for identity resolution."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

_TITLE_SUFFIX_RE = re.compile(
    r"\s*\(.*?(?:remaster|deluxe|edition|version|mix).*?\)",
    flags=re.IGNORECASE,
)
_THE_PREFIX_RE = re.compile(r"^the\s+", flags=re.IGNORECASE)


def normalize_title_for_search(title: str) -> str:
    """Normalize a title for search queries."""
    cleaned = _TITLE_SUFFIX_RE.sub("", title)
    return cleaned.strip()


def normalize_artist_for_search(artist: str) -> str:
    """Normalize an artist name for search queries."""
    cleaned = _THE_PREFIX_RE.sub("", artist)
    return cleaned.strip()


def match_title(query: str, candidate: str) -> float:
    """Fuzzy match two titles, returning a 0.0-1.0 similarity score."""
    query_clean = query.strip().lower()
    candidate_clean = candidate.strip().lower()
    if not query_clean or not candidate_clean:
        return 0.0
    if query_clean == candidate_clean:
        return 1.0

    normalized_query = normalize_title_for_search(query).lower()
    normalized_candidate = normalize_title_for_search(candidate).lower()
    normalized_score = fuzz.ratio(normalized_query, normalized_candidate) / 100.0
    if normalized_query == normalized_candidate:
        return 0.9
    return normalized_score


def duration_matches(
    reference_ms: int | None,
    candidate_ms: int | None,
    tolerance_ms: int = 10000,
) -> bool:
    """Check if two durations are within tolerance."""
    if reference_ms is None or candidate_ms is None:
        return True
    return abs(reference_ms - candidate_ms) <= tolerance_ms
