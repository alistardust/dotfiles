"""Artist-alias equivalence resolver.

Locks the two-representation model: normalized keys decide "same act?" for
scoring, raw surface forms drive retrieval query expansion. Non-members must
pass through ``canonical`` unchanged so the default scoring path is untouched.
"""
from __future__ import annotations

import pytest

from tuneshift.matching.aliases import (
    AliasResolver,
    canonicalize_raw,
    default_resolver,
)
from tuneshift.matching.normalize import normalize_artist as na

# U+00B0 degree sign; U+00BA masculine ordinal indicator.
DEG = "\u00b0"
ORD = "\u00ba"


class TestSeedResolver:
    def test_degree_sign_and_word_unify(self):
        r = default_resolver()
        assert r.same_class(na("98 Degrees"), na(f"98{DEG}"))

    def test_ordinal_glyph_bridged_by_class_not_normalization(self):
        # normalize_artist alone cannot bridge U+00BA; the class must.
        assert na(f"98{ORD}") != na("98 Degrees")
        r = default_resolver()
        assert r.same_class(na(f"98{ORD}"), na("98 Degrees"))

    def test_kesha_rebrand(self):
        r = default_resolver()
        assert r.same_class(na("Ke$ha"), na("Kesha"))

    def test_pink_deliberately_excluded_from_seed(self):
        r = default_resolver()
        assert not r.same_class(na("P!nk"), na("Pink"))


class TestCanonicalIdentity:
    def test_non_member_returns_input_unchanged(self):
        r = default_resolver()
        assert r.canonical(na("Gorillaz")) == na("Gorillaz")

    def test_non_members_do_not_share_a_class(self):
        r = default_resolver()
        assert not r.same_class(na("Gorillaz"), na("Blur"))

    def test_canonical_is_stable_lex_smallest_key(self):
        r = AliasResolver(seed=[{"Zebra", "Aardvark", "Mango"}])
        # All three map to the same canonical: the lex-smallest normalized key.
        canon = {r.canonical(na(x)) for x in ("Zebra", "Aardvark", "Mango")}
        assert canon == {na("Aardvark")}


class TestVariantsForQuery:
    def test_returns_other_raw_surface_forms(self):
        r = default_resolver()
        assert r.variants_for_query("98 Degrees") == sorted([f"98{DEG}", f"98{ORD}"])

    def test_excludes_the_queried_surface_form(self):
        r = default_resolver()
        assert "98 Degrees" not in r.variants_for_query("98 Degrees")

    def test_empty_for_non_member(self):
        r = default_resolver()
        assert r.variants_for_query("Gorillaz") == []

    def test_query_by_any_member_returns_the_rest(self):
        r = default_resolver()
        assert r.variants_for_query(f"98{ORD}") == sorted(["98 Degrees", f"98{DEG}"])

    def test_surrounding_whitespace_ignored(self):
        r = default_resolver()
        assert r.variants_for_query(f"  98{ORD}  ") == sorted(["98 Degrees", f"98{DEG}"])


class TestMergeAndBridging:
    def test_overlapping_classes_union(self):
        r = AliasResolver(seed=[{"A", "B"}], db_classes=[{"B", "C"}])
        assert r.same_class(na("A"), na("C"))

    def test_bridging_three_classes(self):
        r = AliasResolver(seed=[{"A", "B"}, {"C", "D"}], db_classes=[{"B", "C"}])
        assert r.same_class(na("A"), na("D"))

    def test_order_independent(self):
        r1 = AliasResolver(seed=[{"B", "C"}, {"A", "B"}])
        r2 = AliasResolver(seed=[{"A", "B"}, {"B", "C"}])
        assert r1.canonical(na("A")) == r2.canonical(na("A")) == r2.canonical(na("C"))

    def test_singleton_class_dropped(self):
        r = AliasResolver(seed=[{"Solo"}])
        assert r.variants_for_query("Solo") == []
        assert r.canonical(na("Solo")) == na("Solo")

    def test_two_raw_one_norm_key_class_retained_for_retrieval(self):
        # Same normalized key, two distinct surface forms: useless for scoring
        # equivalence (already equal) but valid for retrieval expansion.
        r = AliasResolver(seed=[{"98 Degrees", f"98{DEG}"}])
        assert r.variants_for_query("98 Degrees") == [f"98{DEG}"]

    def test_db_classes_merge_with_seed(self):
        r = AliasResolver(db_classes=[{"98 Degrees", "Ninety-Eight Degrees"}])
        assert r.same_class(na(f"98{ORD}"), na("Ninety-Eight Degrees"))


class TestCanonicalizeRaw:
    def test_trims_surrounding_whitespace_only(self):
        assert canonicalize_raw(f"  98{DEG} ") == f"98{DEG}"

    def test_preserves_case_and_glyphs(self):
        assert canonicalize_raw("Ke$ha") == "Ke$ha"


@pytest.mark.parametrize("member", ["98 Degrees", f"98{DEG}", f"98{ORD}"])
def test_every_seed_member_resolves_to_same_canonical(member):
    r = default_resolver()
    assert r.canonical(na(member)) == r.canonical(na("98 Degrees"))
