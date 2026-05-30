"""Tests for the sequence CLI subcommand."""
import pytest
from unittest.mock import patch, MagicMock
from tidal_importer.cli import main


class TestSequenceArgParsing:
    def test_sequence_requires_playlist_id(self):
        with pytest.raises(SystemExit):
            main(["sequence"])

    def test_sequence_accepts_playlist_id(self):
        with patch("tidal_importer.cli._cmd_sequence") as mock_cmd:
            mock_cmd.return_value = 0
            result = main(["sequence", "abc-123"])
            assert result == 0
            args = mock_cmd.call_args[0][0]
            assert args.playlist_id == "abc-123"

    def test_sequence_accepts_profile(self):
        with patch("tidal_importer.cli._cmd_sequence") as mock_cmd:
            mock_cmd.return_value = 0
            main(["sequence", "abc-123", "--profile=psych-journey"])
            args = mock_cmd.call_args[0][0]
            assert args.profile == "psych-journey"

    def test_sequence_accepts_dry_run(self):
        with patch("tidal_importer.cli._cmd_sequence") as mock_cmd:
            mock_cmd.return_value = 0
            main(["sequence", "abc-123", "--dry-run"])
            args = mock_cmd.call_args[0][0]
            assert args.dry_run is True

    def test_sequence_accepts_save_as(self):
        with patch("tidal_importer.cli._cmd_sequence") as mock_cmd:
            mock_cmd.return_value = 0
            main(["sequence", "abc-123", "--save-as=My New Playlist"])
            args = mock_cmd.call_args[0][0]
            assert args.save_as == "My New Playlist"

    def test_sequence_accepts_weight_overrides(self):
        with patch("tidal_importer.cli._cmd_sequence") as mock_cmd:
            mock_cmd.return_value = 0
            main(["sequence", "abc-123", "--themes=0.5", "--energy=0.3"])
            args = mock_cmd.call_args[0][0]
            assert args.themes == 0.5
            assert args.energy == 0.3


class TestAuthSubcommand:
    def test_auth_requires_service(self):
        with pytest.raises(SystemExit):
            main(["auth"])

    def test_auth_spotify(self):
        with patch("tidal_importer.cli._cmd_auth") as mock:
            mock.return_value = 0
            result = main(["auth", "spotify"])
            assert result == 0
            args = mock.call_args[0][0]
            assert args.service == "spotify"

    def test_auth_lastfm(self):
        with patch("tidal_importer.cli._cmd_auth") as mock:
            mock.return_value = 0
            main(["auth", "lastfm"])
            args = mock.call_args[0][0]
            assert args.service == "lastfm"
