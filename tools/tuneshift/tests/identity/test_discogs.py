"""Tests for Discogs identity source."""

from unittest.mock import MagicMock, patch

from tuneshift.identity.sources.discogs import DiscogsSource


class TestDiscogsSearch:
    def test_search_returns_evidence(self):
        source = DiscogsSource.__new__(DiscogsSource)
        source._client = MagicMock()
        mock_results = MagicMock()
        mock_release = MagicMock()
        mock_release.title = "Heroes - Heroes"
        mock_release.data = {
            "artist": "David Bowie",
            "title": "Heroes",
            "master_id": 12345,
            "year": "1977",
        }
        mock_results.__iter__ = lambda self: iter([mock_release])
        mock_results.pages = 1
        source._client.search.return_value = mock_results
        result = source.search("David Bowie", "Heroes")
        assert result.evidence is not None
        assert result.evidence.source == "discogs"
        assert result.evidence.evidence_type == "release_confirmation"
        assert result.evidence.confidence == 0.05

    def test_search_no_results(self):
        source = DiscogsSource.__new__(DiscogsSource)
        source._client = MagicMock()
        mock_results = MagicMock()
        mock_results.__iter__ = lambda self: iter([])
        mock_results.pages = 0
        source._client.search.return_value = mock_results
        result = source.search("Unknown", "Nonexistent")
        assert result.evidence is None
        assert result.recordings == []


class TestDiscogsCredentials:
    @patch("tuneshift.identity.sources.discogs.Path")
    def test_missing_credentials_raises(self, mock_path):
        mock_path.return_value.exists.return_value = False
        source = DiscogsSource.__new__(DiscogsSource)
        source._credentials_path = mock_path.return_value
        source._client = None
        # Should not crash on init, client is lazy
