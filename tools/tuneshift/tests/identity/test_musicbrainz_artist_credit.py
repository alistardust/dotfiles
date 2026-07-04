"""Regression tests for MusicBrainz artist-credit parsing.

MusicBrainz interleaves plain join-phrase STRINGS between artist dicts in an
``artist-credit`` list (and sometimes provides a bare string). The extractor
must tolerate both without raising ``AttributeError``.
"""
from tuneshift.identity.sources.musicbrainz import MusicBrainzSource


def test_extract_artist_name_with_interleaved_join_phrase_strings():
    source = MusicBrainzSource()
    artist_credit = [
        {"artist": {"name": "A Tribe Called Quest"}},
        " & ",
        {"artist": {"name": "Busta Rhymes"}},
    ]
    assert source._extract_artist_name(artist_credit) == "A Tribe Called Quest & Busta Rhymes"


def test_extract_artist_name_with_bare_string_credit():
    source = MusicBrainzSource()
    assert source._extract_artist_name("Solo Artist") == "Solo Artist"


def test_extract_artist_name_uses_joinphrase_field():
    source = MusicBrainzSource()
    artist_credit = [
        {"artist": {"name": "Simon"}, "joinphrase": " & "},
        {"artist": {"name": "Garfunkel"}},
    ]
    assert source._extract_artist_name(artist_credit) == "Simon & Garfunkel"


def test_extract_artist_name_empty_returns_unknown():
    source = MusicBrainzSource()
    assert source._extract_artist_name([]) == "Unknown"
