"""Tidal discography source for track identity resolution."""

from __future__ import annotations

import logging

from tidal_importer.identity.matching import match_title
from tidal_importer.identity.models import Evidence, RecordingCandidate, SourceResult

logger = logging.getLogger(__name__)


class TidalSource:
    """Browse Tidal artist discography to find track on studio albums."""

    def __init__(self, client=None) -> None:
        self._client = client

    def search(
        self, artist: str, title: str, artist_id: int | None = None
    ) -> SourceResult:
        """Search artist discography for a track."""
        if self._client is None or artist_id is None:
            return SourceResult(recordings=[])

        try:
            albums = self._client.get_artist_albums(artist_id)
        except Exception as e:
            logger.warning("Tidal discography browse failed: %s", e)
            return SourceResult(recordings=[])

        candidates = []
        for album in albums:
            try:
                tracks = self._client.get_album_tracks(album.id)
            except Exception:
                continue

            for track in tracks:
                score = match_title(title, track.name)
                if score >= 0.85:
                    candidate = RecordingCandidate(
                        title=track.name,
                        artist=artist,
                        duration_ms=track.duration * 1000 if track.duration else None,
                        score=0.65,
                    )
                    candidate.release_groups = [{
                        "tidal_album_id": album.id,
                        "album_title": album.name,
                        "year": album.year,
                        "isrc": getattr(track, "isrc", None),
                    }]
                    candidates.append(candidate)
                    break

        evidence = Evidence(
            id=f"tidal-browse-{artist[:10]}-{title[:10]}",
            recording_id="",
            source="tidal_discography",
            evidence_type="discography_browse",
            confidence=0.65 if candidates else 0.0,
        ) if candidates else None

        return SourceResult(recordings=candidates, evidence=evidence)
