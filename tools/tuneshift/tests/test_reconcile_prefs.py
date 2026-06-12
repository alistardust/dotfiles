import pytest
from tuneshift.reconcile_prefs import (
    VersionPreferences,
    resolve_preferences,
    score_version,
)


class TestVersionPreferences:
    def test_default_preferences(self) -> None:
        prefs = VersionPreferences()
        assert "studio" in prefs.prefer
        assert "live" in prefs.avoid

    def test_score_preferred_version(self) -> None:
        prefs = VersionPreferences(prefer=["studio", "explicit"], avoid=["live"])
        score = score_version("Studio Album", 210, prefs, expected_duration=200)
        assert score > 0

    def test_score_avoided_version(self) -> None:
        prefs = VersionPreferences(prefer=["studio"], avoid=["live", "remix"])
        score = score_version("Live at Wembley", 300, prefs, expected_duration=200)
        assert score < 0

    def test_duration_tolerance(self) -> None:
        prefs = VersionPreferences(duration_tolerance_percent=15)
        # 50% longer than expected -> rejected
        score = score_version("Remaster", 300, prefs, expected_duration=200)
        assert score < -100


class TestResolvePreferences:
    def test_playlist_overrides_global(self) -> None:
        global_prefs = {"prefer": ["studio"], "avoid": ["live"]}
        playlist_prefs = {"prefer": ["live"], "avoid": []}
        resolved = resolve_preferences(global_prefs, playlist_prefs, None)
        assert "live" in resolved.prefer
        assert "live" not in resolved.avoid
