"""Live acceptance gate for the matching engine against the gold set.

These are the "flipped on" acceptance assertions the baseline test deferred.
As of the Chunk 4 intent-fidelity work the source-aware engine achieves:

* **zero severe mismatches** — the engine never *confidently* commits the wrong
  track. This is the single most important pillar (Alice: a bad confident pick
  is worse than a "not found") and is asserted hard here.
* **full recall** on the labeled should-match cases.
* **>= 80% zero-intervention** — most tracks resolve with no human review.

``max_review_burden_per_1k`` is the *production* target and is intentionally
NOT gated against this set: the gold set is adversarial (deliberately stuffed
with traps), so its ambiguity rate is far higher than a real library's and the
<=20/1k target is neither reachable nor meaningful here. It is verified against
real telemetry once that exists. What IS gated here is a *regression guard*:
the gold-set review burden must not exceed ``gold_burden_ceiling_per_1k`` (the
current measured burden plus modest headroom), so a change that inflates how
many cases the engine punts to review fails loudly — without padding the set
with easy cases to game the production rate.
"""
from __future__ import annotations

from tests.gold.config import load_targets
from tests.gold.runner import run_gold_set


def test_no_severe_mismatches():
    metrics = run_gold_set()
    targets = load_targets()
    severe = [r for r in metrics.case_results if r.severe_mismatch]
    assert metrics.severe_mismatches <= targets.max_severe_mismatches, (
        "engine confidently selected the wrong track for: "
        + ", ".join(r.case_id for r in severe)
    )


def test_recall_meets_target():
    metrics = run_gold_set()
    targets = load_targets()
    assert metrics.recall >= targets.min_recall, (
        f"recall {metrics.recall:.3f} < target {targets.min_recall:.3f}"
    )


def test_zero_intervention_meets_target():
    metrics = run_gold_set()
    targets = load_targets()
    assert metrics.zero_intervention_rate >= targets.min_zero_intervention_rate, (
        f"zero-intervention {metrics.zero_intervention_rate:.3f} "
        f"< target {targets.min_zero_intervention_rate:.3f}"
    )


def test_review_burden_no_regression():
    """Gold-set review burden must not regress past the recorded ceiling.

    This is the scale-chunk guard: not the absolute production <=20/1k target
    (deferred to real telemetry), but a ceiling on the adversarial set so that
    review inflation is caught immediately.
    """
    metrics = run_gold_set()
    targets = load_targets()
    assert metrics.review_burden_per_1k <= targets.gold_burden_ceiling_per_1k, (
        f"gold-set review burden {metrics.review_burden_per_1k:.1f}/1k regressed "
        f"past ceiling {targets.gold_burden_ceiling_per_1k:.1f}/1k"
    )
