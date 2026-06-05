"""Confidence scoring algorithm for track identity resolution."""

from __future__ import annotations

from tidal_importer.identity.models import ConfidenceTier, Evidence

DISCOGS_BONUS = 0.05
ITUNES_BONUS = 0.03
LASTFM_BONUS = 0.03
NON_ISRC_CAP = 0.94
ABSOLUTE_CAP = 0.99


def compute_confidence(evidence: list[Evidence]) -> tuple[float, ConfidenceTier]:
    """Compute confidence score from evidence list.

    Returns (score, tier) tuple. Deterministic 6-step algorithm.
    """
    if not evidence:
        return 0.0, ConfidenceTier.UNCERTAIN

    # Check for contradictions
    has_contradiction = any(e.evidence_type == "contradiction" for e in evidence)
    if has_contradiction:
        scores = [e.confidence for e in evidence if e.confidence >= 0.70]
        if len(scores) >= 2:
            score = min(scores)
            return score, ConfidenceTier.from_score(score)

    # Step 1: highest base score
    base_score = max(e.confidence for e in evidence)
    has_isrc = any(e.evidence_type == "isrc_match" for e in evidence)

    # Step 2: confirmation bonuses
    bonus = 0.0
    # Find primary source (first one providing the base score)
    primary_source = None
    for ev in evidence:
        if ev.confidence == base_score and primary_source is None:
            primary_source = ev.source
            break

    sources_seen = set()
    for ev in evidence:
        if ev.source in sources_seen:
            continue
        sources_seen.add(ev.source)
        if ev.source == primary_source:
            continue
        if ev.source == "discogs" and ev.evidence_type != "contradiction":
            bonus += DISCOGS_BONUS
        elif ev.source == "itunes":
            bonus += ITUNES_BONUS
        elif ev.source == "lastfm":
            bonus += LASTFM_BONUS

    score = base_score + bonus

    # Step 3: caps
    if not has_isrc:
        score = min(score, NON_ISRC_CAP)
    score = min(score, ABSOLUTE_CAP)

    return score, ConfidenceTier.from_score(score)
