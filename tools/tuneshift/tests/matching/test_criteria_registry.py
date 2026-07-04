"""Chunk 2 Task 2.1: the typed Criterion protocol + registry (AC-C1).

Every matchable/preferable field becomes a registered typed unit — extractor,
comparator, score-projection, hard-cap policy. Adding a criterion is
registration + config, NO bespoke scoring code. The parity-critical contract is
"no verdict => no signal": a criterion with no active preference referencing it
returns None from to_signal and contributes NOTHING to the Distance.
"""

from __future__ import annotations

import pytest

from tuneshift.matching.criteria import (
    Criterion,
    CriterionRegistry,
    CriterionValue,
    HardCapPolicy,
    Strength,
    Verdict,
)
from tuneshift.matching.engine import Distance
from tuneshift.matching.penalties import SignalPenalty


class _DummyGenreCriterion:
    """A minimal criterion over a track's `genre` attribute for the test."""

    name = "genre"
    hard_cap = HardCapPolicy.NONE

    def extract(self, meta: object) -> CriterionValue | None:
        genre = getattr(meta, "genre", None)
        if not genre:
            return None
        return CriterionValue(raw=genre, tokens=frozenset({str(genre).lower()}),
                              structured=True)

    def compare(
        self,
        source: CriterionValue,
        candidate: CriterionValue,
        strength: Strength | None,
    ) -> Verdict:
        if strength is None:
            return Verdict.NO_VERDICT
        if strength is Strength.PREFER:
            return (
                Verdict.SOFT_BONUS
                if source.tokens & candidate.tokens
                else Verdict.SOFT_PENALTY
            )
        return Verdict.NEUTRAL

    def to_signal(self, verdict: Verdict) -> SignalPenalty | None:
        if verdict is Verdict.SOFT_PENALTY:
            return SignalPenalty("genre", -5, 1.0, 5)
        if verdict is Verdict.SOFT_BONUS:
            return SignalPenalty("genre", 5, 0.0, 5)
        return None


class _Meta:
    def __init__(self, genre=None):
        self.genre = genre


def test_registry_registers_and_retrieves() -> None:
    reg = CriterionRegistry()
    crit = _DummyGenreCriterion()
    reg.register(crit)
    assert reg.get("genre") is crit
    assert "genre" in reg
    assert [c.name for c in reg] == ["genre"]


def test_registry_rejects_duplicate_names() -> None:
    reg = CriterionRegistry()
    reg.register(_DummyGenreCriterion())
    with pytest.raises(ValueError, match="genre"):
        reg.register(_DummyGenreCriterion())


def test_dummy_criterion_flows_end_to_end_through_distance() -> None:
    """A registered criterion projects into a real Distance untouched — proving
    the registry EXTENDS the weighted engine rather than rewriting it (AC-C1)."""
    crit: Criterion = _DummyGenreCriterion()
    src = crit.extract(_Meta(genre="rock"))
    cand = crit.extract(_Meta(genre="pop"))
    verdict = crit.compare(src, cand, Strength.PREFER)
    assert verdict is Verdict.SOFT_PENALTY

    distance = Distance()
    signal = crit.to_signal(verdict)
    assert signal is not None
    distance.add(signal)
    assert distance.has_signal("genre")
    assert distance.total > 0.0


def test_no_active_preference_emits_no_signal() -> None:
    """The parity contract: a criterion with no active preference (strength=None)
    yields NO_VERDICT and to_signal None, leaving Distance.signals byte-identical
    to the no-criterion case (AC-C1 / AC-C5 winner-parity)."""
    crit = _DummyGenreCriterion()
    src = crit.extract(_Meta(genre="rock"))
    cand = crit.extract(_Meta(genre="pop"))

    verdict = crit.compare(src, cand, None)
    assert verdict is Verdict.NO_VERDICT
    assert crit.to_signal(verdict) is None

    baseline = Distance()
    with_unreferenced = Distance()
    signal = crit.to_signal(verdict)
    if signal is not None:  # must not happen
        with_unreferenced.add(signal)
    assert with_unreferenced.signals == baseline.signals
    assert with_unreferenced.total == baseline.total


def test_unextractable_value_is_none() -> None:
    """A field absent on the metadata extracts to None (=> engine skips it)."""
    crit = _DummyGenreCriterion()
    assert crit.extract(_Meta(genre=None)) is None


def test_hard_verdict_emits_no_soft_signal() -> None:
    """Hard verdicts cap the recommendation (via hard_cap); they never score as
    a soft SignalPenalty (AC-C2 preview)."""
    class _RequireCrit(_DummyGenreCriterion):
        hard_cap = HardCapPolicy.REJECT

        def compare(self, source, candidate, strength):
            if strength is Strength.REQUIRE:
                return (
                    Verdict.HARD_PASS
                    if source.tokens & candidate.tokens
                    else Verdict.HARD_REJECT
                )
            return Verdict.NO_VERDICT

    crit = _RequireCrit()
    src = crit.extract(_Meta(genre="rock"))
    cand = crit.extract(_Meta(genre="pop"))
    verdict = crit.compare(src, cand, Strength.REQUIRE)
    assert verdict is Verdict.HARD_REJECT
    assert crit.to_signal(verdict) is None


# --- M7: EditAxisCriterion (album_version as the unmarked default) -----------


def _edit_meta(*, title="Song", version=None):
    from types import SimpleNamespace

    return SimpleNamespace(title=title, tidal_version=version)


def test_edit_axis_album_version_satisfied_by_unmarked_release():
    from tuneshift.matching.criteria import EditAxisCriterion, load_token_whitelist

    crit = EditAxisCriterion(whitelist=load_token_whitelist(), target="album_version")
    # An unmarked album track carries no edit token at all.
    val = crit.extract(_edit_meta())
    assert val is not None and val.tokens == frozenset()
    # Unmarked => it IS the album version => a prefer is satisfied (bonus).
    assert crit.compare(val, val, Strength.PREFER) is Verdict.SOFT_BONUS


def test_edit_axis_album_version_not_satisfied_by_radio_edit():
    from tuneshift.matching.criteria import EditAxisCriterion, load_token_whitelist

    crit = EditAxisCriterion(whitelist=load_token_whitelist(), target="album_version")
    radio = crit.extract(_edit_meta(version="Radio Edit"))
    assert "radioedit" in radio.tokens
    # A competing edit marker present => NOT the album version => prefer miss.
    assert crit.compare(radio, radio, Strength.PREFER) is Verdict.SOFT_PENALTY


def test_edit_axis_reads_marker_from_structured_version_field():
    from tuneshift.matching.criteria import EditAxisCriterion, load_token_whitelist

    crit = EditAxisCriterion(whitelist=load_token_whitelist(), target="radio_edit")
    val = crit.extract(_edit_meta(version="Radio Edit"))
    assert val.structured is True
    assert crit.compare(val, val, Strength.PREFER) is Verdict.SOFT_BONUS


def test_edit_axis_require_album_version_hard_rejects_radio_edit():
    from tuneshift.matching.criteria import EditAxisCriterion, load_token_whitelist

    crit = EditAxisCriterion(whitelist=load_token_whitelist(), target="album_version")
    radio = crit.extract(_edit_meta(version="Radio Edit"))
    # A structured marker is confident, so REQUIRE stays hard (not demoted).
    assert crit.compare(radio, radio, Strength.REQUIRE) is Verdict.HARD_REJECT


# --- M3: DateCriterion (recording/release/remaster-year prefer/require) -------


def _date_meta(*, remaster_year=None, release_date=None, recording_date=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        remaster_year=remaster_year,
        release_date=release_date,
        recording_date=recording_date,
    )


def test_date_criterion_prefers_exact_remaster_year():
    from tuneshift.matching.criteria import DateCriterion

    crit = DateCriterion(name="remaster_year", date_field="remaster_year", target="2015")
    hit = crit.extract(_date_meta(remaster_year=2015))
    miss = crit.extract(_date_meta(remaster_year=1999))
    assert crit.compare(hit, hit, Strength.PREFER) is Verdict.SOFT_BONUS
    assert crit.compare(miss, miss, Strength.PREFER) is Verdict.SOFT_PENALTY


def test_date_criterion_original_means_no_remaster():
    from tuneshift.matching.criteria import DateCriterion

    crit = DateCriterion(name="remaster_year", date_field="remaster_year", target="original")
    original = crit.extract(_date_meta(remaster_year=None))
    remastered = crit.extract(_date_meta(remaster_year=2015))
    assert crit.compare(original, original, Strength.PREFER) is Verdict.SOFT_BONUS
    assert crit.compare(remastered, remastered, Strength.PREFER) is Verdict.SOFT_PENALTY


def test_date_criterion_parses_year_from_iso_release_date():
    from tuneshift.matching.criteria import DateCriterion

    crit = DateCriterion(name="release_year", date_field="release_date", target="1999")
    val = crit.extract(_date_meta(release_date="1999-05-18"))
    assert val is not None and "1999" in val.tokens
    assert crit.compare(val, val, Strength.REQUIRE) is Verdict.HARD_PASS


def test_date_criterion_unextractable_yields_no_verdict():
    from tuneshift.matching.criteria import DateCriterion

    crit = DateCriterion(name="remaster_year", date_field="remaster_year", target="2015")
    assert crit.extract(_date_meta()) is None


# --- M4: DurationCriterion (per-criterion / per-playlist duration tolerance) --


def _dur_meta(seconds):
    from types import SimpleNamespace

    return SimpleNamespace(duration_seconds=seconds)


def test_duration_criterion_within_absolute_tolerance_satisfies():
    from tuneshift.matching.criteria import DurationCriterion

    crit = DurationCriterion(name="duration", target="2s")
    src = crit.extract(_dur_meta(200))
    close = crit.extract(_dur_meta(201))
    assert crit.compare(src, close, Strength.REQUIRE) is Verdict.HARD_PASS


def test_duration_criterion_beyond_absolute_tolerance_hard_rejects():
    from tuneshift.matching.criteria import DurationCriterion

    crit = DurationCriterion(name="duration", target="2s")
    src = crit.extract(_dur_meta(200))
    extended = crit.extract(_dur_meta(300))
    # A require tolerance is confident (numeric/structured) -> stays a hard reject.
    assert crit.compare(src, extended, Strength.REQUIRE) is Verdict.HARD_REJECT


def test_duration_criterion_percent_tolerance_relative_to_source():
    from tuneshift.matching.criteria import DurationCriterion

    crit = DurationCriterion(name="duration", target="5%")
    src = crit.extract(_dur_meta(200))  # 5% of 200 = 10s tolerance
    within = crit.extract(_dur_meta(209))
    beyond = crit.extract(_dur_meta(212))
    assert crit.compare(src, within, Strength.PREFER) is Verdict.SOFT_BONUS
    assert crit.compare(src, beyond, Strength.PREFER) is Verdict.SOFT_PENALTY


def test_duration_criterion_missing_duration_yields_no_verdict():
    from tuneshift.matching.criteria import DurationCriterion

    crit = DurationCriterion(name="duration", target="2s")
    assert crit.extract(_dur_meta(None)) is None
    src = crit.extract(_dur_meta(200))
    # Candidate has a duration but the source does not: nothing to measure against.
    empty = crit.extract(_dur_meta(None)) or CriterionValue(raw=None)
    assert crit.compare(empty, src, Strength.REQUIRE) is Verdict.NO_VERDICT


# --- M5: ArtistRoleCriterion (main vs featured artist sets) -------------------


def _artist_meta(artist):
    from types import SimpleNamespace

    return SimpleNamespace(artist=artist)


def test_artist_role_criterion_feat_variant_matches_main_no_penalty():
    from tuneshift.matching.criteria import ArtistRoleCriterion

    crit = ArtistRoleCriterion(name="artist_role", target="main")
    src = crit.extract(_artist_meta("Eminem"))
    feat = crit.extract(_artist_meta("Eminem feat. Rihanna"))
    # Same main artist; the added feature must not trigger a spurious reject.
    assert crit.compare(src, feat, Strength.REQUIRE) is Verdict.HARD_PASS


def test_artist_role_criterion_wrong_main_rejected():
    from tuneshift.matching.criteria import ArtistRoleCriterion

    crit = ArtistRoleCriterion(name="artist_role", target="main")
    src = crit.extract(_artist_meta("Eminem"))
    wrong = crit.extract(_artist_meta("50 Cent feat. Eminem"))
    # Eminem is only FEATURED on the candidate -> the main artist differs -> reject.
    assert crit.compare(src, wrong, Strength.REQUIRE) is Verdict.HARD_REJECT


def test_artist_role_criterion_missing_artist_no_verdict():
    from tuneshift.matching.criteria import ArtistRoleCriterion

    crit = ArtistRoleCriterion(name="artist_role", target="main")
    assert crit.extract(_artist_meta("")) is None
    assert crit.extract(_artist_meta(None)) is None


