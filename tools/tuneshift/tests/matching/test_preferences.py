"""Tests for the canonical preference model, cascade, and DB round-trip."""
from tuneshift.matching.preferences import (
    Preferences,
    VersionPreferences,
    preference_sort_bias,
    resolve_preferences,
)


class TestCascade:
    def test_defaults_when_all_layers_empty(self) -> None:
        prefs = resolve_preferences(None, None, None)
        assert prefs == Preferences()
        assert prefs.is_default()

    def test_global_applies_over_defaults(self) -> None:
        prefs = resolve_preferences({"avoid": ["remix"]}, None, None)
        assert prefs.avoid == ["remix"]
        # unspecified keys keep defaults
        assert "studio" in prefs.prefer

    def test_playlist_overrides_global(self) -> None:
        prefs = resolve_preferences(
            {"prefer": ["studio"], "avoid": ["live"]},
            {"prefer": ["live"], "avoid": []},
            None,
        )
        assert prefs.prefer == ["live"]
        assert prefs.avoid == []

    def test_track_overrides_playlist_and_global(self) -> None:
        prefs = resolve_preferences(
            {"prefer": ["studio"]},
            {"prefer": ["live"]},
            {"prefer": ["acoustic"]},
        )
        assert prefs.prefer == ["acoustic"]

    def test_partial_layers_merge_independently(self) -> None:
        prefs = resolve_preferences(
            {"avoid": ["remix"]},
            {"duration_tolerance_percent": 5.0},
            None,
        )
        assert prefs.avoid == ["remix"]
        assert prefs.duration_tolerance_percent == 5.0
        assert "studio" in prefs.prefer


class TestIsDefault:
    def test_fresh_preferences_are_default(self) -> None:
        assert Preferences().is_default()

    def test_customised_preferences_are_not_default(self) -> None:
        assert not Preferences(avoid=["remix"]).is_default()

    def test_version_preferences_alias(self) -> None:
        assert VersionPreferences is Preferences


class TestSortBias:
    def test_default_preferences_yield_zero_bias(self) -> None:
        # Even with keywords present, defaults must be a strict no-op.
        assert preference_sort_bias("Live at Wembley", Preferences()) == 0

    def test_avoided_keyword_lowers_bias(self) -> None:
        prefs = Preferences(prefer=["studio"], avoid=["live"])
        assert preference_sort_bias("Live at Wembley", prefs) < 0

    def test_preferred_keyword_raises_bias(self) -> None:
        prefs = Preferences(prefer=["acoustic"], avoid=["live"])
        assert preference_sort_bias("Acoustic Sessions", prefs) > 0

    def test_no_keyword_match_is_neutral(self) -> None:
        prefs = Preferences(prefer=["acoustic"], avoid=["live"])
        assert preference_sort_bias("Studio Album", prefs) == 0
