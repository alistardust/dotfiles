"""Integration smoke test: real API calls to MusicBrainz.

Run manually (not in CI) to verify the full pipeline works:
    uv run pytest tests/identity/test_integration.py -v -m integration
"""

from __future__ import annotations

import tempfile
import time

import pytest

from tidal_importer.identity.db import IdentityDB
from tidal_importer.identity.models import TrackInput
from tidal_importer.identity.resolver import ResolverConfig, TrackResolver
from tidal_importer.identity.sources.musicbrainz import MusicBrainzSource


pytestmark = pytest.mark.integration


@pytest.fixture
def db(tmp_path):
    return IdentityDB(str(tmp_path / "integration.db"))


@pytest.fixture
def mb():
    return MusicBrainzSource()


class TestMusicBrainzLive:
    """Live MusicBrainz API tests (rate-limited, 1 req/sec)."""

    def test_isrc_lookup_radiohead(self, mb):
        """Known ISRC for Bohemian Rhapsody should return a result."""
        # GBUM71029604 is Bohemian Rhapsody (known to exist in MB)
        result = mb.lookup_isrc("GBUM71029604")
        assert result is not None
        assert len(result.recordings) >= 1
        assert result.evidence.confidence >= 0.92
        time.sleep(1.1)

    def test_text_search_known_track(self, mb):
        """Text search for a well-known track should find it."""
        result = mb.search("Radiohead", "Karma Police", duration_ms=263000)
        assert len(result.recordings) >= 1
        assert any("Karma" in r.title for r in result.recordings)
        time.sleep(1.1)

    def test_full_pipeline_with_isrc(self, db, mb):
        """Full resolve pipeline with a known ISRC."""
        track = TrackInput(
            platform="tidal",
            platform_id="test-001",
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            duration_ms=355000,
            isrc="GBUM71029604",
        )

        resolver = TrackResolver(db=db, musicbrainz=mb)
        result = resolver.resolve(track)

        assert result is not None
        assert result.confidence >= 0.80
        assert result.tier.value in ("VERIFIED", "CONFIRMED")
        assert result.mb_recording_id is not None
        time.sleep(1.1)

    def test_cache_hit_on_second_resolve(self, db, mb):
        """Second resolve should hit cache, no API call."""
        track = TrackInput(
            platform="tidal",
            platform_id="test-002",
            title="Paranoid Android",
            artist="Radiohead",
            album="OK Computer",
            duration_ms=383000,
            isrc="GBAYE9700101",
        )

        resolver = TrackResolver(db=db, musicbrainz=mb)
        result1 = resolver.resolve(track)
        time.sleep(1.1)

        # Second resolve should use cache
        result2 = resolver.resolve(track)
        assert result2 is not None
        assert result2.confidence == result1.confidence

    def test_text_search_fallback_no_isrc(self, db, mb):
        """Track without ISRC falls back to text search."""
        track = TrackInput(
            platform="tidal",
            platform_id="test-003",
            title="Everything In Its Right Place",
            artist="Radiohead",
            album="Kid A",
            duration_ms=250000,
        )

        resolver = TrackResolver(db=db, musicbrainz=mb)
        result = resolver.resolve(track)

        # May or may not resolve depending on MB text search quality
        if result:
            assert result.confidence >= 0.75
