"""Tests for the resolve CLI command."""

from unittest.mock import MagicMock, patch

import pytest

from tuneshift.commands.resolve import run_resolve


class TestResolveCommand:
    def test_resolve_playlist_by_name(self, tmp_path):
        from tuneshift.db import Database
        from tuneshift.models import Track

        db = Database(tmp_path / "test.db")
        playlist_id = db.create_playlist("Diamond Dogs")
        track = Track(title="Diamond Dogs", artist="David Bowie", album="Diamond Dogs")
        track_id = db.add_track(track)
        db.add_track_to_playlist(playlist_id, track_id, position=0)

        args = MagicMock()
        args.playlist = "Diamond Dogs"
        args.track = None
        args.all = False
        args.upgrade = False
        args.force = False
        args.status = False
        args.verbose = False

        with patch("tuneshift.commands.resolve.resolve_playlist") as mock_rp:
            from tuneshift.identity.models import ResolutionResult, ResolutionStatus

            mock_rp.return_value = [
                ResolutionResult(
                    track_id=track_id,
                    status=ResolutionStatus.RESOLVED,
                    confidence_score=0.85,
                    confidence_tier=MagicMock(value="CONFIRMED"),
                    mb_recording_id="mb-1",
                )
            ]
            run_resolve(args, db)
            mock_rp.assert_called_once()

    def test_force_without_upgrade_errors(self, tmp_path):
        from tuneshift.db import Database

        db = Database(tmp_path / "test.db")
        args = MagicMock()
        args.playlist = None
        args.track = None
        args.all = False
        args.upgrade = False
        args.force = True
        args.status = False
        args.verbose = False

        with pytest.raises(SystemExit):
            run_resolve(args, db)
