"""Chunk 2 Task 2.3: confidence-gated hard filters + committed whitelist (AC-C3).

A require/forbid may only ELIMINATE a candidate when the driving value is
confident: either it came from a structured field, or it is an unambiguous token
drawn from the committed whitelist. Any other token is treated as ambiguous and
its hard verdict is DEMOTED to soft (it can nudge the score but never eliminate).

Gold cases (real-world ambiguity):
- "Pet Sounds (Original Mono & Stereo Mix)": a title-parsed require-mono must NOT
  hard-reject this release — the title carries BOTH mono and stereo (conflicting
  same-axis tokens => ambiguous). It demotes to a soft signal instead.
- "Deluxe" is off-whitelist => a require/forbid deluxe parsed from a title never
  drives a hard filter; it demotes to soft.
- A structured audio_modes=[DOLBY_ATMOS] value IS confident => require-atmos may
  hard-reject a stereo-only candidate.
"""

from __future__ import annotations

from tuneshift.matching.criteria import (
    CriterionValue,
    Strength,
    TitleTokenCriterion,
    TokenCriterion,
    Verdict,
    apply_confidence_gate,
    load_token_whitelist,
)


def _title_value(title: str, whitelist) -> CriterionValue:
    return TitleTokenCriterion(
        name="mix", target="mono", whitelist=whitelist
    ).extract_from_title(title)


def test_whitelist_loads_committed_tokens_with_axes():
    wl = load_token_whitelist()
    # Core mix/spatial/content tokens are committed and unambiguous.
    assert "mono" in wl
    assert "stereo" in wl
    assert wl.axis("mono") == wl.axis("stereo") == "mix"
    assert wl.axis("dolby_atmos") == "spatial"
    # "deluxe" is deliberately NOT on the whitelist (ambiguous edition marker).
    assert "deluxe" not in wl


def test_structured_value_allows_hard_elimination():
    wl = load_token_whitelist()
    structured = CriterionValue(raw=["STEREO"], tokens=frozenset({"stereo"}), structured=True)
    # require-atmos, candidate is stereo-only structured => HARD_REJECT stands.
    gated = apply_confidence_gate(
        Verdict.HARD_REJECT, value=structured, target="dolby_atmos", whitelist=wl
    )
    assert gated is Verdict.HARD_REJECT


def test_offwhitelist_token_demotes_hard_to_soft():
    wl = load_token_whitelist()
    val = CriterionValue(raw="deluxe", tokens=frozenset({"deluxe"}), structured=False)
    # A title-parsed forbid-deluxe would HARD_REJECT, but "deluxe" is off-list.
    gated = apply_confidence_gate(
        Verdict.HARD_REJECT, value=val, target="deluxe", whitelist=wl
    )
    assert gated is Verdict.SOFT_PENALTY
    # A HARD_PASS (met require) on an ambiguous token becomes a soft bonus.
    gated_pass = apply_confidence_gate(
        Verdict.HARD_PASS, value=val, target="deluxe", whitelist=wl
    )
    assert gated_pass is Verdict.SOFT_BONUS


def test_conflicting_same_axis_tokens_are_ambiguous():
    wl = load_token_whitelist()
    both = _title_value("Pet Sounds (Original Mono & Stereo Mix)", wl)
    # Title carries both mono AND stereo (same axis) => ambiguous.
    assert both.tokens >= {"mono", "stereo"}
    gated = apply_confidence_gate(
        Verdict.HARD_PASS, value=both, target="mono", whitelist=wl
    )
    # require-mono must NOT hard-eliminate the stereo-bearing release; demote.
    assert not gated.is_hard


def test_title_criterion_never_hard_rejects_ambiguous_pet_sounds():
    wl = load_token_whitelist()
    crit = TitleTokenCriterion(name="mix", target="mono", whitelist=wl)
    both = crit.extract_from_title("Pet Sounds (Original Mono & Stereo Mix)")
    source = crit.extract_from_title("Pet Sounds (Mono)")
    verdict = crit.compare(source, both, Strength.REQUIRE)
    assert not verdict.is_hard


def test_structured_token_criterion_still_hard_filters():
    wl = load_token_whitelist()
    # A structured TokenCriterion (audio_modes) is confident => hard filter fires.
    crit = TokenCriterion(name="spatial", field_name="audio_modes", target="dolby_atmos")

    class _Meta:
        audio_modes = ["STEREO"]

    val = crit.extract(_Meta())
    verdict = crit.compare(val, val, Strength.REQUIRE)
    gated = apply_confidence_gate(
        verdict, value=val, target="dolby_atmos", whitelist=wl
    )
    assert gated is Verdict.HARD_REJECT
