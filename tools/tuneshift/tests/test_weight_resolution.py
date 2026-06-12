"""Tests for weight resolution cascade in sequencer."""

import pytest

from tuneshift.sequencer.scoring import DIMENSION_SCORERS, DEFAULT_WEIGHTS, PRESETS, resolve_weights


class TestResolveWeights:
    """Test 3-level weight resolution cascade."""

    def test_cli_weights_override_everything(self) -> None:
        """CLI weights take highest priority."""
        cli = {"narrative_arc": 0.1}
        db = {"narrative_arc": 0.9, "energy_flow": 0.5}
        result = resolve_weights(cli_weights=cli, db_weights=db, preset_name=None)
        assert result["narrative_arc"] == 0.1  # CLI wins
        assert result["energy_flow"] == 0.5  # falls through to DB

    def test_db_weights_override_preset(self) -> None:
        """DB weights override preset values."""
        db = {"narrative_arc": 0.8}
        result = resolve_weights(cli_weights=None, db_weights=db, preset_name="energy-wave")
        assert result["narrative_arc"] == 0.8  # DB wins over preset

    def test_preset_provides_base(self) -> None:
        """Preset supplies default weights when CLI/DB absent."""
        result = resolve_weights(cli_weights=None, db_weights=None, preset_name="narrative-queen")
        assert result == PRESETS["narrative-queen"]

    def test_no_weights_returns_equal_blend(self) -> None:
        """All dimensions present at equal weight when nothing specified."""
        result = resolve_weights(cli_weights=None, db_weights=None, preset_name=None)
        # All dimensions present at equal weight
        assert len(result) == len(DIMENSION_SCORERS)
        assert all(v == 0.5 for v in result.values())
        assert set(result.keys()) == set(DIMENSION_SCORERS.keys())

    def test_cascade_preserves_all_dimensions(self) -> None:
        """All dimensions are present in result regardless of override level."""
        cli = {"energy_flow": 0.2}
        db = {"mood_continuity": 0.7}
        result = resolve_weights(cli_weights=cli, db_weights=db, preset_name="discovery")
        assert len(result) == len(DIMENSION_SCORERS)
        assert result["energy_flow"] == 0.2  # CLI
        assert result["mood_continuity"] == 0.7  # DB
        # Other dimensions come from preset
        assert result["variety"] == PRESETS["discovery"]["variety"]

    def test_partial_overrides_preserve_lower_levels(self) -> None:
        """Partial overrides at one level don't wipe out lower levels."""
        # Only override one dimension at DB level
        db = {"energy_flow": 0.1}
        result = resolve_weights(cli_weights=None, db_weights=db, preset_name="mood-bath")
        assert result["energy_flow"] == 0.1  # DB override
        # All other dimensions should come from preset
        for dim, weight in PRESETS["mood-bath"].items():
            if dim != "energy_flow":
                assert result[dim] == weight

    def test_invalid_preset_falls_back_to_default(self) -> None:
        """Unknown preset name falls back to default weights."""
        result = resolve_weights(cli_weights=None, db_weights=None, preset_name="nonexistent")
        assert result == DEFAULT_WEIGHTS
