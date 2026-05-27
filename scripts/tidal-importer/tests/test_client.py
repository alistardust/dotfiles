"""Tests for client.py: Protocol, RateLimiter, retry logic."""
import time
from unittest.mock import patch

from tidal_importer.client import (
    TidalClientProtocol,
    RateLimiter,
    TrackResult,
    PlaylistInfo,
    _retry_with_backoff,
)


class TestRateLimiter:
    def test_first_call_no_wait(self):
        limiter = RateLimiter(max_per_second=4.0)
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05  # no significant wait

    def test_rapid_calls_throttled(self):
        limiter = RateLimiter(max_per_second=4.0)
        limiter.wait()
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.20  # at least 1/4 second gap

    def test_spaced_calls_not_throttled(self):
        limiter = RateLimiter(max_per_second=4.0)
        limiter.wait()
        time.sleep(0.30)
        start = time.monotonic()
        limiter.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05


class TestRetryWithBackoff:
    def test_succeeds_first_try(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            return "ok"

        result = _retry_with_backoff(fn, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count[0] == 1

    @patch("tidal_importer.client.time.sleep")
    def test_retries_on_429(self, mock_sleep):
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("HTTP 429 Too Many Requests")
            return "ok"

        result = _retry_with_backoff(fn, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count[0] == 3
        assert mock_sleep.call_count == 2

    def test_raises_non_retryable(self):
        def fn():
            raise ValueError("bad input")

        import pytest
        with pytest.raises(ValueError, match="bad input"):
            _retry_with_backoff(fn, max_retries=3, base_delay=0.01)

    @patch("tidal_importer.client.time.sleep")
    def test_raises_after_max_retries(self, mock_sleep):
        def fn():
            raise Exception("429 rate limited")

        import pytest
        with pytest.raises(Exception, match="429"):
            _retry_with_backoff(fn, max_retries=2, base_delay=0.01)

    @patch("tidal_importer.client.time.sleep")
    def test_retries_on_connection_error(self, mock_sleep):
        call_count = [0]

        def fn():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("Connection reset")
            return "done"

        result = _retry_with_backoff(fn, max_retries=3, base_delay=0.01)
        assert result == "done"
        assert call_count[0] == 2


class TestFakeClientProtocolCompliance:
    """Verify FakeTidalClient from conftest satisfies the Protocol."""

    def test_fake_has_search_track(self, fake_client):
        results = fake_client.search_track("test query")
        assert isinstance(results, list)

    def test_fake_has_create_playlist(self, fake_client):
        info = fake_client.create_playlist("Test Playlist")
        assert isinstance(info, PlaylistInfo)

    def test_fake_has_add_tracks(self, fake_client):
        info = fake_client.create_playlist("Test")
        count = fake_client.add_tracks(info.playlist_id, [1, 2, 3])
        assert count == 3

    def test_fake_has_get_playlist(self, fake_client):
        info = fake_client.create_playlist("Test")
        result = fake_client.get_playlist(info.playlist_id)
        assert result is not None
        assert result.name == "Test"

    def test_fake_get_nonexistent_playlist(self, fake_client):
        result = fake_client.get_playlist("nonexistent")
        assert result is None
