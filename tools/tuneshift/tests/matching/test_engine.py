"""Tests for matching.engine (Distance + recommend) and matching.confidence."""
import pytest

from tuneshift.matching import confidence as conf
from tuneshift.matching import engine as eng
from tuneshift.matching.penalties import SignalPenalty


def sig(name, points, penalty, weight):
    return SignalPenalty(name, points, penalty, weight)


# --- Distance.total ---

def test_total_empty_is_zero():
    assert eng.Distance().total == 0.0


def test_total_perfect_match():
    d = eng.Distance([sig("title", 50, 0.0, 50), sig("artist", 30, 0.0, 30)])
    assert d.total == 0.0


def test_total_worst_match():
    d = eng.Distance([sig("title", 0, 1.0, 50), sig("artist", 0, 1.0, 30)])
    assert d.total == 1.0


def test_total_weighted_average():
    # title perfect (w50, p0), artist worst (w30, p1) -> 30/80
    d = eng.Distance([sig("title", 50, 0.0, 50), sig("artist", 0, 1.0, 30)])
    assert d.total == pytest.approx(30 / 80)


def test_total_clamps_penalty_over_one():
    # a negative-bonus signal reports penalty 1.0 already, but guard anyway
    d = eng.Distance([sig("artist", -18, 1.5, 30)])
    assert d.total == 1.0


def test_points_is_raw_signed_sum():
    d = eng.Distance([sig("title", 50, 0.0, 50), sig("artist", -18, 1.0, 30), sig("version:live", -20, 1.0, 20)])
    assert d.points == 12


def test_breakdown_sorted_worst_first():
    d = eng.Distance([sig("title", 50, 0.0, 50), sig("artist", 0, 1.0, 30)])
    rows = d.breakdown
    assert rows[0].name == "artist"
    assert rows[0].contribution == 30.0
    assert rows[1].name == "title"
    assert rows[1].contribution == 0.0


# --- recommend: threshold ladder ---

def test_recommend_auto():
    d = eng.Distance([sig("title", 50, 0.0, 50), sig("artist", 30, 0.0, 30)])
    assert eng.recommend(d) is eng.Recommendation.AUTO


def test_recommend_suggest():
    # total 0.25 -> between auto_max(0.15) and suggest_max(0.35)
    d = eng.Distance([sig("a", 0, 0.25, 100)])
    assert eng.recommend(d) is eng.Recommendation.SUGGEST


def test_recommend_ask():
    d = eng.Distance([sig("a", 0, 0.50, 100)])
    assert eng.recommend(d) is eng.Recommendation.ASK


def test_recommend_reject():
    d = eng.Distance([sig("a", 0, 0.90, 100)])
    assert eng.recommend(d) is eng.Recommendation.REJECT


# --- recommend: gap criterion ---

def test_recommend_gap_downgrades_auto():
    d = eng.Distance([sig("title", 50, 0.05, 50)])  # total 0.05 -> AUTO
    # runner-up nearly as good (gap < gap_min 0.10) -> downgrade
    assert eng.recommend(d, runner_up=0.10) is eng.Recommendation.SUGGEST


def test_recommend_gap_preserves_auto_when_clear():
    d = eng.Distance([sig("title", 50, 0.05, 50)])
    assert eng.recommend(d, runner_up=0.40) is eng.Recommendation.AUTO


# --- recommend: max-rec caps ---

def test_hard_version_reject_caps_to_reject():
    # strings match perfectly but candidate is karaoke
    d = eng.Distance([sig("title", 50, 0.0, 50), sig("version:karaoke", -50, 1.0, 50)])
    assert d.capped_recommendation() is eng.Recommendation.REJECT
    assert eng.recommend(d) is eng.Recommendation.REJECT


def test_duration_penalty_caps_to_suggest():
    # perfect strings but duration off -> never AUTO
    d = eng.Distance([sig("title", 50, 0.0, 50), sig("duration", -20, 0.2, 20)])
    assert eng.recommend(d) is eng.Recommendation.SUGGEST


def test_cap_does_not_upgrade():
    # already REJECT by distance; a SUGGEST cap must not upgrade it
    d = eng.Distance([sig("a", 0, 0.9, 100), sig("duration", -10, 0.5, 20)])
    assert eng.recommend(d) is eng.Recommendation.REJECT


# --- confidence parity with legacy classify_results ---

CLASSIFY_CASES = [
    ([], "not_found"),
    ([40, 30], "not_found"),
    ([85, 60], "high"),
    ([85, 75], "ambiguous"),
    ([55, 52], "ambiguous"),
    ([90], "high"),
    ([49], "not_found"),
]


@pytest.mark.parametrize("scores, expected", CLASSIFY_CASES)
def test_classify_scores_parity(scores, expected):
    assert conf.classify_scores(scores) == expected


def test_classify_matches_legacy_function():
    from tuneshift.matching import classify_results
    for scores, _ in CLASSIFY_CASES:
        assert conf.classify_scores(scores) == classify_results(scores)
