"""Discogs source for track identity resolution."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from tidal_importer.identity.models import Evidence, RecordingCandidate, SourceResult

logger = logging.getLogger(__name__)

DEFAULT_CREDENTIALS_PATH = Path.home() / ".local" / "share" / "tidal-importer" / "discogs_credentials.json"


class DiscogsSource:
    """Discogs API source for compilation detection and album verification."""

    def __init__(self, credentials_path: Path | None = None) -> None:
        self._credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self._token: str | None = None
        self._client = None
        self._load_credentials()

    def _load_credentials(self) -> None:
        if not self._credentials_path.exists():
            logger.warning("Discogs credentials not found at %s", self._credentials_path)
            return
        try:
            data = json.loads(self._credentials_path.read_text())
            self._token = data.get("personal_access_token")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load Discogs credentials: %s", e)

    def _get_client(self):
        if self._client is None:
            if not self._token:
                return None
            import discogs_client
            self._client = discogs_client.Client(
                "TuneShift/0.1",
                user_token=self._token,
            )
        return self._client

    def search(self, artist: str, title: str) -> SourceResult:
        """Search Discogs for a release matching artist and title."""
        client = self._get_client()
        if client is None:
            return SourceResult(recordings=[])

        try:
            results = client.search(f"{artist} - {title}", type="release")
            candidates = []
            for release in results:
                formats = release.formats or []
                descriptions = []
                for fmt in formats:
                    descriptions.extend(fmt.get("descriptions", []))

                candidate = RecordingCandidate(
                    title=release.title,
                    artist=artist,
                    score=0.70,
                )
                candidate.release_groups = [{
                    "discogs_release_id": release.id,
                    "master_id": release.data.get("master_id"),
                    "year": release.year,
                    "is_compilation": "Compilation" in descriptions,
                    "descriptions": descriptions,
                }]
                candidates.append(candidate)
                break

            evidence = Evidence(
                id=f"discogs-search-{artist[:10]}-{title[:10]}",
                recording_id="",
                source="discogs",
                evidence_type="text_search",
                confidence=0.70 if candidates else 0.0,
            ) if candidates else None

            return SourceResult(recordings=candidates, evidence=evidence)
        except Exception as e:
            logger.warning("Discogs search failed: %s", e)
            return SourceResult(recordings=[])

    def check_compilation(self, artist: str, album_title: str) -> bool:
        """Check if a specific album is a compilation on Discogs."""
        client = self._get_client()
        if client is None:
            return False

        try:
            results = client.search(f"{artist} - {album_title}", type="release")
            for release in results:
                formats = release.formats or []
                for fmt in formats:
                    if "Compilation" in fmt.get("descriptions", []):
                        return True
                return False
        except Exception as e:
            logger.warning("Discogs compilation check failed: %s", e)
            return False

    def verify_album_type(
        self, artist: str, album_title: str, expected_compilation: bool
    ) -> Evidence | None:
        """Verify album classification against Discogs."""
        is_comp = self.check_compilation(artist, album_title)

        if is_comp == expected_compilation:
            return Evidence(
                id=f"discogs-verify-{artist[:10]}-{album_title[:10]}",
                recording_id="",
                source="discogs",
                evidence_type="compilation_flag",
                confidence=0.85,
            )
        else:
            return Evidence(
                id=f"discogs-contra-{artist[:10]}-{album_title[:10]}",
                recording_id="",
                source="discogs",
                evidence_type="contradiction",
                confidence=0.75,
            )
