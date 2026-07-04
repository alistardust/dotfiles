"""Alias equivalence at the scoring layer.

Locks that ``score_match`` / ``score_match_with_version`` treat aliased artist
surface forms as the same act (the 98\u00ba / Kesha bugs), while leaving every
un-aliased artist byte-identical to the historical scorer and keeping genuinely
different artists penalized.
"""
from tuneshift.matching.aliases import AliasResolver
from tuneshift.matching.track import score_match, score_match_with_version

DEG = "\u00b0"  # U+00B0 degree sign
ORD = "\u00ba"  # U+00BA masculine ordinal indicator


class TestSeedAliasScoring:
    def test_ordinal_glyph_scores_as_exact_artist(self):
        # U+00BA is not bridged by normalization; the seed class must rescue it.
        score = score_match(
            "The Hardest Thing", f"98{ORD}", None,
            "The Hardest Thing", "98 Degrees", "The Collection",
        )
        assert score >= 80

    def test_degree_sign_scores_as_exact_artist(self):
        score = score_match(
            "The Hardest Thing", f"98{DEG}", None,
            "The Hardest Thing", "98 Degrees", "The Collection",
        )
        assert score >= 80

    def test_kesha_rebrand_scores_as_exact_artist(self):
        score = score_match(
            "Tik Tok", "Ke$ha", None, "Tik Tok", "Kesha", "Animal",
        )
        assert score >= 80

    def test_with_version_path_also_bridges_alias(self):
        # Isolate the alias effect from version/album penalties: scoring the
        # aliased surface form must equal scoring the canonical form itself.
        aliased = score_match_with_version(
            "The Hardest Thing", f"98{ORD}", None,
            "The Hardest Thing", "98 Degrees", "The Collection",
        )
        canonical = score_match_with_version(
            "The Hardest Thing", "98 Degrees", None,
            "The Hardest Thing", "98 Degrees", "The Collection",
        )
        assert aliased == canonical


class TestNonMemberByteParity:
    def test_different_artists_still_penalized(self):
        # A non-aliased mismatch must stay well below an exact-artist match.
        aliased = score_match(
            "The Hardest Thing", f"98{ORD}", None,
            "The Hardest Thing", "98 Degrees", "The Collection",
        )
        mismatch = score_match(
            "The Hardest Thing", "Gorillaz", None,
            "The Hardest Thing", "98 Degrees", "The Collection",
        )
        assert mismatch < aliased

    def test_resolver_param_default_matches_none(self):
        # Passing an empty resolver must be byte-identical to omitting it for a
        # non-member artist (the resolver only acts on class members).
        empty = AliasResolver(seed=[])
        args = ("Yellow", "Coldplay", None, "Yellow", "Coldplay", "Parachutes")
        assert score_match(*args) == score_match(*args, alias_resolver=empty)

    def test_seed_only_default_leaves_unrelated_artist_unchanged(self):
        base = score_match(
            "Clocks", "Coldplay", None, "Clocks", "Radiohead", "OK Computer",
        )
        empty = AliasResolver(seed=[])
        assert base == score_match(
            "Clocks", "Coldplay", None, "Clocks", "Radiohead", "OK Computer",
            alias_resolver=empty,
        )


class TestDbOverrideScoring:
    def test_user_added_class_bridges_at_scoring_layer(self):
        # A DB-supplied class the seed does not know must also clear the bar.
        resolver = AliasResolver(db_classes=[{"Prince", "The Artist"}])
        score = score_match(
            "Kiss", "The Artist", None, "Kiss", "Prince", "Parade",
            alias_resolver=resolver,
        )
        # Without the class this would be a hard artist mismatch.
        baseline = score_match("Kiss", "The Artist", None, "Kiss", "Prince", "Parade")
        assert score > baseline
        assert score >= 80
