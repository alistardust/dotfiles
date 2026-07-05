"""i18n + structural normalization: accents, scripts, part-numbers, editions.

These lock the Chunk 8 internationalization behavior:

- Latin accents fold so "Beyoncé" matches "Beyonce" — accent-insensitive.
- CJK / kana scripts are preserved verbatim: we never transliterate 夜に駆ける
  to romaji, and we never strip Japanese dakuten (which would change the word).
- Unicode punctuation (curly quotes, en/em dashes, ellipsis) folds to ASCII.
- "Pt." / "Pt" abbreviations expand to "Part" so multi-part titles match.
- Ordinal-anniversary editions ("40th Anniversary Edition") are stripped like
  any other edition suffix.
- Multi-artist credits compare as a set, so collaborator order does not matter.
"""

from tuneshift.matching import normalize_artist, normalize_title
from tuneshift.matching.normalize import base_title, strip_version_markers
from tuneshift.matching.normalize import (
    artist_set_overlap,
    fold_accents,
    split_artist_roles,
    split_artists,
)


class TestAccentFolding:
    def test_latin_accents_fold_in_artist(self):
        assert normalize_artist("Beyoncé") == normalize_artist("Beyonce")

    def test_latin_accents_fold_in_title(self):
        assert normalize_title("Café del Mar") == "cafe del mar"

    def test_various_diacritics(self):
        assert fold_accents("Sinéad Ó'Connor") == "Sinead O'Connor"
        assert fold_accents("Motörhead") == "Motorhead"
        assert fold_accents("Björk") == "Bjork"
        assert fold_accents("Zoë") == "Zoe"


class TestScriptPreservation:
    def test_cjk_not_transliterated(self):
        # Japanese title must survive normalization intact (no romaji).
        assert normalize_title("夜に駆ける") == "夜に駆ける"

    def test_kana_dakuten_preserved(self):
        # が (ka + dakuten) must NOT be folded to か — that changes the word.
        assert fold_accents("がぎぐ") == "がぎぐ"

    def test_hangul_preserved(self):
        assert normalize_title("아이유") == "아이유"

    def test_mixed_script_folds_latin_only(self):
        # Latin accent folds; CJK stays.
        assert fold_accents("café 東京") == "cafe 東京"


class TestUnicodePunctuation:
    def test_curly_quotes_fold(self):
        assert normalize_title("\u201cQuoted\u201d Title\u2026") == '"quoted" title...'

    def test_dashes_fold_to_hyphen(self):
        # en-dash and em-dash both normalize to ASCII hyphen.
        assert normalize_title("A\u2013B") == normalize_title("A-B")
        assert normalize_title("A\u2014B") == normalize_title("A-B")


class TestPartNumberExpansion:
    def test_pt_abbreviation_expands(self):
        assert normalize_title("Another Brick in the Wall, Pt. 2") == \
            normalize_title("Another Brick in the Wall, Part 2")

    def test_pt_without_period(self):
        assert normalize_title("Song Pt 3") == normalize_title("Song Part 3")

    def test_pt_not_matched_midword(self):
        # "Ptolemy" must not become "Partolemy".
        assert normalize_title("Ptolemy") == "ptolemy"


class TestOrdinalAnniversaryStripping:
    def test_ordinal_anniversary_stripped(self):
        assert normalize_title("People's Instinctive Travels "
                               "(25th Anniversary Edition)") == \
            normalize_title("People's Instinctive Travels")

    def test_various_ordinals(self):
        assert normalize_title("Album (40th Anniversary Edition)") == "album"
        assert normalize_title("Album (1st Anniversary Edition)") == "album"
        assert normalize_title("Album (3rd Anniversary Edition)") == "album"


class TestMultiArtistSetOverlap:
    def test_split_basic(self):
        assert split_artists("Jay-Z & Alicia Keys") == {"jay-z", "alicia keys"}

    def test_split_separators(self):
        assert split_artists("A, B and C") == {"a", "b", "c"}
        assert split_artists("A feat. B") == {"a", "b"}
        assert split_artists("A x B") == {"a", "b"}

    def test_order_independent_overlap(self):
        assert artist_set_overlap(
            "Jay-Z & Alicia Keys", "Alicia Keys & Jay-Z"
        ) == 1.0

    def test_partial_overlap(self):
        # One of two collaborators matches.
        assert artist_set_overlap("A & B", "A & C") == 0.5

    def test_disjoint_overlap(self):
        assert artist_set_overlap("A & B", "C & D") == 0.0

    def test_single_artist_overlap(self):
        assert artist_set_overlap("Adele", "Adele") == 1.0


class TestArtistRoles:
    """split_artist_roles separates main from featured credits (M5)."""

    def test_no_feature_all_main(self):
        main, featured = split_artist_roles("Jay-Z & Alicia Keys")
        assert main == {"jay-z", "alicia keys"}
        assert featured == set()

    def test_feat_marker_splits_roles(self):
        main, featured = split_artist_roles("Eminem feat. Rihanna")
        assert main == {"eminem"}
        assert featured == {"rihanna"}

    def test_co_billed_mains_stay_main(self):
        # "with"/"&" join co-billed MAIN artists; only feat/ft/featuring is a role
        # boundary.
        main, featured = split_artist_roles("Calvin Harris & Dua Lipa")
        assert main == {"calvin harris", "dua lipa"}
        assert featured == set()

    def test_featured_never_also_main(self):
        main, featured = split_artist_roles("A feat. A")
        assert main == {"a"}
        assert featured == set()


class TestBaseTitle:
    """base_title strips trailing descriptive subtitles for the retitle blend."""

    def test_trailing_subtitle_is_stripped(self):
        assert base_title("Sample Song (One Descriptive Phrase)") == "Sample Song"
        assert base_title("Sample Song (Another Descriptive Phrase)") == "Sample Song"

    def test_leading_and_embedded_parens_preserved(self):
        # Integral parentheticals that are part of the song name must survive.
        assert base_title("(You Drive Me) Crazy") == "(You Drive Me) Crazy"
        assert base_title("(Sittin' On) The Dock of the Bay") == \
            "(Sittin' On) The Dock of the Bay"

    def test_stacked_trailing_groups_and_dash_suffix(self):
        assert base_title("Song (A) (B)") == "Song"
        assert base_title("Song (A) - B") == "Song"
        assert base_title("Song (Live - 2020)") == "Song"

    def test_stripping_to_empty_returns_original(self):
        assert base_title("(Instrumental)") == "(Instrumental)"

    def test_tempo_marker_is_a_version_marker_not_a_subtitle(self):
        # "(Sped Up)" is neutralized by strip_version_markers before base_title
        # ever runs, so the version axis (not the title blend) owns that call.
        assert strip_version_markers("Cornelia Street (Sped Up)") == "Cornelia Street"
        assert strip_version_markers("Song - Slowed Down") == "Song"
        assert strip_version_markers("Song (Nightcore)") == "Song"
