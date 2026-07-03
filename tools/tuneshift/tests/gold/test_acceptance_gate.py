"""Live acceptance gate for the matching engine against the gold set.

These are the "flipped on" acceptance assertions the baseline test deferred.
As of the Chunk 4 intent-fidelity work the source-aware engine achieves:

* **zero severe mismatches** — the engine never *confidently* commits the wrong
  track. This is the single most important pillar (Alice: a bad confident pick
  is worse than a "not found") and is asserted hard here.
* **full recall** on the labeled should-match cases.
* **>= 80% zero-intervention** — most tracks resolve with no human review.

``max_review_burden_per_1k`` is intentionally NOT gated here yet: the seed gold
set has only ~12 cases, so a single review case is ~83/1k and the <=20/1k target
is mathematically unreachable until the set grows (that happens in the scale
chunk, which expands the dataset). The metric is still recorded and reported so
regressions are visible; it is asserted once the dataset is large enough.
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
