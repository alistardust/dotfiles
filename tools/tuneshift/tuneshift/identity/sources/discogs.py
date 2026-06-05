"""Discogs source for identity resolution confirmation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tuneshift.identity.models import Evidence, SourceResult

logger = logging.getLogger(__name__)

DEFAULT_CREDENTIALS_PATH = (
    Path.home() / ".local" / "share" / "tuneshift" / "discogs_token"
)


class DiscogsSource:
    """Discogs release confirmation source.

    Provides independent verification (+0.05 confidence bonus) when a release
    is found matching artist + title on Discogs.
    """

    def __init__(self, credentials_path: Path | None = None) -> None:
        self._credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self._client: Any | None = None

    def _get_client(self) -> Any:
        """Lazy-load Discogs client."""
        if self._client is not None:
            return self._client

        if not self._credentials_path.exists():
            raise FileNotFoundError(
                f"Discogs token not found at {self._credentials_path}. "
                "Create it with your Discogs personal access token."
            )

        import discogs_client

        token = self._credentials_path.read_text().strip()
        self._client = discogs_client.Client("TuneShift/0.1", user_token=token)
        return self._client

    def search(self, artist: str, title: str) -> SourceResult:
        """Search Discogs for release confirmation."""
        try:
            client = self._get_client()
            results = client.search(title, artist=artist, type="release")
            found = any(True for _ in results)

            if not found:
                return SourceResult(recordings=[])

            evidence = Evidence(
                source="discogs",
                evidence_type="release_confirmation",
                confidence=0.05,
            )
            return SourceResult(recordings=[], evidence=evidence)

        except FileNotFoundError:
            logger.warning("Discogs credentials not configured, skipping")
            return SourceResult(recordings=[])
        except Exception:
            logger.debug("Discogs search failed for %s - %s", artist, title)
            return SourceResult(recordings=[])
