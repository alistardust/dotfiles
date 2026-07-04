"""Compat tests for the deprecated tuneshift.reconcile_prefs shim.

The canonical home is tuneshift.matching.preferences (see
tests/matching/test_preferences.py). These tests only assert the shim keeps
re-exporting the public names. The old score_version scorer was dead code and
was removed during the matching overhaul.
"""
from tuneshift.reconcile_prefs import (
    Preferences,
    VersionPreferences,
    resolve_preferences,
)


def test_shim_reexports_are_the_canonical_types() -> None:
    from tuneshift.matching.preferences import Preferences as CanonicalPreferences

    assert Preferences is CanonicalPreferences
    assert VersionPreferences is CanonicalPreferences


def test_default_preferences() -> None:
    prefs = VersionPreferences()
    assert "studio" in prefs.prefer
    assert "live" in prefs.avoid


def test_playlist_overrides_global() -> None:
    global_prefs = {"prefer": ["studio"], "avoid": ["live"]}
    playlist_prefs = {"prefer": ["live"], "avoid": []}
    resolved = resolve_preferences(global_prefs, playlist_prefs, None)
    assert "live" in resolved.prefer
    assert "live" not in resolved.avoid
