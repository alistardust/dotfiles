"""Tests for Discogs source."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tidal_importer.identity.sources.discogs import DiscogsSource


class TestDiscogsSearch:
    def test_no_credentials_returns_empty(self, tmp_path):
        source = DiscogsSource(credentials_path=tmp_path / "nonexistent.json")
        result = source.search("Artist", "Title")
        assert len(result.recordings) == 0

    def test_with_mocked_client(self, tmp_path):
        creds = tmp_path / "creds.json"
        creds.write_text('{"personal_access_token": "test-token"}')

        source = DiscogsSource(credentials_path=creds)

        mock_release = MagicMock()
        mock_release.title = "Artist - Title"
        mock_release.id = 12345
        mock_release.formats = [{"descriptions": ["LP", "Album"]}]
        mock_release.year = 2020
        mock_release.data = {"master_id": 67890}

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_release]
        source._client = mock_client

        result = source.search("Artist", "Title")
        assert len(result.recordings) == 1
        assert result.recordings[0].score == 0.70
        assert result.evidence.source == "discogs"

    def test_compilation_detected(self, tmp_path):
        creds = tmp_path / "creds.json"
        creds.write_text('{"personal_access_token": "test-token"}')

        source = DiscogsSource(credentials_path=creds)

        mock_release = MagicMock()
        mock_release.title = "Various - Greatest Hits"
        mock_release.id = 999
        mock_release.formats = [{"descriptions": ["Compilation", "CD"]}]
        mock_release.year = 2015
        mock_release.data = {"master_id": 111}

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_release]
        source._client = mock_client

        result = source.search("Various", "Greatest Hits")
        assert result.recordings[0].release_groups[0]["is_compilation"] is True


class TestCompilationCheck:
    def test_returns_true_for_compilation(self, tmp_path):
        creds = tmp_path / "creds.json"
        creds.write_text('{"personal_access_token": "test-token"}')

        source = DiscogsSource(credentials_path=creds)

        mock_release = MagicMock()
        mock_release.formats = [{"descriptions": ["Compilation"]}]

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_release]
        source._client = mock_client

        assert source.check_compilation("Various", "Now 100") is True

    def test_returns_false_for_studio_album(self, tmp_path):
        creds = tmp_path / "creds.json"
        creds.write_text('{"personal_access_token": "test-token"}')

        source = DiscogsSource(credentials_path=creds)

        mock_release = MagicMock()
        mock_release.formats = [{"descriptions": ["LP", "Album"]}]

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_release]
        source._client = mock_client

        assert source.check_compilation("Radiohead", "OK Computer") is False


class TestVerifyAlbumType:
    def test_confirmation_evidence(self, tmp_path):
        creds = tmp_path / "creds.json"
        creds.write_text('{"personal_access_token": "test-token"}')

        source = DiscogsSource(credentials_path=creds)

        mock_release = MagicMock()
        mock_release.formats = [{"descriptions": ["Compilation"]}]

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_release]
        source._client = mock_client

        evidence = source.verify_album_type("Various", "Hits", expected_compilation=True)
        assert evidence is not None
        assert evidence.evidence_type == "compilation_flag"
        assert evidence.confidence == 0.85

    def test_contradiction_evidence(self, tmp_path):
        creds = tmp_path / "creds.json"
        creds.write_text('{"personal_access_token": "test-token"}')

        source = DiscogsSource(credentials_path=creds)

        mock_release = MagicMock()
        mock_release.formats = [{"descriptions": ["LP", "Album"]}]

        mock_client = MagicMock()
        mock_client.search.return_value = [mock_release]
        source._client = mock_client

        evidence = source.verify_album_type("Artist", "Album", expected_compilation=True)
        assert evidence is not None
        assert evidence.evidence_type == "contradiction"
