"""Tests for the canonical preference model, cascade, and DB round-trip."""
from tuneshift.matching.preferences import (
    Preferences,
    VersionPreferences,
    preference_sort_bias,
    resolve_preferences,
    version_intent,
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

    def test_min_lead_defaults_to_zero(self) -> None:
        assert resolve_preferences(None, None, None).min_lead == 0

    def test_min_lead_cascades_and_track_wins(self) -> None:
        prefs = resolve_preferences(
            {"min_lead": 5},
            {"min_lead": 8},
            {"min_lead": 15},
        )
        assert prefs.min_lead == 15

    def test_min_lead_does_not_break_is_default(self) -> None:
        # A configured min_lead makes prefs non-default (byte-parity guard).
        assert not resolve_preferences({"min_lead": 10}, None, None).is_default()


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


class TestVersionIntent:
    def test_default_prefs_yield_empty_sets(self) -> None:
        # Critical guard: default avoid=(live,remix,...) must NOT leak into the
        # source-aware avoid set, or a live source would reject itself.
        prefer, avoid = version_intent(Preferences())
        assert prefer == frozenset()
        assert avoid == frozenset()

    def test_non_default_maps_recording_classes(self) -> None:
        prefer, avoid = version_intent(Preferences(prefer=["live"], avoid=["remix"]))
        assert prefer == frozenset({"live"})
        assert avoid == frozenset({"remix"})

    def test_packaging_keywords_are_dropped(self) -> None:
        # radio-edit / deluxe are not recording classes; only live survives.
        prefer, avoid = version_intent(
            Preferences(prefer=["live"], avoid=["radio-edit", "deluxe"])
        )
        assert prefer == frozenset({"live"})
        assert avoid == frozenset()

    def test_studio_kept_as_recording_class(self) -> None:
        # studio IS a recording class, so it is forwarded (harmless: it only
        # reinforces the implicit baseline). The avoid class comes through too.
        prefer, avoid = version_intent(Preferences(prefer=["studio"], avoid=["live"]))
        assert prefer == frozenset({"studio"})
        assert avoid == frozenset({"live"})

    def test_original_keyword_dropped(self) -> None:
        # "original" is not a RecordingClass value; it is dropped.
        prefer, avoid = version_intent(Preferences(prefer=["original"], avoid=["live"]))
        assert prefer == frozenset()
        assert avoid == frozenset({"live"})
