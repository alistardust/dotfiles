"""Preference resolution: stored typed prefs -> ActivePreference (AC-C1/S5).

These exercise the registry seam that turns a user's ``prefer spatial=atmos``
into a criterion the two-phase engine actually fires on, using REAL candidate
metadata (Tidal ``audio_modes``) rather than an ad-hoc test criterion.
"""
from __future__ import annotations

from types import SimpleNamespace

from tuneshift.matching.criteria import Strength
from tuneshift.matching.registry import (
    KNOWN_AXES,
    PreferenceSpec,
    criterion_for,
    resolve_active_preferences,
    resolve_scoped_specs,
)
from tuneshift.matching.selection import select_version


def _rel(pid, *, audio_modes, available=True):
    # Same identity (title/artist/album), differing only by audio_modes — the
    # "Beg For You" atmos-vs-stereo case (separate Tidal IDs, same recording).
    return SimpleNamespace(
        platform_id=pid,
        title="Beg For You",
        artist="Charli XCX",
        album="Crash",
        isrc="GB1234500001",
        duration_seconds=173,
        available=available,
        audio_modes=audio_modes,
    )


SOURCE = _rel("src", audio_modes=[])
STEREO = _rel("stereo_id", audio_modes=["STEREO"])
ATMOS = _rel("atmos_id", audio_modes=["DOLBY_ATMOS"])


def test_spatial_alias_target_canonicalized_to_whitelist_token():
    # "atmos" is an alias surface form; the built criterion must match the
    # candidate's canonical DOLBY_ATMOS token.
    crit = criterion_for("spatial", "atmos")
    val = crit.extract(ATMOS)
    assert val is not None
    assert crit.compare(crit.extract(SOURCE) or val, val, Strength.PREFER).name == "SOFT_BONUS"


def test_prefer_atmos_selects_atmos_id_over_stereo_end_to_end():
    specs = [PreferenceSpec(axis="spatial", target="atmos",
                            strength=Strength.PREFER, scope="playlist")]
    active = resolve_active_preferences(specs)
    result = select_version(SOURCE, [STEREO, ATMOS], active=active)

    assert result.winner is ATMOS
    assert result.decided_by == "spatial"


def test_require_atmos_hard_filters_stereo():
    specs = [PreferenceSpec(axis="spatial", target="atmos",
                            strength=Strength.REQUIRE, scope="playlist")]
    active = resolve_active_preferences(specs)
    result = select_version(SOURCE, [STEREO, ATMOS], active=active)

    assert result.winner is ATMOS
    # the stereo release was eliminated in phase 1, not merely out-scored
    assert any(fc.candidate is STEREO for fc in result.filtered)


def test_prefer_atmos_when_only_stereo_available_still_picks_stereo():
    # No atmos ID exists: the soft preference cannot invent one; the available
    # stereo release still wins (a soft pref never eliminates the only option).
    specs = [PreferenceSpec(axis="spatial", target="atmos",
                            strength=Strength.PREFER, scope="playlist")]
    active = resolve_active_preferences(specs)
    result = select_version(SOURCE, [STEREO], active=active)

    assert result.winner is STEREO


class TestResolveScopedSpecs:
    """Three-scope cascade + most-specific-wins collapse (AC-CLI1 precedence)."""

    def test_empty_scopes_yield_no_specs(self):
        assert resolve_scoped_specs(None, None, None) == []
        assert resolve_scoped_specs([], [], []) == []

    def test_single_global_spec_maps_to_global_scope(self):
        specs = resolve_scoped_specs(
            [{"criterion": "spatial", "strength": "prefer", "target": "atmos"}],
            None,
            None,
        )
        assert len(specs) == 1
        assert specs[0].axis == "spatial"
        assert specs[0].strength is Strength.PREFER
        assert specs[0].scope == "global"

    def test_playlist_track_maps_to_track_scope_for_precedence(self):
        specs = resolve_scoped_specs(
            None,
            None,
            [{"criterion": "spatial", "strength": "require", "target": "atmos"}],
        )
        assert specs[0].scope == "track"

    def test_most_specific_scope_wins_on_same_axis_target(self):
        # global avoids atmos, playlist-track requires it -> the specific one wins,
        # and there is exactly ONE surviving spec (no contradictory hard filters).
        specs = resolve_scoped_specs(
            [{"criterion": "spatial", "strength": "avoid", "target": "atmos"}],
            None,
            [{"criterion": "spatial", "strength": "require", "target": "atmos"}],
        )
        assert len(specs) == 1
        assert specs[0].strength is Strength.REQUIRE
        assert specs[0].scope == "track"

    def test_playlist_overrides_global_but_track_absent(self):
        specs = resolve_scoped_specs(
            [{"criterion": "spatial", "strength": "avoid", "target": "atmos"}],
            [{"criterion": "spatial", "strength": "prefer", "target": "atmos"}],
            None,
        )
        assert len(specs) == 1
        assert specs[0].strength is Strength.PREFER
        assert specs[0].scope == "playlist"

    def test_alias_target_collapses_against_canonical(self):
        # "atmos" (alias) and "dolby_atmos" (canonical) are the SAME axis+target;
        # the more specific scope must override rather than duplicate.
        specs = resolve_scoped_specs(
            [{"criterion": "spatial", "strength": "avoid", "target": "dolby_atmos"}],
            [{"criterion": "spatial", "strength": "prefer", "target": "atmos"}],
            None,
        )
        assert len(specs) == 1
        assert specs[0].strength is Strength.PREFER

    def test_distinct_targets_on_same_axis_coexist(self):
        specs = resolve_scoped_specs(
            [
                {"criterion": "content", "strength": "avoid", "target": "karaoke"},
                {"criterion": "content", "strength": "avoid", "target": "instrumental"},
            ],
            None,
            None,
        )
        assert len(specs) == 2
        assert {s.target for s in specs} == {"karaoke", "instrumental"}

    def test_unknown_axis_and_strength_are_skipped(self):
        specs = resolve_scoped_specs(
            [
                {"criterion": "bogus_axis", "strength": "prefer", "target": "x"},
                {"criterion": "spatial", "strength": "nonsense", "target": "atmos"},
                {"criterion": "spatial", "strength": "prefer", "target": ""},
            ],
            None,
            None,
        )
        assert specs == []

    def test_known_axes_covers_structured_and_title(self):
        assert {"spatial", "mix", "fidelity"} <= KNOWN_AXES
        assert {"performance", "content", "edit", "production"} <= KNOWN_AXES

    def test_cascade_feeds_end_to_end_selection(self):
        # playlist-track require atmos, resolved through the cascade, hard-filters
        # the stereo release exactly as a direct PreferenceSpec would.
        specs = resolve_scoped_specs(
            [{"criterion": "spatial", "strength": "avoid", "target": "atmos"}],
            None,
            [{"criterion": "spatial", "strength": "require", "target": "atmos"}],
        )
        active = resolve_active_preferences(specs)
        result = select_version(SOURCE, [STEREO, ATMOS], active=active)
        assert result.winner is ATMOS
        assert any(fc.candidate is STEREO for fc in result.filtered)
