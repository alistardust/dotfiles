"""Tests for the import-text command."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from tuneshift.commands.import_text_cmd import _parse_playlist_file, handle_import_text
from tuneshift.db import Database


SAMPLE_PLAYLIST = """\
# Diamond Dogs
# 3 tracks
# Tidal playlist ID: abc-123-def

    1. David Bowie - Suffragette City [Ziggy Stardust]
    2. Queen - Killer Queen [Sheer Heart Attack]
    3. T. Rex - Get It On [Electric Warrior]
"""


class TestParsePlaylistFile:
    def test_extracts_name(self) -> None:
        lines = SAMPLE_PLAYLIST.splitlines()
        name, _, _ = _parse_playlist_file(lines)
        assert name == "Diamond Dogs"

    def test_extracts_tidal_id(self) -> None:
        lines = SAMPLE_PLAYLIST.splitlines()
        _, tidal_id, _ = _parse_playlist_file(lines)
        assert tidal_id == "abc-123-def"

    def test_extracts_tracks(self) -> None:
        lines = SAMPLE_PLAYLIST.splitlines()
        _, _, tracks = _parse_playlist_file(lines)
        assert len(tracks) == 3
        # (title, artist, album)
        assert tracks[0] == ("Suffragette City", "David Bowie", "Ziggy Stardust")
        assert tracks[1] == ("Killer Queen", "Queen", "Sheer Heart Attack")
        assert tracks[2] == ("Get It On", "T. Rex", "Electric Warrior")

    def test_handles_no_album(self) -> None:
        lines = ["# Minimal", "    1. Artist - Title"]
        _, _, tracks = _parse_playlist_file(lines)
        assert tracks == [("Title", "Artist", None)]

    def test_handles_empty_file(self) -> None:
        name, tidal_id, tracks = _parse_playlist_file([])
        assert name is None
        assert tidal_id is None
        assert tracks == []


class TestHandleImportText:
    def test_imports_new_playlist(self, tmp_path: Path) -> None:
        playlist_file = tmp_path / "test.txt"
        playlist_file.write_text(SAMPLE_PLAYLIST)
        db = Database(tmp_path / "test.db")
        args = SimpleNamespace(file=str(playlist_file), name=None, force=False)

        result = handle_import_text(args, db)

        assert result == 0
        pl = db.find_playlist_by_name("Diamond Dogs")
        assert pl is not None
        tracks = db.get_playlist_tracks(pl.id)
        assert len(tracks) == 3

    def test_links_tidal_id(self, tmp_path: Path) -> None:
        playlist_file = tmp_path / "test.txt"
        playlist_file.write_text(SAMPLE_PLAYLIST)
        db = Database(tmp_path / "test.db")
        args = SimpleNamespace(file=str(playlist_file), name=None, force=False)

        handle_import_text(args, db)

        pl = db.find_playlist_by_name("Diamond Dogs")
        platform_id = db.get_platform_playlist_id(pl.id, "tidal")
        assert platform_id == "abc-123-def"

    def test_rejects_duplicate_without_force(self, tmp_path: Path) -> None:
        playlist_file = tmp_path / "test.txt"
        playlist_file.write_text(SAMPLE_PLAYLIST)
        db = Database(tmp_path / "test.db")
        args = SimpleNamespace(file=str(playlist_file), name=None, force=False)

        handle_import_text(args, db)
        result = handle_import_text(args, db)

        assert result == 1

    def test_force_replaces_existing(self, tmp_path: Path) -> None:
        playlist_file = tmp_path / "test.txt"
        playlist_file.write_text(SAMPLE_PLAYLIST)
        db = Database(tmp_path / "test.db")
        args_no_force = SimpleNamespace(file=str(playlist_file), name=None, force=False)
        args_force = SimpleNamespace(file=str(playlist_file), name=None, force=True)

        handle_import_text(args_no_force, db)
        result = handle_import_text(args_force, db)

        assert result == 0
        pl = db.find_playlist_by_name("Diamond Dogs")
        tracks = db.get_playlist_tracks(pl.id)
        assert len(tracks) == 3

    def test_name_override(self, tmp_path: Path) -> None:
        playlist_file = tmp_path / "test.txt"
        playlist_file.write_text(SAMPLE_PLAYLIST)
        db = Database(tmp_path / "test.db")
        args = SimpleNamespace(file=str(playlist_file), name="Custom Name", force=False)

        handle_import_text(args, db)

        assert db.find_playlist_by_name("Custom Name") is not None
        assert db.find_playlist_by_name("Diamond Dogs") is None

    def test_file_not_found(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        args = SimpleNamespace(file="/nonexistent/path.txt", name=None, force=False)
        assert handle_import_text(args, db) == 1

    def test_deduplicates_tracks(self, tmp_path: Path) -> None:
        """Same track appearing in two playlists should not create duplicate."""
        file1 = tmp_path / "p1.txt"
        file1.write_text("# Neon Lights\n    1. Queen - Killer Queen [Sheer Heart Attack]\n")
        file2 = tmp_path / "p2.txt"
        file2.write_text("# Stargazer\n    1. Queen - Killer Queen [Sheer Heart Attack]\n")
        db = Database(tmp_path / "test.db")

        handle_import_text(SimpleNamespace(file=str(file1), name=None, force=False), db)
        handle_import_text(SimpleNamespace(file=str(file2), name=None, force=False), db)

        p1 = db.find_playlist_by_name("Neon Lights")
        p2 = db.find_playlist_by_name("Stargazer")
        p1_tracks = db.get_playlist_tracks(p1.id)
        p2_tracks = db.get_playlist_tracks(p2.id)
        # Same track object (same ID)
        assert p1_tracks[0].id == p2_tracks[0].id
