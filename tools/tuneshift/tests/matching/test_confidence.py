"""Tests for the configurable ambiguity delta (min_lead) in classify_scores."""
from tuneshift.matching import classify_scores


def test_default_boundaries_unchanged():
    # Clear winner: top >= 80, second < 70.
    assert classify_scores([92, 60]) == "high"
    # Near tie by second-max rule.
    assert classify_scores([92, 88]) == "ambiguous"
    # Below floor.
    assert classify_scores([40]) == "not_found"
    assert classify_scores([]) == "not_found"


def test_min_lead_zero_is_noop():
    assert classify_scores([92, 60], min_lead=0) == "high"


def test_min_lead_pushes_narrow_lead_to_ambiguous():
    # top=85, second=68 -> normally high (second < 70). A required lead of 20
    # is not met (gap=17), so it becomes ambiguous for review.
    assert classify_scores([85, 68]) == "high"
    assert classify_scores([85, 68], min_lead=20) == "ambiguous"


def test_min_lead_satisfied_stays_high():
    # gap of 25 >= required 20.
    assert classify_scores([90, 65], min_lead=20) == "high"


def test_min_lead_single_candidate_has_full_lead():
    # second defaults to 0, so a lone strong candidate always clears min_lead.
    assert classify_scores([88], min_lead=50) == "high"
