"""Tests for the track identity resolver pipeline."""

from unittest.mock import MagicMock

import pytest

from tuneshift.identity.confidence import compute_confidence
from tuneshift.identity.models import (
    ConfidenceTier,
    Evidence,
    RecordingCandidate,
    ResolutionStatus,
    SourceResult,
    TrackInput,
)
from tuneshift.identity.resolver import ResolverConfig, TrackResolver


@pytest.fixture
def mock_store():
    """Mock IdentityStore (the Database adapter)."""
    store = MagicMock()
    store.get_resolution_state.return_value = (None, None, None)
    store.get_isrc.return_value = None
    return store


@pytest.fixture
def mock_mb():
    """Mock MusicBrainz source."""
    return MagicMock()


@pytest.fixture
def mock_discogs():
    """Mock Discogs source."""
    return MagicMock()


class TestResolverCacheCheck:
    def test_skips_fresh_confirmed_track(self, mock_store, mock_mb):
        mock_store.get_resolution_state.return_value = ("CONFIRMED", 0.85, "2026-06-01T00:00:00")
        resolver = TrackResolver(store=mock_store, musicbrainz=mock_mb)
        track = TrackInput(title="Heroes", artist="David Bowie")
        result = resolver.resolve(track_id=1, track=track)
        assert result.status == ResolutionStatus.SKIPPED
        mock_mb.lookup_isrc.assert_not_called()

    def test_resolves_stale_track(self, mock_store, mock_mb):
        mock_store.get_resolution_state.return_value = ("CONFIRMED", 0.85, "2025-01-01T00:00:00")
        mock_mb.lookup_isrc.return_value = None
        mock_mb.search.return_value = SourceResult(recordings=[])
        resolver = TrackResolver(store=mock_store, musicbrainz=mock_mb, config=ResolverConfig(upgrade_mode=True))
        track = TrackInput(title="Heroes", artist="David Bowie", isrc="GBAYE7700012")
        result = resolver.resolve(track_id=1, track=track)
        assert result.status != ResolutionStatus.SKIPPED


class TestResolverISRCLookup:
    def test_isrc_hit_resolves_verified(self, mock_store, mock_mb):
        mock_mb.lookup_isrc.return_value = SourceResult(
            recordings=[RecordingCandidate(title="Heroes", artist="David Bowie", mb_recording_id="mb-123", score=1.0)],
            evidence=Evidence(source="musicbrainz", evidence_type="isrc_lookup", confidence=0.95),
        )
        mock_mb.search.return_value = SourceResult(recordings=[])
        resolver = TrackResolver(store=mock_store, musicbrainz=mock_mb)
        track = TrackInput(title="Heroes", artist="David Bowie", isrc="GBAYE7700012")
        result = resolver.resolve(track_id=1, track=track)
        assert result.status == ResolutionStatus.RESOLVED
        assert result.mb_recording_id == "mb-123"
        mock_store.store_resolution.assert_called_once()


class TestResolverTextSearch:
    def test_text_search_fallback(self, mock_store, mock_mb, mock_discogs):
        mock_mb.lookup_isrc.return_value = None
        mock_mb.search.return_value = SourceResult(
            recordings=[RecordingCandidate(title="Heroes", artist="David Bowie", mb_recording_id="mb-456", score=0.95)],
            evidence=Evidence(source="musicbrainz", evidence_type="text_search", confidence=0.80),
        )
        mock_discogs.search.return_value = SourceResult(
            recordings=[],
            evidence=Evidence(source="discogs", evidence_type="release_confirmation", confidence=0.05),
        )
        resolver = TrackResolver(store=mock_store, musicbrainz=mock_mb, discogs=mock_discogs)
        track = TrackInput(title="Heroes", artist="David Bowie")
        result = resolver.resolve(track_id=1, track=track)
        assert result.status == ResolutionStatus.RESOLVED
        assert result.confidence_score >= 0.80


class TestResolverFailure:
    def test_all_sources_fail(self, mock_store, mock_mb, mock_discogs):
        mock_mb.lookup_isrc.return_value = None
        mock_mb.search.return_value = SourceResult(recordings=[])
        mock_discogs.search.return_value = SourceResult(recordings=[])
        resolver = TrackResolver(store=mock_store, musicbrainz=mock_mb, discogs=mock_discogs)
        track = TrackInput(title="Unknown", artist="Nobody")
        result = resolver.resolve(track_id=1, track=track)
        assert result.status == ResolutionStatus.FAILED
        mock_store.store_failed_evidence.assert_called_once()


class TestPublicAPI:
    def test_resolve_track_constructs_input(self, mock_store, mock_mb):
        from tuneshift.identity import resolve_track
        from tuneshift.models import Track

        mock_store.get_track.return_value = Track(
            id=1, title="Heroes", artist="David Bowie", album="Heroes",
            isrc="GBAYE7700012", duration_seconds=372,
        )
        mock_store.get_resolution_state.return_value = (None, None, None)
        mock_mb.lookup_isrc.return_value = SourceResult(
            recordings=[RecordingCandidate(title="Heroes", artist="David Bowie", mb_recording_id="mb-1", score=1.0)],
            evidence=Evidence(source="musicbrainz", evidence_type="isrc_lookup", confidence=0.95),
        )
        mock_mb.search.return_value = SourceResult(recordings=[])
        result = resolve_track(mock_store, track_id=1, musicbrainz=mock_mb)
        assert result.status == ResolutionStatus.RESOLVED
        assert result.track_id == 1

    def test_resolve_playlist_iterates(self, mock_store, mock_mb):
        from tuneshift.identity import resolve_playlist
        from tuneshift.models import Track

        tracks = [
            Track(id=1, title="Heroes", artist="David Bowie", duration_seconds=372),
            Track(id=2, title="Starman", artist="David Bowie", duration_seconds=256),
        ]
        mock_store.find_tracks_by_playlist.return_value = tracks
        mock_store.get_track.side_effect = lambda tid: next(t for t in tracks if t.id == tid)
        mock_store.get_resolution_state.return_value = (None, None, None)
        mock_mb.lookup_isrc.return_value = None
        mock_mb.search.return_value = SourceResult(recordings=[])

        results = resolve_playlist(mock_store, playlist_id=1, musicbrainz=mock_mb)
        assert len(results) == 2

    def test_resolve_playlist_sigint_returns_partial(self, mock_store, mock_mb):
        """SIGINT mid-batch returns results resolved so far."""
        import os
        import signal

        from tuneshift.identity import resolve_playlist
        from tuneshift.models import Track

        tracks = [
            Track(id=1, title="Heroes", artist="David Bowie", duration_seconds=372),
            Track(id=2, title="Starman", artist="David Bowie", duration_seconds=256),
            Track(id=3, title="Ziggy", artist="David Bowie", duration_seconds=194),
        ]
        mock_store.find_tracks_by_playlist.return_value = tracks
        mock_store.get_track.side_effect = lambda tid: next(t for t in tracks if t.id == tid)
        mock_store.get_resolution_state.return_value = (None, None, None)
        mock_mb.lookup_isrc.return_value = None

        call_count = [0]

        def slow_search(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                os.kill(os.getpid(), signal.SIGINT)
            return SourceResult(recordings=[])

        mock_mb.search.side_effect = slow_search

        results = resolve_playlist(mock_store, playlist_id=1, musicbrainz=mock_mb)
        assert len(results) < 3
        assert len(results) >= 1
