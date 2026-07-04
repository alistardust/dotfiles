"""Tests for the Spotify album/artist search surface added for matching parity.

These mock the underlying spotipy client (client._sp) and exercise the response
mapping only — no network, no auth.
"""
from unittest.mock import MagicMock

import pytest

from tuneshift.platforms.spotify import SpotifyClient


@pytest.fixture
def client():
    # Pass an explicit client_id so construction never reaches the env/1Password
    # credential lookup — these tests mock _sp and must stay hermetic ("no
    # network, no auth", per the module docstring).
    c = SpotifyClient(client_id="test-client-id")
    c._sp = MagicMock()
    return c


def test_search_album_maps_fields(client):
    client._sp.search.return_value = {
        "albums": {"items": [
            {"id": "al1", "name": "Rumours", "artists": [{"name": "Fleetwood Mac"}],
             "total_tracks": 11, "release_date": "1977-02-04"},
            {"id": "", "name": "skip-me"},
        ]}
    }
    albums = client.search_album("Rumours Fleetwood Mac")
    assert len(albums) == 1
    assert albums[0].platform_id == "al1"
    assert albums[0].title == "Rumours"
    assert albums[0].artist == "Fleetwood Mac"
    assert albums[0].track_count == 11
    assert albums[0].release_year == 1977


def test_search_album_handles_missing_release_date(client):
    client._sp.search.return_value = {
        "albums": {"items": [
            {"id": "al1", "name": "X", "artists": [], "total_tracks": 0},
        ]}
    }
    albums = client.search_album("X")
    assert albums[0].release_year is None
    assert albums[0].artist == ""


def test_get_album_tracks_injects_album_name_and_paginates(client):
    client._sp.album.return_value = {
        "name": "Rumours",
        "tracks": {
            "items": [
                {"id": "t1", "name": "Dreams", "artists": [{"name": "Fleetwood Mac"}],
                 "duration_ms": 257000},
            ],
            "next": "cursor",
        },
    }
    client._sp.next.return_value = {
        "items": [
            {"id": "t2", "name": "The Chain", "artists": [{"name": "Fleetwood Mac"}],
             "duration_ms": 268000},
        ],
        "next": None,
    }
    tracks = client.get_album_tracks("al1")
    assert [t.platform_id for t in tracks] == ["t1", "t2"]
    assert all(t.album == "Rumours" for t in tracks)
    assert tracks[0].duration_seconds == 257


def test_search_artist_enriches_result(client):
    client._sp.search.return_value = {
        "artists": {"items": [
            {"id": "ar1", "name": "Radiohead", "popularity": 82,
             "genres": ["rock", "alternative"], "followers": {"total": 9000000}},
        ]}
    }
    artists = client.search_artist("Radiohead")
    assert len(artists) == 1
    a = artists[0]
    assert a.platform_id == "ar1"
    assert a.name == "Radiohead"
    assert a.popularity == 82
    assert a.genres == ["rock", "alternative"]
    assert a.followers == 9000000


def test_search_artist_tolerates_missing_enrichment(client):
    client._sp.search.return_value = {
        "artists": {"items": [{"id": "ar1", "name": "Obscure"}]}
    }
    a = client.search_artist("Obscure")[0]
    assert a.popularity is None
    assert a.genres == []
    assert a.followers is None


def test_get_artist_albums_maps_items(client):
    client._sp.artist_albums.return_value = {
        "items": [
            {"id": "al1", "name": "OK Computer", "artists": [{"name": "Radiohead"}],
             "total_tracks": 12, "release_date": "1997"},
            {"id": "", "name": "skip"},
        ]
    }
    albums = client.get_artist_albums("ar1")
    assert len(albums) == 1
    assert albums[0].title == "OK Computer"
    assert albums[0].release_year == 1997


def test_search_track_captures_is_playable(client):
    client._sp.search.return_value = {
        "tracks": {"items": [
            {"id": "t1", "name": "Song", "artists": [{"name": "A"}],
             "album": {"name": "Alb"}, "duration_ms": 200000,
             "external_ids": {"isrc": "X"}, "is_playable": False},
        ]}
    }
    tracks = client.search_track("q")
    assert tracks[0].available is False


def test_search_track_derives_availability_from_markets(client):
    client._sp.search.return_value = {
        "tracks": {"items": [
            {"id": "t1", "name": "Song", "artists": [{"name": "A"}],
             "album": {"name": "Alb"}, "available_markets": []},
            {"id": "t2", "name": "Song2", "artists": [{"name": "A"}],
             "album": {"name": "Alb"}, "available_markets": ["US"]},
        ]}
    }
    tracks = client.search_track("q")
    assert tracks[0].available is False
    assert tracks[1].available is True


def test_search_track_availability_unknown_when_absent(client):
    client._sp.search.return_value = {
        "tracks": {"items": [
            {"id": "t1", "name": "Song", "artists": [{"name": "A"}],
             "album": {"name": "Alb"}},
        ]}
    }
    tracks = client.search_track("q")
    assert tracks[0].available is None


def test_search_track_passes_market_from_token(client):
    client._sp.search.return_value = {"tracks": {"items": []}}
    client.search_track("q")
    _, kwargs = client._sp.search.call_args
    assert kwargs.get("market") == "from_token"
