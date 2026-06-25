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


@dataclass
class AlbumResult:
    """An album search result from any platform."""

    platform_id: str
    title: str
    artist: str
    track_count: int = 0
    release_year: int | None = None


@dataclass
class ArtistResult:
    """An artist search result from any platform."""

    platform_id: str
    name: str


@dataclass
class PlaylistPin:
    """A pinned track position or adjacency constraint."""

    playlist_id: int
    track_id: int
    pin_type: str  # "opener", "closer", "anchor", "position"
    group_id: str | None = None  # for adjacency groups
    group_order: int | None = None  # position within group, or target index for "position" pins


@dataclass
class Artist:
    """A normalized artist entity in the library."""

    id: int | None = None
    name: str = ""
    norm_name: str = ""
    sort_name: str | None = None
    bio: str | None = None
    identity: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    identity_confidence: str = "unconfirmed"
    genres: list[str] = field(default_factory=list)
    origin: str | None = None
    active_start: int | None = None
    active_end: int | None = None
    mb_artist_id: str | None = None
    tidal_artist_id: int | None = None
    spotify_artist_uri: str | None = None
    lastfm_url: str | None = None
    wikipedia_url: str | None = None
    enrichment_sources: list[str] = field(default_factory=list)
    verified: bool = False
    enriched_at: str | None = None
    verified_at: str | None = None


@dataclass
class Album:
    """A normalized album entity in the library."""

    id: int | None = None
    title: str = ""
    norm_title: str = ""
    artist_id: int | None = None
    release_date: str | None = None
    release_type: str = "album"
    edition: str = "original"
    genres: list[str] = field(default_factory=list)
    mb_release_group_id: str | None = None
    tidal_album_id: int | None = None
    spotify_album_uri: str | None = None
    enriched_at: str | None = None


@dataclass
class BannedArtist:
    """An artist on the global ban list."""

    id: int | None = None
    name: str = ""
    norm_name: str = ""
    reason: str | None = None
