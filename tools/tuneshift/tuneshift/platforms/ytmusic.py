"""YouTube Music platform client."""

import os
import stat
from pathlib import Path
from typing import Any

import ytmusicapi
from ytmusicapi import YTMusic

from tuneshift.models import PlaylistInfo, TrackResult
from tuneshift.platforms.auth import validate_no_symlink
from tuneshift.platforms.rate_limiter import RateLimiter

_TOKEN_DIR = Path.home() / ".local" / "share" / "tuneshift"
_TOKEN_FILE = _TOKEN_DIR / "ytmusic.json"


class YTMusicClient:
    """YouTube Music streaming platform client."""

    def __init__(self, token_path: Path | None = None) -> None:
        self._token_path = token_path or _TOKEN_FILE
        self._yt: YTMusic | None = None
        self._rate_limiter = RateLimiter(max_per_second=2.0)

    @property
    def platform_name(self) -> str:
        return "ytmusic"

    def login(self) -> bool:
        """Run the available YT Music authentication flow and load the saved session."""
        self._prepare_token_path()
        self._run_setup()
        self._fix_token_perms()
        return self.load_session()

    def load_session(self) -> bool:
        """Load a saved YT Music auth file from disk."""
        validate_no_symlink(self._token_path)
        if not self._token_path.exists():
            return False
        try:
            self._yt = YTMusic(str(self._token_path))
        except Exception:
            return False
        self._fix_token_perms()
        return True

    def search_track(self, query: str, limit: int = 10) -> list[TrackResult]:
        """Search YT Music songs by text."""
        ytmusic = self._ensure_session()
        items = self._call_api(lambda: ytmusic.search(query, filter="songs", limit=limit))
        return [self._to_result(item) for item in items if item.get("videoId")]

    def search_isrc(self, isrc: str) -> TrackResult | None:
        """YT Music does not support direct ISRC lookup."""
        return None

    def get_playlist(self, playlist_id: str) -> PlaylistInfo | None:
        """Return playlist metadata or None if it is unavailable."""
        ytmusic = self._ensure_session()
        try:
            playlist = self._call_api(lambda: ytmusic.get_playlist(playlist_id, limit=0))
        except Exception:
            return None
        return PlaylistInfo(
            platform_id=str(playlist_id),
            name=str(playlist.get("title", "")),
            num_tracks=_parse_track_count(playlist.get("trackCount")),
        )

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackResult]:
        """Return all tracks in the playlist."""
        ytmusic = self._ensure_session()
        playlist = self._call_api(lambda: ytmusic.get_playlist(playlist_id, limit=5000))
        tracks = playlist.get("tracks", [])
        return [self._to_result(track) for track in tracks if track.get("videoId")]

    def create_playlist(self, name: str, description: str = "") -> PlaylistInfo:
        """Create a YT Music playlist."""
        ytmusic = self._ensure_session()
        created = self._call_api(
            lambda: ytmusic.create_playlist(
                name,
                description or " ",
                privacy_status="PRIVATE",
            )
        )
        playlist_id = _extract_playlist_id(created)
        return PlaylistInfo(platform_id=playlist_id, name=name, num_tracks=0)

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> int:
        """Add tracks to a YT Music playlist."""
        ytmusic = self._ensure_session()
        if track_ids:
            self._call_api(lambda: ytmusic.add_playlist_items(playlist_id, track_ids))
        return len(track_ids)

    def remove_tracks_by_positions(self, playlist_id: str, positions: list[int]) -> int:
        """Remove playlist entries by zero-based positions."""
        ytmusic = self._ensure_session()
        if not positions:
            return 0
        playlist = self._call_api(lambda: ytmusic.get_playlist(playlist_id, limit=5000))
        tracks = playlist.get("tracks", [])
        to_remove = []
        for position in sorted(positions, reverse=True):
            if 0 <= position < len(tracks):
                to_remove.append(tracks[position])
        if to_remove:
            self._call_api(lambda: ytmusic.remove_playlist_items(playlist_id, to_remove))
        return len(to_remove)

    def replace_playlist_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        """Clear the playlist and re-add the provided tracks in order."""
        ytmusic = self._ensure_session()
        playlist = self._call_api(lambda: ytmusic.get_playlist(playlist_id, limit=5000))
        current_tracks = playlist.get("tracks", [])
        if current_tracks:
            self._call_api(lambda: ytmusic.remove_playlist_items(playlist_id, current_tracks))
        if track_ids:
            self._call_api(lambda: ytmusic.add_playlist_items(playlist_id, track_ids))

    def find_playlist_by_name(self, name: str) -> PlaylistInfo | None:
        """Find the first library playlist with the provided title."""
        ytmusic = self._ensure_session()
        playlists = self._call_api(lambda: ytmusic.get_library_playlists(limit=5000))
        for playlist in playlists:
            if playlist.get("title") == name:
                return PlaylistInfo(
                    platform_id=str(playlist.get("playlistId", "")),
                    name=str(playlist.get("title", "")),
                    num_tracks=_parse_track_count(playlist.get("count")),
                )
        return None

    def _fix_token_perms(self) -> None:
        if self._token_path.exists():
            os.chmod(self._token_path, stat.S_IRUSR | stat.S_IWUSR)

    def _prepare_token_path(self) -> None:
        validate_no_symlink(self._token_path)
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self._token_path.parent, stat.S_IRWXU)

    def _run_setup(self) -> None:
        self._rate_limiter.wait()
        if hasattr(YTMusic, "setup"):
            YTMusic.setup(filepath=str(self._token_path))
            return
        if hasattr(ytmusicapi, "setup_oauth"):
            ytmusicapi.setup_oauth(filepath=str(self._token_path), open_browser=True)
            return
        ytmusicapi.setup(filepath=str(self._token_path))

    def _call_api(self, fn: Any) -> Any:
        self._rate_limiter.wait()
        return fn()

    def _ensure_session(self) -> YTMusic:
        if self._yt is None:
            raise RuntimeError("Not logged in. Run: tuneshift login ytmusic")
        return self._yt

    @staticmethod
    def _to_result(item: dict[str, Any]) -> TrackResult:
        artists = item.get("artists", [])
        artist_name = artists[0].get("name", "") if artists else ""
        album = item.get("album") or {}
        if isinstance(album, dict):
            album_name = album.get("name", "")
        elif isinstance(album, str):
            album_name = album
        else:
            album_name = ""
        return TrackResult(
            platform_id=str(item.get("videoId", "")),
            title=str(item.get("title", "")),
            artist=artist_name,
            album=album_name,
            duration_seconds=_parse_duration_seconds(item),
            isrc=None,
        )


def _extract_playlist_id(created: str | dict[str, Any]) -> str:
    if isinstance(created, str):
        return created
    for key in ("id", "playlistId"):
        value = created.get(key)
        if value:
            return str(value)
    raise RuntimeError("YT Music did not return a playlist ID")


def _parse_track_count(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = "".join(ch for ch in value if ch.isdigit())
        if digits:
            return int(digits)
    return 0


def _parse_duration_seconds(item: dict[str, Any]) -> int | None:
    duration_seconds = item.get("duration_seconds")
    if isinstance(duration_seconds, int):
        return duration_seconds
    duration_text = item.get("duration")
    if not isinstance(duration_text, str) or not duration_text:
        return None
    parts = duration_text.split(":")
    if not all(part.isdigit() for part in parts):
        return None
    total = 0
    for part in parts:
        total = (total * 60) + int(part)
    return total
