from pathlib import Path
from types import SimpleNamespace
import pytest
from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.commands.curate_cmd import handle_curate


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "test.db")
    pid = d.create_playlist("Trans Wrath")
    d.set_goal(pid, "Trans fury and empowerment")
    # Add some tracks
    for i in range(15):
        track = Track(title=f"Track {i}", artist=f"Artist {i % 3}")
        tid = d.add_track(track)
        d.add_track_to_playlist(pid, tid, i)
        d.update_track_metadata(tid, {"energy": i * 0.06, "themes": ["rock"]})
    return d


class TestHandleCurate:
    def test_analyze_mode(self, db: Database, capsys) -> None:
        args = SimpleNamespace(
            playlist="Trans Wrath",
            mode="analyze",
            dry_run=False,
            strategy="quick",
        )
        result = handle_curate(args, db)
        assert result == 0
        out = capsys.readouterr().out
        assert "strongest" in out.lower() or "weakest" in out.lower()

    def test_trim_dry_run(self, db: Database, capsys) -> None:
        args = SimpleNamespace(
            playlist="Trans Wrath",
            mode="trim",
            dry_run=True,
            strategy="quick",
            target_tracks=10,
            hard_limit=12,
        )
        result = handle_curate(args, db)
        assert result == 0
        out = capsys.readouterr().out
        assert "dry run" in out.lower() or "would" in out.lower()

    def test_unknown_playlist_returns_error(self, db: Database) -> None:
        args = SimpleNamespace(
            playlist="Nonexistent",
            mode="analyze",
            dry_run=False,
            strategy="quick",
        )
        result = handle_curate(args, db)
        assert result == 1

    def test_empty_playlist_returns_error(self, db: Database) -> None:
        db.create_playlist("Empty Playlist")
        args = SimpleNamespace(
            playlist="Empty Playlist",
            mode="analyze",
            dry_run=False,
            strategy="quick",
        )
        result = handle_curate(args, db)
        assert result == 1

    def test_trim_applies_changes(self, db: Database, capsys) -> None:
        args = SimpleNamespace(
            playlist="Trans Wrath",
            mode="trim",
            dry_run=False,
            strategy="quick",
            target_tracks=10,
            hard_limit=12,
        )
        result = handle_curate(args, db)
        assert result == 0
        out = capsys.readouterr().out
        assert "trimmed" in out.lower() or "kept" in out.lower()
        
        # Verify the playlist was actually trimmed
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        track_ids = db.get_playlist_track_ids(pid)
        assert len(track_ids) <= 12
