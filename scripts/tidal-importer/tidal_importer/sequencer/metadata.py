"""Multi-source track metadata fetcher with graceful degradation."""
import time
from typing import Any

from tidal_importer.sequencer.cache import TrackMetadata, MetadataCache


_CAMELOT_MAP: dict[tuple[int, int], str] = {
    (0, 1): "8B",
    (0, 0): "5A",
    (1, 1): "3B",
    (1, 0): "12A",
    (2, 1): "10B",
    (2, 0): "7A",
    (3, 1): "5B",
    (3, 0): "2A",
    (4, 1): "12B",
    (4, 0): "9A",
    (5, 1): "7B",
    (5, 0): "4A",
    (6, 1): "2B",
    (6, 0): "11A",
    (7, 1): "9B",
    (7, 0): "6A",
    (8, 1): "4B",
    (8, 0): "1A",
    (9, 1): "11B",
    (9, 0): "8A",
    (10, 1): "6B",
    (10, 0): "3A",
    (11, 1): "1B",
    (11, 0): "10A",
}


def isrc_to_camelot(key_note: int | None, mode: int | None) -> str | None:
    """Convert Spotify key_note plus mode values to a Camelot code."""
    if key_note is None or mode is None:
        return None
    return _CAMELOT_MAP.get((key_note, mode))


class SpotifySource:
    """Fetch audio features from Spotify via ISRC lookups."""

    def __init__(self, client: Any = None):
        self._client = client

    def fetch_features(self, isrcs: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch audio features for tracks by ISRC."""
        results: dict[str, dict[str, Any]] = {}
        if self._client is None:
            return results

        for isrc in isrcs:
            try:
                search_result = self._client.search(
                    f"isrc:{isrc}", type="track", limit=1
                )
                items = search_result.get("tracks", {}).get("items", [])
                if not items:
                    continue

                spotify_id = items[0]["id"]
                features_list = self._client.audio_features([spotify_id])
                if not features_list or features_list[0] is None:
                    continue

                feature_data = features_list[0]
                key_note = feature_data.get("key")
                mode = feature_data.get("mode")
                results[isrc] = {
                    "bpm": feature_data.get("tempo"),
                    "key_note": key_note,
                    "mode": mode,
                    "energy": feature_data.get("energy"),
                    "valence": feature_data.get("valence"),
                    "acousticness": feature_data.get("acousticness"),
                    "loudness": feature_data.get("loudness"),
                    "danceability": feature_data.get("danceability"),
                    "duration_ms": feature_data.get("duration_ms"),
                    "camelot_code": isrc_to_camelot(key_note, mode),
                }
                time.sleep(0.1)
            except Exception:
                continue
        return results


class MusicBrainzSource:
    """Fetch metadata from MusicBrainz by ISRC."""

    def __init__(self, client: Any = None):
        self._client = client

    def fetch_features(self, isrcs: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch available features from MusicBrainz."""
        results: dict[str, dict[str, Any]] = {}
        if self._client is None:
            return results

        for isrc in isrcs:
            try:
                result = self._client.get_recordings_by_isrc(isrc)
                recordings = result.get("isrc", {}).get("recording-list", [])
                if not recordings:
                    continue

                recording = recordings[0]
                length = recording.get("length")
                results[isrc] = {
                    "duration_ms": int(length) if length else None,
                }
                time.sleep(1.1)
            except Exception:
                continue
        return results


class LastFmSource:
    """Fetch tags from Last.fm via pylast."""

    def __init__(self, client: Any = None):
        self._client = client

    def fetch_tags(self, tracks: list[dict[str, str]]) -> dict[str, list[str]]:
        """Fetch top tags for a list of artist and title pairs."""
        results: dict[str, list[str]] = {}
        if self._client is None:
            return results

        for track in tracks:
            try:
                key = f"{track['artist']} - {track['title']}"
                lastfm_track = self._client.get_track(track["artist"], track["title"])
                top_tags = lastfm_track.get_top_tags(limit=10)
                results[key] = [
                    tag.item.name.lower()
                    for tag in top_tags
                    if hasattr(tag, "weight") and int(tag.weight) >= 25
                ]
                time.sleep(0.2)
            except Exception:
                continue
        return results


class MetadataFetcher:
    """Orchestrate metadata collection from multiple sources with caching."""

    def __init__(
        self,
        cache: MetadataCache,
        spotify_source: Any = None,
        musicbrainz_source: Any = None,
        lastfm_source: Any = None,
    ):
        self._cache = cache
        self._spotify = spotify_source
        self._musicbrainz = musicbrainz_source
        self._lastfm = lastfm_source

    def get_metadata(
        self,
        tracks: list[dict[str, Any]],
        progress_callback: Any = None,
    ) -> dict[str, TrackMetadata]:
        """Fetch metadata for all tracks, using cache first."""
        total = len(tracks)
        isrcs = [track["isrc"] for track in tracks]

        cached = self._cache.get_many(isrcs)
        results: dict[str, TrackMetadata] = dict(cached)

        uncached = [track for track in tracks if track["isrc"] not in cached]
        if not uncached:
            if progress_callback:
                progress_callback(total, total)
            return results

        uncached_isrcs = [track["isrc"] for track in uncached]

        spotify_features: dict[str, dict[str, Any]] = {}
        if self._spotify:
            try:
                spotify_features = self._spotify.fetch_features(uncached_isrcs)
            except Exception:
                spotify_features = {}

        mb_isrcs = [isrc for isrc in uncached_isrcs if isrc not in spotify_features]
        mb_features: dict[str, dict[str, Any]] = {}
        if self._musicbrainz and mb_isrcs:
            try:
                mb_features = self._musicbrainz.fetch_features(mb_isrcs)
            except Exception:
                mb_features = {}

        for index, track_info in enumerate(uncached):
            isrc = track_info["isrc"]
            features = spotify_features.get(isrc, mb_features.get(isrc, {}))

            metadata = TrackMetadata(
                isrc=isrc,
                tidal_id=track_info["tidal_id"],
                title=track_info["title"],
                artist=track_info["artist"],
                duration_ms=features.get("duration_ms"),
                bpm=features.get("bpm"),
                key_note=features.get("key_note"),
                mode=features.get("mode"),
                energy=features.get("energy"),
                valence=features.get("valence"),
                acousticness=features.get("acousticness"),
                loudness=features.get("loudness"),
                danceability=features.get("danceability"),
                camelot_code=features.get("camelot_code"),
                source="spotify"
                if isrc in spotify_features
                else "musicbrainz" if isrc in mb_features else None,
            )

            self._cache.save(metadata)
            results[isrc] = metadata

            if progress_callback:
                progress_callback(len(cached) + index + 1, total)

        return results
