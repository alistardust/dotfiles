"""Tests for the configurable acceptance targets."""
from __future__ import annotations

import json

import pytest

from tests.gold.config import AcceptanceTargets, load_targets


def test_defaults_match_approved_targets():
    targets = AcceptanceTargets()
    assert targets.max_severe_mismatches == 0
    assert targets.min_recall == 0.95
    assert targets.max_review_burden_per_1k == 20.0
    assert targets.min_zero_intervention_rate == 0.80


def test_shipped_config_file_loads():
    """The committed acceptance.json parses into the expected defaults."""
    targets = load_targets()
    assert isinstance(targets, AcceptanceTargets)
    assert targets.max_severe_mismatches == 0
    assert targets.min_recall == 0.95


def test_env_override_is_honored(tmp_path, monkeypatch):
    override = tmp_path / "custom.json"
    override.write_text(json.dumps({"min_recall": 0.99, "max_severe_mismatches": 2}))
    monkeypatch.setenv("TUNESHIFT_GOLD_TARGETS", str(override))

    targets = load_targets()

    assert targets.min_recall == 0.99
    assert targets.max_severe_mismatches == 2
    # Unspecified fields fall back to defaults.
    assert targets.max_review_burden_per_1k == 20.0


def test_partial_override_keeps_defaults(tmp_path, monkeypatch):
    override = tmp_path / "partial.json"
    override.write_text(json.dumps({"max_review_burden_per_1k": 5.0}))
    monkeypatch.setenv("TUNESHIFT_GOLD_TARGETS", str(override))

    targets = load_targets()

    assert targets.max_review_burden_per_1k == 5.0
    assert targets.min_recall == 0.95


def test_unknown_keys_ignored(tmp_path, monkeypatch):
    override = tmp_path / "extra.json"
    override.write_text(json.dumps({"min_recall": 0.9, "bogus": 123}))
    monkeypatch.setenv("TUNESHIFT_GOLD_TARGETS", str(override))

    targets = load_targets()

    assert targets.min_recall == 0.9
    assert not hasattr(targets, "bogus")


def test_malformed_config_fails_loudly(tmp_path, monkeypatch):
    override = tmp_path / "bad.json"
    override.write_text("{not valid json")
    monkeypatch.setenv("TUNESHIFT_GOLD_TARGETS", str(override))

    with pytest.raises(ValueError):
        load_targets()


def test_missing_config_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNESHIFT_GOLD_TARGETS", str(tmp_path / "does-not-exist.json"))
    targets = load_targets()
    assert targets == AcceptanceTargets()
