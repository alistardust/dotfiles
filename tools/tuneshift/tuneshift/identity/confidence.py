"""Confidence scoring for identity resolution evidence."""

from __future__ import annotations

from tuneshift.identity.models import ConfidenceTier, Evidence


def compute_confidence(evidence: list[Evidence]) -> tuple[float, ConfidenceTier]:
    """Compute composite confidence score from evidence list.

    Sums individual evidence confidence values, capped at 1.0.
    Returns (score, tier).
    """
    if not evidence:
        return 0.0, ConfidenceTier.UNCERTAIN

    score = min(1.0, sum(item.confidence for item in evidence))
    tier = ConfidenceTier.from_score(score)
    return score, tier
