import pytest
from tuneshift.sequencer.weights import resolve_weights, DEFAULT_WEIGHTS, PRESETS


class TestResolveWeights:
    def test_returns_default_when_none(self) -> None:
        w = resolve_weights(None, None)
        assert w == DEFAULT_WEIGHTS

    def test_preset_override(self) -> None:
        w = resolve_weights(None, "narrative-queen")
        assert w["narrative_arc"] == 0.9

    def test_custom_dict_used_directly(self) -> None:
        custom = {"energy_flow": 1.0, "variety": 0.5}
        w = resolve_weights(custom, None)
        assert w["energy_flow"] == 1.0
        assert w["variety"] == 0.5
        # Unspecified dimensions default to 0.0
        assert w.get("narrative_arc", 0.0) == 0.0

    def test_custom_overrides_preset(self) -> None:
        custom = {"narrative_arc": 0.5}
        w = resolve_weights(custom, "narrative-queen")
        # Custom wins over preset
        assert w["narrative_arc"] == 0.5

    def test_invalid_preset_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown preset"):
            resolve_weights(None, "nonexistent")
