"""Records the current matching engine's gold-set metrics as the baseline.

This is the measured starting point every later chunk is a delta against.
The test asserts the runner executes and produces well-formed metrics; it
does NOT assert the acceptance targets are met yet, because the current engine
is known to have the weaknesses the overhaul exists to fix. Later chunks flip
the acceptance assertions on.

The recorded BASELINE.json is a git-ignored artifact (see .gitignore).
"""
from __future__ import annotations

import json
from pathlib import Path

from tests.gold.config import load_targets
from tests.gold.dataset import gold_cases
from tests.gold.runner import GoldMetrics, evaluate, run_gold_set

_BASELINE_PATH = Path(__file__).with_name("BASELINE.json")


def _record(metrics: GoldMetrics) -> None:
    payload = {
        "metrics": metrics.as_dict(),
        "targets": load_targets().as_dict(),
        "gate": evaluate(metrics),
    }
    _BASELINE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def test_runner_executes_and_records_baseline():
    metrics = run_gold_set()

    # Runner produced a result for every labeled case.
    assert metrics.total_cases == len(gold_cases())
    assert metrics.total_cases > 0
    assert len(metrics.case_results) == metrics.total_cases

    # Metrics are well-formed and within valid ranges.
    assert 0.0 <= metrics.recall <= 1.0
    assert 0.0 <= metrics.zero_intervention_rate <= 1.0
    assert metrics.review_burden_per_1k >= 0.0
    assert metrics.severe_mismatches >= 0
    assert metrics.should_match_cases + metrics.unavailable_cases == metrics.total_cases

    _record(metrics)
    assert _BASELINE_PATH.exists()

    # The recorded file round-trips and carries the target/gate structure.
    recorded = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    assert set(recorded) == {"metrics", "targets", "gate"}
    assert set(recorded["gate"]) == {
        "severe_mismatches", "recall", "review_burden", "zero_intervention"
    }


def test_run_is_deterministic():
    """Identical inputs must yield identical metrics across runs (0 drift)."""
    first = run_gold_set().as_dict()
    second = run_gold_set().as_dict()
    assert first == second


def test_evaluate_reports_all_targets():
    metrics = run_gold_set()
    gate = evaluate(metrics)
    assert set(gate) == {"severe_mismatches", "recall", "review_burden", "zero_intervention"}
    assert all(isinstance(v, bool) for v in gate.values())
