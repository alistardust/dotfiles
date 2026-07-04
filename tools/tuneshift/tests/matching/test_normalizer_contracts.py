"""Drift-guard contracts for the four normalizers (FL4).

TuneShift has four normalization functions that serve THREE distinct concerns.
They must NOT be collapsed into one, because their outputs mean different things
and some are persisted:

1. ``matching.normalize_*`` -- COMPARISON / equivalence keys used by the scoring
   engine. Aggressive: folds Latin accents, strips feat/explicit/all editions,
   casefolds. Output is transient (recomputed every match).

2. ``db.normalize_*`` -- STORED, INDEXED identity keys (``norm_title`` /
   ``norm_artist`` / ``norm_album`` columns; ``albums`` has
   ``UNIQUE(norm_title, artist_id, edition)``). Deliberately LIGHT and STABLE:
   lowercase, ``&``->``and``, strip only remaster/deluxe-edition parens, collapse
   whitespace, strip a leading "the " for artists. It intentionally does NOT fold
   accents or strip feat -- changing it would require a full reindex/backfill
   migration of every stored ``norm_*`` value and could collapse rows that the
   UNIQUE constraint currently keeps distinct (e.g. ``café``/``cafe``).

3. ``identity.normalize_*_for_search`` -- EXTERNAL API query strings. Strips a
   parenthetical version suffix and a leading "the ", but PRESERVES case and
   diacritics because external search engines rank on the surface form.

4. ``composer._normalize_text`` -- CONCEPT token extraction for the sequencer.
   Not a title/artist normalizer at all: it word-tokenizes and casefolds for
   theme/vibe overlap scoring.

These tests pin each normalizer's documented contract with a golden corpus and
assert the intentional DIVERGENCES between them. If a future refactor accidentally
changes any normalizer's output, or makes one silently delegate to another with
different semantics, exactly one of these tests goes RED -- catching the "four
copies of edition knowledge drift" the overhaul set out to prevent, without
forcing a dangerous data migration.
"""

from tuneshift import db as db_mod
from tuneshift.composer import matcher as composer_matcher
from tuneshift.identity import matching as identity_matching
from tuneshift.matching import normalize as matching_normalize


class TestDbNormalizerContract:
    """db.normalize_* is a stable, stored index key. Byte-output is pinned."""

    def test_normalize_title_golden(self):
        cases = {
            "Café del Mar": "café del mar",            # accents PRESERVED
            "Beyoncé": "beyoncé",
            "Song (Remastered 2009)": "song",           # remaster paren stripped
            "Song (Deluxe Edition)": "song",            # deluxe edition stripped
            "Song (Live at Wembley)": "song (live at wembley)",  # live kept
            "Track (feat. Drake)": "track (feat. drake)",        # feat kept
            "The Killers": "the killers",               # title keeps leading "the"
            "Song (Taylor's Version)": "song (taylor's version)",  # NOT stripped
            "AC/DC & Friends": "ac/dc and friends",     # & -> and
            "Motörhead": "motörhead",                   # accents PRESERVED
            "Naïve": "naïve",
            "  Extra   Spaces  ": "extra spaces",       # whitespace collapsed
        }
        for raw, expected in cases.items():
            assert db_mod.normalize_title(raw) == expected, raw

    def test_normalize_title_none(self):
        assert db_mod.normalize_title(None) is None
        assert db_mod.normalize_title("   ") is None

    def test_normalize_artist_golden(self):
        cases = {
            "Café del Mar": "café del mar",
            "Beyoncé": "beyoncé",
            "The Killers": "killers",                   # artist strips leading "the"
            "AC/DC & Friends": "ac/dc and friends",
            "Motörhead": "motörhead",
            "  Extra   Spaces  ": "extra spaces",
        }
        for raw, expected in cases.items():
            assert db_mod.normalize_artist(raw) == expected, raw

    def test_stable_key_does_not_fold_accents(self):
        # The core safety invariant: db keys stay distinct across accents so the
        # albums UNIQUE(norm_title, artist_id, edition) constraint never merges
        # genuinely different releases. Folding here = a reindex migration.
        assert db_mod.normalize_title("Café") != db_mod.normalize_title("Cafe")
        assert db_mod.normalize_title("Naïve") != db_mod.normalize_title("Naive")

    def test_stable_key_keeps_feat_and_explicit(self):
        assert "feat" in (db_mod.normalize_title("X (feat. Y)") or "")
        assert "explicit" in (db_mod.normalize_title("X [Explicit]") or "")


class TestMatchingNormalizerContract:
    """matching.normalize_* is the aggressive comparison/equivalence key."""

    def test_normalize_title_golden(self):
        cases = {
            "Café del Mar": "cafe del mar",             # accents FOLDED
            "Beyoncé": "beyonce",
            "Song (Remastered 2009)": "song",
            "Song (Deluxe Edition)": "song",
            "Song (Taylor's Version)": "song",          # edition stripped
            "Track (feat. Drake)": "track",             # feat STRIPPED
            "Track [Explicit]": "track",                # explicit STRIPPED
            "Naïve": "naive",
        }
        for raw, expected in cases.items():
            assert matching_normalize.normalize_title(raw) == expected, raw

    def test_normalize_artist_golden(self):
        cases = {
            "Beyoncé": "beyonce",                       # accents FOLDED
            "The Killers": "killers",
            "Motörhead": "motorhead",
        }
        for raw, expected in cases.items():
            assert matching_normalize.normalize_artist(raw) == expected, raw

    def test_comparison_key_folds_accents(self):
        # Opposite invariant to the db key: equivalence WANTS café == cafe.
        assert matching_normalize.normalize_title("Café") == matching_normalize.normalize_title("Cafe")
        assert matching_normalize.normalize_artist("Beyoncé") == matching_normalize.normalize_artist("Beyonce")


class TestIdentitySearchNormalizerContract:
    """identity.normalize_*_for_search builds external query strings."""

    def test_title_for_search_golden(self):
        cases = {
            "Café del Mar": "Café del Mar",             # case + accents PRESERVED
            "Song (Remastered 2009)": "Song",           # version suffix stripped
            "Song (Deluxe Edition)": "Song",
            "Song (Taylor's Version)": "Song",
            "Song (Live at Wembley)": "Song (Live at Wembley)",  # non-version paren kept
            "The Killers": "The Killers",               # title keeps "the"
        }
        for raw, expected in cases.items():
            assert identity_matching.normalize_title_for_search(raw) == expected, raw

    def test_artist_for_search_golden(self):
        cases = {
            "The Killers": "Killers",                   # leading "the" stripped
            "Beyoncé": "Beyoncé",                       # case + accents PRESERVED
            "AC/DC & Friends": "AC/DC & Friends",
        }
        for raw, expected in cases.items():
            assert identity_matching.normalize_artist_for_search(raw) == expected, raw

    def test_search_preserves_surface_form(self):
        # Search recall depends on case/diacritics; must NOT be lowercased/folded.
        assert identity_matching.normalize_title_for_search("Beyoncé") == "Beyoncé"


class TestComposerTokenizerContract:
    """composer._normalize_text is a concept tokenizer, not a title normalizer."""

    def test_tokenizes_and_casefolds(self):
        assert composer_matcher._normalize_text("Defiant Anthem!") == "defiant anthem"
        assert composer_matcher._normalize_text("Peaceful, Calm") == "peaceful calm"

    def test_drops_punctuation_between_words(self):
        assert composer_matcher._normalize_text("rock & roll") == "rock roll"


class TestNormalizerDivergence:
    """The four normalizers intentionally DISAGREE. Lock the divergences so no
    future 'consolidation' silently makes one delegate to another."""

    def test_db_and_matching_disagree_on_accents(self):
        raw = "Café"
        assert db_mod.normalize_title(raw) != matching_normalize.normalize_title(raw)

    def test_db_and_matching_disagree_on_feat(self):
        raw = "Track (feat. Drake)"
        assert db_mod.normalize_title(raw) != matching_normalize.normalize_title(raw)

    def test_identity_search_preserves_case_unlike_others(self):
        raw = "Beyoncé"
        assert identity_matching.normalize_artist_for_search(raw) == "Beyoncé"
        assert db_mod.normalize_artist(raw) == "beyoncé"
        assert matching_normalize.normalize_artist(raw) == "beyonce"
