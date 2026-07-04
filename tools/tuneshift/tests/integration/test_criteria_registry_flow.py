"""Chunk 2 integration gate: the criterion pieces compose into per-playlist
version selection (AC-C1..C7).

This exercises the whole Chunk 2 slice wired the way the selection engine will
drive it in Chunk 3, on a real per-playlist scenario:

* the SAME track has two candidate releases — a 2024 Dolby Atmos remaster and
  the 1999 stereo original;
* an "Atmos" playlist prefers ``spatial=atmos`` (a STRUCTURED audio_modes
  criterion) and must select the Atmos release;
* an "Originals" playlist prefers ``release-context=original`` and must select
  the stereo original;
* when both preferences are active with conflicting pulls, the per-playlist
  PRECEDENCE order decides — and flipping it flips the winner (AC-C7);
* a require driven by an OFF-whitelist title token never eliminates a
  candidate (AC-C3); and
* a genuine tie falls through to the deterministic tie-break (AC-C6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tuneshift.matching.criteria import (
    Strength,
    TitleTokenCriterion,
    TokenCriterion,
    Verdict,
    load_token_whitelist,
)
from tuneshift.matching.precedence import (
    PreferenceRef,
    derive_precedence,
    resolve_conflict,
)
from tuneshift.matching.tiebreak import TieCandidate, tie_break


@dataclass
class _Release:
    id: str
    title: str
    audio_modes: list[str] = field(default_factory=list)
    release_context: list[str] = field(default_factory=list)
    release_year: int | None = None
    availability_rank: int = 0


ATMOS_REMASTER = _Release(
    id="atmos_remaster",
    title="Wouldn't It Be Nice",
    audio_modes=["DOLBY_ATMOS"],
    release_context=["remaster"],
    release_year=2024,
    availability_rank=9,
)
STEREO_ORIGINAL = _Release(
    id="stereo_original",
    title="Wouldn't It Be Nice",
    audio_modes=["STEREO"],
    release_context=["original"],
    release_year=1966,
    availability_rank=9,
)
CANDIDATES = [ATMOS_REMASTER, STEREO_ORIGINAL]

# The two competing soft criteria (both structured), plus the whitelist gate.
SPATIAL = TokenCriterion(name="spatial", field_name="audio_modes", target="dolby_atmos")
CONTEXT = TokenCriterion(name="release_context", field_name="release_context", target="original")


def _verdicts_for(criterion, target_strength) -> dict[str, dict[str, Verdict]]:
    """Run one criterion at a given strength across both candidates."""
    out: dict[str, dict[str, Verdict]] = {}
    src = criterion.extract(ATMOS_REMASTER)  # source value is irrelevant for token membership
    for release in CANDIDATES:
        value = criterion.extract(release)
        verdict = criterion.compare(src, value, target_strength) if value else Verdict.NO_VERDICT
        out[release.id] = {criterion.name: verdict}
    return out


def _merge(*verdict_maps: dict[str, dict[str, Verdict]]) -> dict[str, dict[str, Verdict]]:
    merged: dict[str, dict[str, Verdict]] = {}
    for vm in verdict_maps:
        for cid, crit_verdicts in vm.items():
            merged.setdefault(cid, {}).update(crit_verdicts)
    return merged


def test_atmos_playlist_selects_atmos_release():
    verdicts = _verdicts_for(SPATIAL, Strength.PREFER)
    precedence = derive_precedence(
        global_refs=[],
        playlist_refs=[PreferenceRef("spatial", Strength.PREFER, "dolby_atmos", "playlist")],
        track_refs=[],
    )
    decision = resolve_conflict(verdicts, precedence)
    assert decision.winner == "atmos_remaster"
    assert decision.decided_by == "spatial"


def test_originals_playlist_selects_stereo_original():
    verdicts = _verdicts_for(CONTEXT, Strength.PREFER)
    precedence = derive_precedence(
        global_refs=[],
        playlist_refs=[PreferenceRef("release_context", Strength.PREFER, "original", "playlist")],
        track_refs=[],
    )
    decision = resolve_conflict(verdicts, precedence)
    assert decision.winner == "stereo_original"
    assert decision.decided_by == "release_context"


def test_conflicting_prefs_resolved_by_precedence_both_ways():
    verdicts = _merge(
        _verdicts_for(SPATIAL, Strength.PREFER),
        _verdicts_for(CONTEXT, Strength.PREFER),
    )
    atmos_first = derive_precedence(
        global_refs=[],
        playlist_refs=[
            PreferenceRef("spatial", Strength.PREFER, "dolby_atmos", "playlist"),
            PreferenceRef("release_context", Strength.PREFER, "original", "playlist"),
        ],
        track_refs=[],
    )
    assert resolve_conflict(verdicts, atmos_first).winner == "atmos_remaster"

    context_first = derive_precedence(
        global_refs=[],
        playlist_refs=[
            PreferenceRef("release_context", Strength.PREFER, "original", "playlist"),
            PreferenceRef("spatial", Strength.PREFER, "dolby_atmos", "playlist"),
        ],
        track_refs=[],
    )
    assert resolve_conflict(verdicts, context_first).winner == "stereo_original"


def test_track_scope_pref_overrides_playlist_scope():
    # An Atmos playlist, but this ONE track is pinned to the original at track scope.
    verdicts = _merge(
        _verdicts_for(SPATIAL, Strength.PREFER),
        _verdicts_for(CONTEXT, Strength.PREFER),
    )
    precedence = derive_precedence(
        global_refs=[],
        playlist_refs=[PreferenceRef("spatial", Strength.PREFER, "dolby_atmos", "playlist")],
        track_refs=[PreferenceRef("release_context", Strength.PREFER, "original", "track")],
    )
    # Track scope outranks playlist scope, so the original wins despite the Atmos playlist.
    assert resolve_conflict(verdicts, precedence).winner == "stereo_original"


def test_offwhitelist_require_does_not_eliminate_candidate():
    wl = load_token_whitelist()
    crit = TitleTokenCriterion(name="edition", target="deluxe", whitelist=wl)
    # A "require deluxe" parsed from titles: neither release carries it, and
    # "deluxe" is off-whitelist, so the hard verdict must demote to soft (no
    # candidate is eliminated).
    src = crit.extract_from_title("Wouldn't It Be Nice (Deluxe)")
    for release in CANDIDATES:
        cand = crit.extract_from_title(release.title)
        verdict = crit.compare(src, cand, Strength.REQUIRE)
        assert not verdict.is_hard


def test_tie_falls_through_to_deterministic_tiebreak():
    # No active preference distinguishes the two releases -> unresolved conflict.
    verdicts = {r.id: {} for r in CANDIDATES}
    decision = resolve_conflict(verdicts, [])
    assert decision.unresolved
    # Selection then applies the tie-break: earliest original release-year wins.
    winner = tie_break([
        TieCandidate(id=r.id, release_year=r.release_year, availability_rank=r.availability_rank)
        for r in CANDIDATES
    ])
    assert winner.winner == "stereo_original"
    assert winner.decided_by == "release-year"
