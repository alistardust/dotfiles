"""Drift-guard contracts for the five normalizers (FL4).

TuneShift has five normalization functions that serve FOUR distinct concerns.
They must NOT be collapsed into one, because their outputs mean different things
and some are persisted:

1. ``matching.normalize_*`` -- COMPARISON / equivalence keys used by the scoring
   engine. Aggressive: folds Latin accents, strips feat/explicit/all editions,
   casefolds. Output is transient (recomputed every match).

1b. ``matching.fold_typography`` -- ROUND-TRIP identity. Folds accents,
   typographic punctuation, case and whitespace, and stops. Recognises a string
   as itself after something restyled it (a model echoing back a title), so it
   must NOT strip editions or feat: those distinguish rows the library holds
   separately.

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


class TestFoldTypographyContract:
    """matching.fold_typography is the round-trip identity key.

    Narrower than ``normalize_title`` on purpose. It recognises a string as
    itself after something restyled it, such as a language model echoing back
    a title it was handed, and it does not try to find the same song under a
    different release. Two rows the library holds separately must stay
    separate keys.
    """

    def test_fold_typography_golden(self):
        cases = {
            "Café del Mar": "cafe del mar",                  # accents FOLDED
            "I\u2019ll Feel Better": "i'll feel better",     # curly -> straight
            "Song  (Remastered 2009)": "song (remastered 2009)",  # edition KEPT
            "Track (feat. Drake)": "track (feat. drake)",    # feat KEPT
            "Track [Explicit]": "track [explicit]",          # explicit KEPT
            "  Spaced   Out  ": "spaced out",                # whitespace collapsed
            "": "",
        }
        for raw, expected in cases.items():
            assert matching_normalize.fold_typography(raw) == expected, raw

    def test_restyled_punctuation_folds_together(self):
        # The whole point: a model may return either apostrophe.
        straight = matching_normalize.fold_typography("I'll Feel Better")
        curly = matching_normalize.fold_typography("I\u2019ll Feel Better")
        assert straight == curly


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
    """The five normalizers intentionally DISAGREE. Lock the divergences so no
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

    def test_fold_typography_and_matching_disagree_on_editions(self):
        # The regression this pair exists to prevent: borrowing normalize_title
        # for round-trip identity collapses a remaster onto its original, and
        # the enrich ambiguity guard then refuses to classify either.
        plain, remaster = "Bohemian Rhapsody", "Bohemian Rhapsody (Remastered 2011)"
        assert matching_normalize.normalize_title(plain) == matching_normalize.normalize_title(remaster)
        assert matching_normalize.fold_typography(plain) != matching_normalize.fold_typography(remaster)

    def test_fold_typography_and_matching_disagree_on_feat(self):
        plain, feat = "Big Yellow Taxi", "Big Yellow Taxi (feat. Lucius)"
        assert matching_normalize.normalize_title(plain) == matching_normalize.normalize_title(feat)
        assert matching_normalize.fold_typography(plain) != matching_normalize.fold_typography(feat)

    def test_fold_typography_and_db_disagree_on_accents(self):
        raw = "Café"
        assert db_mod.normalize_title(raw) != matching_normalize.fold_typography(raw)


# The norm_* columns are written once at insert and read on every lookup. The
# golden corpus above pins what the normalizer emits; it cannot see rows that
# were indexed before an edit. This class holds the other end: a library whose
# norm_* values were frozen under today's normalizer, asserted to still be
# reachable through find_track, which recomputes the key at query time.
#
# These literals are deliberately NOT recomputed from the normalizer. Deriving
# them would move both sides together and pin nothing.
INDEXED_LIBRARY = [
    # title, artist, album, norm_title, norm_artist, norm_album
    ("Carey", "Joni Mitchell", "Blue", "carey", "joni mitchell", "blue"),
    (
        "Café Solo",
        "Sigur Rós",
        "Ágætis byrjun",
        "café solo",
        "sigur rós",
        "ágætis byrjun",
    ),
    (
        "Song (feat. Nico)",
        "The Velvet Underground",
        "Loaded",
        "song (feat. nico)",
        "velvet underground",
        "loaded",
    ),
    (
        "Black & White",
        "Earth & Fire",
        "Atlantis",
        "black and white",
        "earth and fire",
        "atlantis",
    ),
    (
        "Within You Without You",
        "The Beatles",
        "Sgt. Pepper (Remastered)",
        "within you without you",
        "beatles",
        "sgt. pepper",
    ),
    ("Hey   Jude", "The Beatles", None, "hey jude", "beatles", None),
    # One row per family the regex currently misses, stored as the library
    # holds them today. These are what a regex widening would strand: the
    # lookup would compute the stripped key and never reach the stored one.
    (
        "Them Bones",
        "Alice In Chains",
        "Dirt (2022 Remaster)",
        "them bones",
        "alice in chains",
        "dirt (2022 remaster)",
    ),
    (
        "Diamonds",
        "Rihanna",
        "Diamonds (Deluxe)",
        "diamonds",
        "rihanna",
        "diamonds (deluxe)",
    ),
    (
        "Kokomo",
        "The Beach Boys",
        "Sounds Of Summer (Expanded Edition)",
        "kokomo",
        "beach boys",
        "sounds of summer (expanded edition)",
    ),
    (
        "Sloop John B",
        "The Beach Boys",
        "Pet Sounds (50th Anniversary Edition)",
        "sloop john b",
        "beach boys",
        "pet sounds (50th anniversary edition)",
    ),
]


class TestStoredKeysStayReachableAfterANormalizerEdit:
    """A row indexed yesterday must still be found today, or it is a migration.

    Changing ``db.normalize_*`` does not rewrite the ``norm_*`` columns already
    on disk. ``find_track`` normalizes its arguments at query time, so an edit
    that is not paired with a backfill makes existing rows silently
    unreachable: the lookup misses, the caller concludes the track is new, and
    ingest writes a second library row for a song that was already there. No
    error is raised at any point.
    """

    def _library(self, tmp_path):
        db = db_mod.Database(tmp_path / "indexed.db")
        for title, artist, album, n_title, n_artist, n_album in INDEXED_LIBRARY:
            db.conn.execute(
                "INSERT INTO tracks "
                "(title, artist, album, norm_title, norm_artist, norm_album) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (title, artist, album, n_title, n_artist, n_album),
            )
        db.conn.commit()
        return db

    def test_every_indexed_row_is_still_reachable(self, tmp_path):
        db = self._library(tmp_path)
        for title, artist, album, *_ in INDEXED_LIBRARY:
            found = db.find_track(title, artist, album)
            assert found is not None, (
                f"{title!r} by {artist!r} was indexed under the frozen "
                f"normalizer and find_track can no longer reach it. The "
                f"normalizer changed without a backfill of norm_*; every "
                f"stored row is now stale and ingest will duplicate it."
            )
            assert found.title == title

    def test_a_stale_key_is_what_duplication_looks_like(self, tmp_path):
        # Demonstrates the failure the test above guards against, using a row
        # whose stored key was written under a normalizer that lowercased
        # nothing. This is the shape of every row in the library after an
        # unmigrated edit.
        db = db_mod.Database(tmp_path / "stale.db")
        db.conn.execute(
            "INSERT INTO tracks (title, artist, norm_title, norm_artist) "
            "VALUES (?, ?, ?, ?)",
            ("Carey", "Joni Mitchell", "Carey", "Joni Mitchell"),
        )
        db.conn.commit()
        assert db.find_track("Carey", "Joni Mitchell", None) is None
