"""Preference resolution: stored typed prefs -> ActivePreference (AC-C1/S5).

These exercise the registry seam that turns a user's ``prefer spatial=atmos``
into a criterion the two-phase engine actually fires on, using REAL candidate
metadata (Tidal ``audio_modes``) rather than an ad-hoc test criterion.
"""
from __future__ import annotations

from types import SimpleNamespace

from tuneshift.matching.criteria import Strength
from tuneshift.matching.registry import (
    PreferenceSpec,
    criterion_for,
    resolve_active_preferences,
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
