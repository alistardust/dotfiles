"""Tests for tuneshift pin command."""

import sys
from argparse import Namespace
from pathlib import Path

from tuneshift.commands.pin_cmd import handle_pin
from tuneshift.db import Database
from tuneshift.models import Track


def _setup_playlist(db: Database) -> int:
    """Create a playlist with some tracks for testing."""
    playlist_id = db.create_playlist("Test Playlist")
    tracks = [
        Track(title="Opener Song", artist="Artist A"),
        Track(title="Middle Song", artist="Artist B"),
        Track(title="Closer Song", artist="Artist C"),
        Track(title="Another Song", artist="Artist D"),
    ]
    for i, track in enumerate(tracks):
        tid = db.insert_track(track)
        db.add_track_to_playlist(playlist_id, tid, position=i)
    return playlist_id


class TestPinOpener:
    def test_pin_opener_succeeds(self, tmp_db: Path, capsys):
        db = Database(tmp_db)
        _setup_playlist(db)
        args = Namespace(playlist="Test Playlist", opener="Opener Song", closer=None,
                         adjacent=None, remove=None, list_pins=False, group=None)
        result = handle_pin(args, db)
        assert result == 0
        pins = db.get_pins(1)
        openers = [p for p in pins if p.pin_type == "opener"]
        assert len(openers) == 1
        captured = capsys.readouterr()
        assert "Pinned" in captured.out

    def test_pin_opener_replaces_existing(self, tmp_db: Path):
        db = Database(tmp_db)
        _setup_playlist(db)
        args1 = Namespace(playlist="Test Playlist", opener="Opener Song", closer=None,
                          adjacent=None, remove=None, list_pins=False, group=None)
        handle_pin(args1, db)

        args2 = Namespace(playlist="Test Playlist", opener="Middle Song", closer=None,
                          adjacent=None, remove=None, list_pins=False, group=None)
        handle_pin(args2, db)

        pins = db.get_pins(1)
        openers = [p for p in pins if p.pin_type == "opener"]
        assert len(openers) == 1


class TestPinCloser:
    def test_pin_closer_succeeds(self, tmp_db: Path):
        db = Database(tmp_db)
        _setup_playlist(db)
        args = Namespace(playlist="Test Playlist", opener=None, closer="Closer Song",
                         adjacent=None, remove=None, list_pins=False, group=None)
        result = handle_pin(args, db)
        assert result == 0
        pins = db.get_pins(1)
        closers = [p for p in pins if p.pin_type == "closer"]
        assert len(closers) == 1


class TestPinAdjacency:
    def test_create_adjacency_group(self, tmp_db: Path, capsys):
        db = Database(tmp_db)
        _setup_playlist(db)
        args = Namespace(playlist="Test Playlist", opener=None, closer=None,
                         adjacent=["Opener Song", "Middle Song"], remove=None,
                         list_pins=False, group="intro")
        result = handle_pin(args, db)
        assert result == 0
        pins = db.get_pins(1)
        anchors = [p for p in pins if p.pin_type == "anchor"]
        assert len(anchors) == 2
        assert all(p.group_id == "intro" for p in anchors)
        captured = capsys.readouterr()
        assert "adjacency" in captured.out.lower()


class TestPinRemove:
    def test_remove_pin(self, tmp_db: Path, capsys):
        db = Database(tmp_db)
        _setup_playlist(db)
        # Set a pin first
        args_set = Namespace(playlist="Test Playlist", opener="Opener Song", closer=None,
                             adjacent=None, remove=None, list_pins=False, group=None)
        handle_pin(args_set, db)
        assert len(db.get_pins(1)) == 1

        # Remove it
        args_rm = Namespace(playlist="Test Playlist", opener=None, closer=None,
                            adjacent=None, remove="Opener Song", list_pins=False, group=None)
        result = handle_pin(args_rm, db)
        assert result == 0
        assert len(db.get_pins(1)) == 0


class TestPinList:
    def test_list_pins_empty(self, tmp_db: Path, capsys):
        db = Database(tmp_db)
        _setup_playlist(db)
        args = Namespace(playlist="Test Playlist", opener=None, closer=None,
                         adjacent=None, remove=None, list_pins=True, group=None)
        result = handle_pin(args, db)
        assert result == 0
        captured = capsys.readouterr()
        assert "No pins" in captured.out

    def test_list_pins_shows_pins(self, tmp_db: Path, capsys):
        db = Database(tmp_db)
        _setup_playlist(db)
        # Add an opener pin
        args_set = Namespace(playlist="Test Playlist", opener="Opener Song", closer=None,
                             adjacent=None, remove=None, list_pins=False, group=None)
        handle_pin(args_set, db)

        args_list = Namespace(playlist="Test Playlist", opener=None, closer=None,
                              adjacent=None, remove=None, list_pins=True, group=None)
        result = handle_pin(args_list, db)
        assert result == 0
        captured = capsys.readouterr()
        assert "opener" in captured.out


class TestPinErrors:
    def test_playlist_not_found(self, tmp_db: Path, capsys):
        db = Database(tmp_db)
        args = Namespace(playlist="Nonexistent", opener="Something", closer=None,
                         adjacent=None, remove=None, list_pins=False, group=None)
        result = handle_pin(args, db)
        assert result == 1

    def test_track_not_found(self, tmp_db: Path, capsys):
        db = Database(tmp_db)
        _setup_playlist(db)
        args = Namespace(playlist="Test Playlist", opener="Nonexistent Track", closer=None,
                         adjacent=None, remove=None, list_pins=False, group=None)
        result = handle_pin(args, db)
        assert result == 1

    def test_no_action_specified(self, tmp_db: Path, capsys):
        db = Database(tmp_db)
        _setup_playlist(db)
        args = Namespace(playlist="Test Playlist", opener=None, closer=None,
                         adjacent=None, remove=None, list_pins=False, group=None)
        result = handle_pin(args, db)
        assert result == 1
