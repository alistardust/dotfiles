"""Tests for MusicBrainz per-call wall-clock timeout (BUG-4)."""

import time

from tuneshift.identity.sources.musicbrainz import MusicBrainzSource


def test_isrc_lookup_returns_none_on_timeout(monkeypatch):
    monkeypatch.setenv("TUNESHIFT_NETWORK_TIMEOUT", "0.1")

    def hang(*args, **kwargs):
        time.sleep(5.0)

    monkeypatch.setattr(
        "tuneshift.identity.sources.musicbrainz.musicbrainzngs.get_recordings_by_isrc",
        hang,
    )
    start = time.monotonic()
    assert MusicBrainzSource().lookup_isrc("USUG11904206") is None
    assert time.monotonic() - start < 2.0


def test_search_returns_empty_on_timeout(monkeypatch):
    monkeypatch.setenv("TUNESHIFT_NETWORK_TIMEOUT", "0.1")

    def hang(*args, **kwargs):
        time.sleep(5.0)

    monkeypatch.setattr(
        "tuneshift.identity.sources.musicbrainz.musicbrainzngs.search_recordings",
        hang,
    )
    result = MusicBrainzSource().search("The Weeknd", "Blinding Lights")
    assert result.recordings == []
