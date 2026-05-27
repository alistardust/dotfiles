"""Tidal API client with Protocol for DI and retry logic."""
import time
import random
import typing
from pathlib import Path
from dataclasses import dataclass

import tidalapi

from tidal_importer.paths import secure_write, validate_no_symlink


@dataclass(frozen=True)
class TrackResult:
    """A search result from Tidal."""
    tidal_id: int
    title: str
    artist: str
    album: str


@dataclass(frozen=True)
class PlaylistInfo:
    """Info about a created/existing playlist."""
    playlist_id: str
    name: str
    num_tracks: int


class TidalClientProtocol(typing.Protocol):
    """Protocol for Tidal API operations (enables DI/testing)."""

    def search_track(self, query: str, limit: int = 10) -> list[TrackResult]: ...
    def create_playlist(self, name: str, description: str = "") -> PlaylistInfo: ...
    def add_tracks(self, playlist_id: str, track_ids: list[int]) -> int: ...
    def get_playlist(self, playlist_id: str) -> PlaylistInfo | None: ...


class RateLimiter:
    """Token bucket rate limiter. Max requests per second."""

    def __init__(self, max_per_second: float = 4.0):
        self._min_interval = 1.0 / max_per_second
        self._last_call = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


def _retry_with_backoff(
    fn: typing.Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> typing.Any:
    """Retry fn with exponential backoff + jitter on rate limit errors."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            if attempt == max_retries:
                raise
            # Retry on 429 or connection errors
            err_str = str(e).lower()
            if "429" in err_str or "rate" in err_str or "connection" in err_str:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(delay)
            else:
                raise


SESSION_DIR = Path.home() / ".local" / "share" / "tidal-importer"
SESSION_FILE = SESSION_DIR / "session.json"


class TidalClient:
    """Real Tidal API client using tidalapi."""

    def __init__(self, session_path: Path | None = None):
        self._session_path = session_path or SESSION_FILE
        self._rate_limiter = RateLimiter(max_per_second=4.0)
        self._session: tidalapi.Session | None = None

    def login(self) -> str:
        """Start OAuth login flow. Returns the login URL for the user."""
        self._session = tidalapi.Session()
        login, future = self._session.login_oauth()
        return login.verification_uri_complete

    def login_wait(self) -> bool:
        """Wait for the user to complete OAuth. Returns True on success."""
        if self._session is None:
            raise RuntimeError("Call login() first")
        # tidalapi handles the polling internally
        if self._session.check_login():
            self._save_session()
            return True
        return False

    def load_session(self) -> bool:
        """Load a saved session from disk. Returns True if valid."""
        validate_no_symlink(self._session_path)
        if not self._session_path.exists():
            return False
        import json
        data = json.loads(self._session_path.read_text())
        self._session = tidalapi.Session()
        return self._session.load_oauth_session(
            data["token_type"],
            data["access_token"],
            data["refresh_token"],
            data.get("expiry_time"),
        )

    def _save_session(self) -> None:
        """Persist session token securely (0600)."""
        if self._session is None:
            return
        import json
        data = json.dumps({
            "token_type": self._session.token_type,
            "access_token": self._session.access_token,
            "refresh_token": self._session.refresh_token,
            "expiry_time": str(self._session.expiry_time) if self._session.expiry_time else None,
        })
        secure_write(self._session_path, data)

    def search_track(self, query: str, limit: int = 10) -> list[TrackResult]:
        """Search for tracks. Rate-limited with retry."""
        self._ensure_session()
        self._rate_limiter.wait()

        def _do_search():
            results = self._session.search(query, models=[tidalapi.media.Track], limit=limit)
            tracks = results.get("tracks", []) or []
            return [
                TrackResult(
                    tidal_id=t.id,
                    title=t.name or "",
                    artist=t.artist.name if t.artist else "",
                    album=t.album.name if t.album else "",
                )
                for t in tracks
            ]

        return _retry_with_backoff(_do_search)

    def create_playlist(self, name: str, description: str = "") -> PlaylistInfo:
        """Create a new playlist."""
        self._ensure_session()
        self._rate_limiter.wait()

        def _do_create():
            playlist = self._session.user.create_playlist(name, description)
            return PlaylistInfo(
                playlist_id=str(playlist.id),
                name=playlist.name,
                num_tracks=playlist.num_tracks or 0,
            )

        return _retry_with_backoff(_do_create)

    def add_tracks(self, playlist_id: str, track_ids: list[int]) -> int:
        """Add tracks to a playlist. Returns number added."""
        self._ensure_session()
        self._rate_limiter.wait()

        def _do_add():
            playlist = self._session.playlist(playlist_id)
            playlist.add(track_ids)
            return len(track_ids)

        return _retry_with_backoff(_do_add)

    def get_playlist(self, playlist_id: str) -> PlaylistInfo | None:
        """Get playlist info. Returns None if not found."""
        self._ensure_session()
        self._rate_limiter.wait()

        def _do_get():
            try:
                playlist = self._session.playlist(playlist_id)
                return PlaylistInfo(
                    playlist_id=str(playlist.id),
                    name=playlist.name,
                    num_tracks=playlist.num_tracks or 0,
                )
            except Exception:
                return None

        return _retry_with_backoff(_do_get)

    def _ensure_session(self) -> None:
        if self._session is None or not self._session.check_login():
            raise RuntimeError("Not logged in. Call login() or load_session() first.")
