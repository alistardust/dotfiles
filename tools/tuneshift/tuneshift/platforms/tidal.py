"""Tidal platform client."""

import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import tidalapi

from tuneshift.models import PlaylistInfo, TrackResult
from tuneshift.platforms.auth import secure_write, validate_no_symlink
from tuneshift.platforms.rate_limiter import RateLimiter

_TOKEN_DIR = Path.home() / ".local" / "share" / "tuneshift"
_TOKEN_FILE = _TOKEN_DIR / "tidal.json"


def _retry(fn: Callable[[], Any], max_retries: int = 3) -> Any:
    """Retry a Tidal API call with exponential backoff."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            if attempt == max_retries:
                raise
            error_text = str(exc).lower()
            if "429" not in error_text and "rate" not in error_text and "connection" not in error_text:
                raise
            delay = (2**attempt) + random.uniform(0.0, 0.5)
            time.sleep(delay)
    raise RuntimeError("Unreachable retry state")


class TidalClient:
    """Tidal streaming platform client."""

    def __init__(self, token_path: Path | None = None) -> None:
        self._token_path = token_path or _TOKEN_FILE
        self._rate_limiter = RateLimiter(max_per_second=4.0)
        self._session: tidalapi.Session | None = None
        self._login_future: Any | None = None

    @property
    def platform_name(self) -> str:
        return "tidal"

    def login(self) -> str:
        """Start the Tidal device authorization flow and return the verification URL."""
        self._session = tidalapi.Session()
        login, self._login_future = self._call_with_retry(self._session.login_oauth)
        return str(login.verification_uri_complete)

    def login_wait(self, timeout: float = 300.0) -> bool:
        """Wait for the device authorization flow to complete."""
        if self._session is None or self._login_future is None:
            raise RuntimeError("Call login() first")
        try:
            self._login_future.result(timeout=timeout)
        except Exception:
            return False
        self._save_token()
        return True

    def load_session(self) -> bool:
        """Load a saved OAuth session from disk."""
        validate_no_symlink(self._token_path)
        if not self._token_path.exists():
            return False
        data = json.loads(self._token_path.read_text(encoding="utf-8"))
        expiry_time = _parse_expiry_time(data.get("expiry_time"))
        self._session = tidalapi.Session()
        return bool(
            self._session.load_oauth_session(
                data["token_type"],
                data["access_token"],
                data.get("refresh_token"),
                expiry_time,
                is_pkce=True,
            )
        )

    def search_track(self, query: str, limit: int = 10) -> list[TrackResult]:
        """Search for tracks on Tidal."""
        self._ensure_session()

        def _search() -> list[TrackResult]:
            assert self._session is not None
            results = self._session.search(query, models=[tidalapi.media.Track], limit=limit)
            tracks = results.get("tracks", []) or []
            return [self._track_to_result(track) for track in tracks]

        return self._call_with_retry(_search)

    def search_isrc(self, isrc: str) -> TrackResult | None:
        """Search for the first result whose ISRC matches exactly."""
        results = self.search_track(isrc, limit=5)
        normalized_isrc = isrc.upper()
        for result in results:
            if result.isrc and result.isrc.upper() == normalized_isrc:
                return result
        return None

    def get_playlist(self, playlist_id: str) -> PlaylistInfo | None:
        """Return playlist metadata or None if the playlist does not exist."""
        self._ensure_session()

        def _get_playlist() -> PlaylistInfo | None:
            assert self._session is not None
            try:
                playlist = self._session.playlist(playlist_id)
            except Exception as exc:
                error_text = str(exc).lower()
                if "404" in error_text or "not found" in error_text:
                    return None
                raise
            return PlaylistInfo(
                platform_id=str(playlist.id),
                name=playlist.name or "",
                num_tracks=int(playlist.num_tracks or 0),
            )

        return self._call_with_retry(_get_playlist)

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackResult]:
        """Return all tracks for a playlist in order."""
        self._ensure_session()

        def _get_tracks() -> list[TrackResult]:
            assert self._session is not None
            playlist = self._session.playlist(playlist_id)
            return [self._track_to_result(track) for track in playlist.tracks()]

        return self._call_with_retry(_get_tracks)

    def create_playlist(self, name: str, description: str = "") -> PlaylistInfo:
        """Create a new playlist for the authenticated user."""
        self._ensure_session()

        def _create_playlist() -> PlaylistInfo:
            assert self._session is not None
            playlist = self._session.user.create_playlist(name, description)
            return PlaylistInfo(
                platform_id=str(playlist.id),
                name=playlist.name or name,
                num_tracks=int(playlist.num_tracks or 0),
            )

        return self._call_with_retry(_create_playlist)

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> int:
        """Add tracks to a playlist and return the number requested."""
        self._ensure_session()

        def _add_tracks() -> int:
            assert self._session is not None
            playlist = self._session.playlist(playlist_id)
            playlist.add([int(track_id) for track_id in track_ids])
            return len(track_ids)

        return self._call_with_retry(_add_tracks)

    def remove_tracks_by_positions(self, playlist_id: str, positions: list[int]) -> int:
        """Remove tracks from a playlist by their zero-based positions."""
        self._ensure_session()
        if not positions:
            return 0

        def _remove_tracks() -> int:
            assert self._session is not None
            playlist = self._session.playlist(playlist_id)
            playlist.remove_by_indices(sorted(positions, reverse=True))
            return len(positions)

        return self._call_with_retry(_remove_tracks)

    def replace_playlist_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        """Replace the playlist contents with the provided track IDs."""
        self._ensure_session()

        def _replace_tracks() -> None:
            assert self._session is not None
            playlist = self._session.playlist(playlist_id)
            current_tracks = playlist.tracks()
            if current_tracks:
                playlist.remove_by_indices(list(range(len(current_tracks))))
            if track_ids:
                playlist.add([int(track_id) for track_id in track_ids])

        self._call_with_retry(_replace_tracks)

    def find_playlist_by_name(self, name: str) -> PlaylistInfo | None:
        """Find the first playlist owned by the user with the given name."""
        self._ensure_session()

        def _find_playlist() -> PlaylistInfo | None:
            assert self._session is not None
            for playlist in self._session.user.playlists():
                if playlist.name == name:
                    return PlaylistInfo(
                        platform_id=str(playlist.id),
                        name=playlist.name or "",
                        num_tracks=int(playlist.num_tracks or 0),
                    )
            return None

        return self._call_with_retry(_find_playlist)

    def _ensure_session(self) -> None:
        if self._session is None or not self._session.check_login():
            raise RuntimeError("Not logged in. Run: tuneshift login tidal")

    def _call_with_retry(self, fn: Callable[[], Any]) -> Any:
        self._rate_limiter.wait()
        return _retry(fn)

    def _save_token(self) -> None:
        if self._session is None:
            return
        data = {
            "token_type": self._session.token_type,
            "access_token": self._session.access_token,
            "refresh_token": self._session.refresh_token,
            "expiry_time": self._session.expiry_time.isoformat() if self._session.expiry_time else None,
        }
        secure_write(self._token_path, json.dumps(data))

    @staticmethod
    def _track_to_result(track: Any) -> TrackResult:
        return TrackResult(
            platform_id=str(track.id),
            title=track.name or "",
            artist=track.artist.name if getattr(track, "artist", None) else "",
            album=track.album.name if getattr(track, "album", None) else "",
            duration_seconds=track.duration if getattr(track, "duration", None) else None,
            isrc=getattr(track, "isrc", None),
        )


def _parse_expiry_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
