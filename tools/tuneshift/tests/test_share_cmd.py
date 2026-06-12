"""Tests for the share command."""
from pathlib import Path
from unittest.mock import patch
import pytest
from tuneshift.db import Database
from tuneshift.commands.share_cmd import handle_share, PLATFORM_URL_TEMPLATES


@pytest.fixture
def db_with_links(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    pid = db.create_playlist("Test Playlist")
    db.link_platform_playlist(pid, "tidal", "abc-123-def")
    db.link_platform_playlist(pid, "ytmusic", "PLtest123")
    db.link_platform_playlist(pid, "spotify", "6rqhFgbbKwnb9MLmUQDhG6")
    return db


class Args:
    def __init__(self, name: str, fmt: str = "plain"):
        self.name = name
        self.format = fmt


class TestShareCommand:
    def test_plain_output(self, db_with_links: Database, capsys) -> None:
        rc = handle_share(Args("Test Playlist"), db_with_links)
        assert rc == 0
        out = capsys.readouterr().out
        assert "tidal.com/playlist/abc-123-def" in out
        assert "music.youtube.com/playlist?list=PLtest123" in out
        assert "open.spotify.com/playlist/6rqhFgbbKwnb9MLmUQDhG6" in out

    def test_markdown_output(self, db_with_links: Database, capsys) -> None:
        rc = handle_share(Args("Test Playlist", "markdown"), db_with_links)
        assert rc == 0
        out = capsys.readouterr().out
        assert "**Test Playlist**" in out
        assert "[Tidal](" in out
        assert "[YouTube Music](" in out

    def test_slack_output(self, db_with_links: Database, capsys) -> None:
        rc = handle_share(Args("Test Playlist", "slack"), db_with_links)
        assert rc == 0
        out = capsys.readouterr().out
        assert "*Test Playlist*" in out
        assert ":headphones:" in out
        assert "<https://tidal.com/playlist/abc-123-def|Tidal>" in out

    def test_urls_only(self, db_with_links: Database, capsys) -> None:
        rc = handle_share(Args("Test Playlist", "urls"), db_with_links)
        assert rc == 0
        out = capsys.readouterr().out
        lines = [l for l in out.strip().split("\n") if l]
        assert len(lines) == 3
        assert all(l.startswith("https://") for l in lines)

    def test_not_found(self, db_with_links: Database, capsys) -> None:
        rc = handle_share(Args("Nonexistent"), db_with_links)
        assert rc == 1

    def test_no_links(self, tmp_path: Path, capsys) -> None:
        db = Database(tmp_path / "test.db")
        pid = db.create_playlist("Empty")
        rc = handle_share(Args("Empty"), db)
        assert rc == 1
        assert "No platform links" in capsys.readouterr().out
