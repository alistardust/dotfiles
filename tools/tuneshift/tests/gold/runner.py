"""Gold-set runner: score the current matching engine and emit metrics.

The runner ranks each case's candidate pool with the live scorer
(``score_match_with_version``) and classifies confidence with
``classify_results`` — the exact functions the reconciler relies on — then
derives the four headline metrics the overhaul is judged by:

* **recall** — fraction of "should-match" cases whose top-ranked candidate is
  the labeled correct id.
* **severe mismatches** — cases where the engine would *confidently* commit the
  wrong thing: a high-confidence pick that is not the expected id, or a
  confident pick on a case that should be unavailable. These are the dangerous
  failures the overhaul must drive to zero.
* **review burden per 1k** — ambiguous cases (surfaced for human review) scaled
  to a per-1,000-track rate.
* **zero-intervention rate** — fraction of cases resolved correctly with no
  human review required.

Results are deterministic for fixed inputs so later chunks can be scored as
deltas against the recorded baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tuneshift.matching import classify_results, score_match_with_version

from tests.gold.config import AcceptanceTargets, load_targets
from tests.gold.dataset import GoldCase, gold_cases


@dataclass(frozen=True)
class CaseResult:
    """Per-case scoring outcome."""

    case_id: str
    classification: str  # high | ambiguous | not_found
    selected_platform_id: str | None
    expected_platform_id: str | None
    top_score: int
    correct: bool
    severe_mismatch: bool
    needs_review: bool
    scores: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class GoldMetrics:
    """Aggregate metrics across the gold set."""

    total_cases: int
    should_match_cases: int
    unavailable_cases: int
    recall: float
    severe_mismatches: int
    review_burden_per_1k: float
    zero_intervention_rate: float
    case_results: list[CaseResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        summary = {
            "total_cases": self.total_cases,
            "should_match_cases": self.should_match_cases,
            "unavailable_cases": self.unavailable_cases,
            "recall": round(self.recall, 4),
            "severe_mismatches": self.severe_mismatches,
            "review_burden_per_1k": round(self.review_burden_per_1k, 2),
            "zero_intervention_rate": round(self.zero_intervention_rate, 4),
        }
        summary["cases"] = [
            {
                "case_id": r.case_id,
                "classification": r.classification,
                "selected": r.selected_platform_id,
                "expected": r.expected_platform_id,
                "top_score": r.top_score,
                "correct": r.correct,
                "severe_mismatch": r.severe_mismatch,
                "needs_review": r.needs_review,
            }
            for r in self.case_results
        ]
        return summary


def score_case(case: GoldCase) -> CaseResult:
    """Rank a single case with the live scorer and classify the outcome."""
    all_durations = [c.duration_seconds for c in case.candidates
                     if c.duration_seconds is not None]
    scored: list[tuple[str, int]] = []
    prefer = frozenset(case.prefer_classes)
    avoid = frozenset(case.avoid_classes)
    for candidate in case.candidates:
        score = score_match_with_version(
            case.source_title,
            case.source_artist,
            case.source_album,
            candidate.title,
            candidate.artist,
            candidate.album,
            result_duration=candidate.duration_seconds,
            reference_duration=case.source_duration_seconds,
            all_durations=all_durations or None,
            prefer=prefer,
            avoid=avoid,
        )
        scored.append((candidate.platform_id, score))

    classification = classify_results([s for _, s in scored])
    scored.sort(key=lambda pair: pair[1], reverse=True)
    top_id, top_score = scored[0] if scored else (None, 0)

    should_match = case.expected_platform_id is not None
    # A "confident" pick is one the reconciler would commit without asking.
    confident = classification == "high"
    selected_id = top_id if classification != "not_found" else None

    if should_match:
        correct = (
            classification != "not_found"
            and selected_id == case.expected_platform_id
        )
        # Confidently selecting a track that is not the expected one.
        severe_mismatch = confident and selected_id != case.expected_platform_id
        needs_review = classification == "ambiguous"
    else:
        # Correct outcome is "no acceptable match".
        correct = classification == "not_found"
        # Confidently committing any candidate for an unavailable track.
        severe_mismatch = confident
        needs_review = classification == "ambiguous"

    return CaseResult(
        case_id=case.id,
        classification=classification,
        selected_platform_id=selected_id,
        expected_platform_id=case.expected_platform_id,
        top_score=top_score,
        correct=correct,
        severe_mismatch=severe_mismatch,
        needs_review=needs_review,
        scores=dict(scored),
    )


def run_gold_set(cases: list[GoldCase] | None = None) -> GoldMetrics:
    """Score every case and aggregate the headline metrics."""
    cases = cases if cases is not None else gold_cases()
    results = [score_case(case) for case in cases]

    total = len(results)
    should_match = [r for r in results if r.expected_platform_id is not None]
    unavailable = [r for r in results if r.expected_platform_id is None]

    recall_hits = sum(1 for r in should_match if r.correct)
    recall = recall_hits / len(should_match) if should_match else 1.0

    severe = sum(1 for r in results if r.severe_mismatch)
    review_count = sum(1 for r in results if r.needs_review)
    review_burden_per_1k = (review_count / total * 1000) if total else 0.0

    zero_intervention = sum(1 for r in results if r.correct and not r.needs_review)
    zero_intervention_rate = zero_intervention / total if total else 1.0

    return GoldMetrics(
        total_cases=total,
        should_match_cases=len(should_match),
        unavailable_cases=len(unavailable),
        recall=recall,
        severe_mismatches=severe,
        review_burden_per_1k=review_burden_per_1k,
        zero_intervention_rate=zero_intervention_rate,
        case_results=results,
    )


def evaluate(metrics: GoldMetrics, targets: AcceptanceTargets | None = None) -> dict[str, bool]:
    """Return per-target pass/fail flags for the given metrics."""
    targets = targets if targets is not None else load_targets()
    return {
        "severe_mismatches": metrics.severe_mismatches <= targets.max_severe_mismatches,
        "recall": metrics.recall >= targets.min_recall,
        "review_burden": metrics.review_burden_per_1k <= targets.max_review_burden_per_1k,
        "zero_intervention": metrics.zero_intervention_rate >= targets.min_zero_intervention_rate,
    }
