"""Removal positions must mean the same thing the track list meant.

``get_playlist_tracks`` compacts: it drops unavailable entries, entries with
no usable metadata, and entries the platform returned without an id. Callers
therefore index into a *compacted* list, and that is the index space
``remove_tracks_by_positions`` is handed.

Every removal path underneath indexes the *raw* listing instead. One skipped
entry before the target shifts every later index down by one, so the removal
lands on a bystander. These tests pin the translation.

The shape is identical for each platform: a three-entry playlist whose middle
entry is dropped, then a request to remove compacted position 1, which is the
third raw entry.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from tuneshift.models import TrackResult
from tuneshift.platforms.spotify import SpotifyClient
from tuneshift.platforms.tidal import TidalClient
from tuneshift.platforms.ytmusic import YTMusicClient


def _result(platform_id: str) -> TrackResult:
    return TrackResult(platform_id=platform_id, title=platform_id, artist="A", album="")


def _tidal_client(raw_tracks):
    client = TidalClient.__new__(TidalClient)
    client._rate_limiter = MagicMock()
    client._session = MagicMock()
    client._ensure_session = lambda: None
    client._call_with_retry = lambda fn: fn()
    client._track_to_result = lambda track: _result(str(track.id))
    playlist = MagicMock()
    playlist.tracks.return_value = raw_tracks
    client._session.playlist.return_value = playlist
    return client, playlist


def test_tidal_skipped_entry_shifts_the_removal_index() -> None:
    """The middle entry has no name, so Tidal drops it from the track list."""
    raw = [
        SimpleNamespace(id="t0", name="Zero"),
        SimpleNamespace(id="t1", name=None),
        SimpleNamespace(id="t2", name="Two"),
    ]
    client, playlist = _tidal_client(raw)

    assert [t.platform_id for t in client.get_playlist_tracks("pl-1")] == ["t0", "t2"]

    client.remove_tracks_by_positions("pl-1", [1])

    playlist.remove_by_indices.assert_called_once_with([2])


def test_tidal_unconvertible_entry_shifts_the_removal_index() -> None:
    """An entry that raises during conversion is dropped the same way."""
    raw = [
        SimpleNamespace(id="t0", name="Zero"),
        SimpleNamespace(id="boom", name="Boom"),
        SimpleNamespace(id="t2", name="Two"),
    ]
    client, playlist = _tidal_client(raw)

    def _convert(track):
        if track.id == "boom":
            raise ValueError("unavailable")
        return _result(str(track.id))

    client._track_to_result = _convert

    assert [t.platform_id for t in client.get_playlist_tracks("pl-1")] == ["t0", "t2"]

    client.remove_tracks_by_positions("pl-1", [1])

    playlist.remove_by_indices.assert_called_once_with([2])


def test_tidal_removal_is_unaffected_when_nothing_is_skipped() -> None:
    raw = [
        SimpleNamespace(id="t0", name="Zero"),
        SimpleNamespace(id="t1", name="One"),
        SimpleNamespace(id="t2", name="Two"),
    ]
    client, playlist = _tidal_client(raw)

    client.remove_tracks_by_positions("pl-1", [1])

    playlist.remove_by_indices.assert_called_once_with([1])


def test_tidal_multiple_positions_translate_and_stay_descending() -> None:
    """Descending order is what keeps earlier indices valid during removal."""
    raw = [
        SimpleNamespace(id="t0", name="Zero"),
        SimpleNamespace(id="t1", name=None),
        SimpleNamespace(id="t2", name="Two"),
        SimpleNamespace(id="t3", name=None),
        SimpleNamespace(id="t4", name="Four"),
    ]
    client, playlist = _tidal_client(raw)

    client.remove_tracks_by_positions("pl-1", [0, 2])

    playlist.remove_by_indices.assert_called_once_with([4, 0])


def _spotify_client(raw_items):
    client = SpotifyClient.__new__(SpotifyClient)
    spotify = MagicMock()
    client._ensure_session = lambda: spotify
    client._call_api = lambda fn: fn()
    spotify.playlist_tracks.return_value = {"items": raw_items, "total": len(raw_items)}
    return client, spotify


def test_spotify_skipped_entry_shifts_the_removal_position() -> None:
    """A local-only or unavailable item comes back with no id, and is dropped."""
    raw = [
        {"track": {"id": "s0", "name": "Zero", "artists": [], "album": {}}},
        {"track": None},
        {"track": {"id": "s2", "name": "Two", "artists": [], "album": {}}},
    ]
    client, spotify = _spotify_client(raw)

    assert [t.platform_id for t in client.get_playlist_tracks("pl-1")] == ["s0", "s2"]

    client.remove_tracks_by_positions("pl-1", [1])

    sent = spotify.playlist_remove_specific_occurrences_of_items.call_args[0][1]
    assert sent == [{"uri": "spotify:track:s2", "positions": [2]}]


def _spotify_paged_client(raw_items):
    """Serve raw_items 100 at a time, the way the Spotify API paginates."""
    client = SpotifyClient.__new__(SpotifyClient)
    spotify = MagicMock()
    client._ensure_session = lambda: spotify
    client._call_api = lambda fn: fn()

    def _page(playlist_id, offset=0, limit=100, fields=None):
        return {
            "items": raw_items[offset : offset + limit],
            "total": len(raw_items),
        }

    spotify.playlist_tracks.side_effect = _page
    return client, spotify


def test_spotify_raw_index_accounts_for_the_page_offset() -> None:
    """A track past the first page must keep its index in the whole playlist."""
    raw = [{"track": None}]
    raw += [
        {"track": {"id": f"s{n}", "name": f"Track {n}", "artists": [], "album": {}}}
        for n in range(1, 150)
    ]
    client, spotify = _spotify_paged_client(raw)

    tracks = client.get_playlist_tracks("pl-1")
    assert len(tracks) == 149
    assert tracks[0].platform_id == "s1"
    assert tracks[-1].platform_id == "s149"

    # Compacted position 120 is s121, which sits at raw index 121 on page two.
    client.remove_tracks_by_positions("pl-1", [120])

    sent = spotify.playlist_remove_specific_occurrences_of_items.call_args[0][1]
    assert sent == [{"uri": "spotify:track:s121", "positions": [121]}]


def _ytmusic_client(raw_items):
    client = YTMusicClient.__new__(YTMusicClient)
    calls: list[tuple] = []

    def _data_api(method, endpoint, params=None, **kwargs):
        calls.append((method, endpoint, dict(params or {})))
        if method == "delete":
            return {}
        return {"items": raw_items}

    client._data_api = _data_api
    return client, calls


def test_ytmusic_skipped_entry_shifts_the_deleted_item() -> None:
    """An item with no videoId is dropped from the track list."""
    raw = [
        {
            "id": "i0",
            "snippet": {"resourceId": {"videoId": "v0"}, "title": "Zero"},
        },
        {"id": "i1", "snippet": {"resourceId": {}, "title": "Gone"}},
        {
            "id": "i2",
            "snippet": {"resourceId": {"videoId": "v2"}, "title": "Two"},
        },
    ]
    client, calls = _ytmusic_client(raw)

    assert [t.platform_id for t in client.get_playlist_tracks("pl-1")] == ["v0", "v2"]

    client.remove_tracks_by_positions("pl-1", [1])

    deletes = [c for c in calls if c[0] == "delete"]
    assert [c[2]["id"] for c in deletes] == ["i2"]
