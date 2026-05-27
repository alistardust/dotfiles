"""Shared test fixtures and test doubles."""
import pytest
from dataclasses import dataclass, field


@dataclass
class TrackResult:
    tidal_id: int
    title: str
    artist: str
    album: str
    duration: int = 0
    isrc: str = ""


@dataclass
class PlaylistInfo:
    playlist_id: str
    name: str


@dataclass
class FakePlaylist:
    """Internal state for a created playlist."""
    playlist_id: str
    name: str
    track_ids: list[int] = field(default_factory=list)


class FakeTidalClient:
    """Test double for TidalClient protocol. Uses dict-based state."""

    def __init__(
        self,
        search_results: dict[str, list[TrackResult]] | None = None,
        error_on_search: Exception | None = None,
    ):
        self._search_results = search_results or {}
        self._error_on_search = error_on_search
        self._playlists: dict[str, FakePlaylist] = {}
        self._next_id = 0
        self.search_call_count = 0

    def search_tracks(self, query: str, limit: int = 5) -> list[TrackResult]:
        self.search_call_count += 1
        if self._error_on_search:
            raise self._error_on_search
        return self._search_results.get(query, [])[:limit]

    def create_playlist(self, name: str) -> str:
        playlist_id = f"fake-playlist-{self._next_id}"
        self._next_id += 1
        self._playlists[playlist_id] = FakePlaylist(
            playlist_id=playlist_id, name=name
        )
        return playlist_id

    def add_tracks(self, playlist_id: str, track_ids: list[int]) -> None:
        if playlist_id not in self._playlists:
            raise ValueError(f"Playlist {playlist_id} not found")
        self._playlists[playlist_id].track_ids.extend(track_ids)

    def get_user_playlists(self) -> list[PlaylistInfo]:
        return [
            PlaylistInfo(playlist_id=p.playlist_id, name=p.name)
            for p in self._playlists.values()
        ]

    def get_playlist_tracks(self, playlist_id: str) -> list[int]:
        """Test helper: inspect what tracks were added."""
        if playlist_id not in self._playlists:
            return []
        return list(self._playlists[playlist_id].track_ids)


@pytest.fixture
def fake_client():
    return FakeTidalClient()
