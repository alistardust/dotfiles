"""Configurable acceptance targets for the matching gold set.

The quality bars the matching engine must clear are policy, not code, so they
live in an editable JSON file (``acceptance.json`` next to this module) and fall
back to documented defaults. Override the file in place, or point
``TUNESHIFT_GOLD_TARGETS`` at an alternate JSON file, to tune the gates without
touching source.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

_CONFIG_FILE = Path(__file__).with_name("acceptance.json")
_ENV_OVERRIDE = "TUNESHIFT_GOLD_TARGETS"


@dataclass(frozen=True)
class AcceptanceTargets:
    """Thresholds the gold-set metrics are judged against.

    Defaults encode the approved targets: zero severe mismatches, at least 95%
    recall, no more than 20 review items per 1,000 tracks, and at least 80% of
    playlists needing no manual intervention.
    """

    max_severe_mismatches: int = 0
    min_recall: float = 0.95
    max_review_burden_per_1k: float = 20.0
    min_zero_intervention_rate: float = 0.80

    @classmethod
    def _field_names(cls) -> set[str]:
        return {f.name for f in fields(cls)}

    @classmethod
    def from_mapping(cls, data: dict) -> AcceptanceTargets:
        """Build targets from a mapping, ignoring unknown keys, over defaults."""
        known = cls._field_names()
        overrides = {k: v for k, v in data.items() if k in known}
        return cls(**{**asdict(cls()), **overrides})

    def as_dict(self) -> dict:
        return asdict(self)


def _config_path() -> Path:
    env_path = os.environ.get(_ENV_OVERRIDE)
    return Path(env_path) if env_path else _CONFIG_FILE


def load_targets() -> AcceptanceTargets:
    """Load acceptance targets from JSON config, falling back to defaults.

    A missing or empty config file yields the defaults. A malformed file raises
    ValueError so a broken gate configuration fails loudly rather than silently
    reverting to defaults.
    """
    path = _config_path()
    if not path.exists():
        return AcceptanceTargets()
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"Cannot read acceptance targets at {path}: {exc}") from exc
    if not raw:
        return AcceptanceTargets()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid acceptance targets JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Acceptance targets at {path} must be a JSON object")
    return AcceptanceTargets.from_mapping(data)
