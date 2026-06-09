"""Data models for tuneshift."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Track:
    """A canonical track in the library."""

    id: int | None = None
    title: str = ""
    artist: str = ""
    album: str | None = None
    duration_seconds: int | None = None
    isrc: str | None = None
    energy: float | None = None
    valence: float | None = None
    tempo: float | None = None
    key: str | None = None
    themes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PlatformMapping:
    """Maps a canonical track to a platform-specific ID."""

    track_id: int
    platform: str
    platform_track_id: str
    platform_title: str | None = None
    platform_artist: str | None = None
    platform_album: str | None = None
    match_score: int | None = None
    is_divergent: bool = False
    divergence_note: str | None = None
    status: str = "matched"
    user_approved: bool = False


@dataclass
class Playlist:
    """A canonical playlist."""

    id: int | None = None
    name: str = ""
    description: str | None = None
    auto_reorder: bool = False
    reorder_arc: str = "wave"


@dataclass
class PlatformPlaylist:
    """Links a canonical playlist to a platform."""

    playlist_id: int
    platform: str
    platform_playlist_id: str
    last_synced_at: str | None = None


@dataclass
class TrackResult:
    """A search result from any platform."""

    platform_id: str
    title: str
    artist: str
    album: str
    duration_seconds: int | None = None
    isrc: str | None = None


@dataclass
class PlaylistInfo:
    """Playlist metadata from any platform."""

    platform_id: str
    name: str
    num_tracks: int
