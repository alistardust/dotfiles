"""Tests for the folders/tag/untag/collections command handlers.

DB-backed handlers are exercised directly; Tidal-network subactions are
covered only through their not-logged-in guard (client mocked to None) so
no network calls occur.
"""

from pathlib import Path
from types import SimpleNamespace

import tuneshift.commands.folders_cmd as folders_cmd
from tuneshift.commands.folders_cmd import (
    handle_collections,
    handle_folders,
    handle_tag,
    handle_untag,
)
from tuneshift.db import Database


def _playlist(db: Database, name: str = "Mix") -> int:
    return db.create_playlist(name)


# --- tag ---------------------------------------------------------------

def test_tag_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_tag(SimpleNamespace(playlist="Nope", collection="C"), db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_tag_success_persists(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _playlist(db)
    assert handle_tag(SimpleNamespace(playlist="Mix", collection="Rock"), db) == 0
    assert 'Tagged "Mix" with "Rock"' in capsys.readouterr().out
    assert [p.name for p in db.get_collection_playlists("Rock")] == ["Mix"]


# --- untag -------------------------------------------------------------

def test_untag_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_untag(SimpleNamespace(playlist="Nope", collection="C"), db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_untag_success(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    pid = _playlist(db)
    db.tag_playlist(pid, "Rock")
    assert handle_untag(SimpleNamespace(playlist="Mix", collection="Rock"), db) == 0
    assert 'Removed "Rock" from "Mix"' in capsys.readouterr().out


def test_untag_not_tagged_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _playlist(db)
    assert handle_untag(SimpleNamespace(playlist="Mix", collection="Rock"), db) == 1
    assert "is not tagged" in capsys.readouterr().err


# --- collections -------------------------------------------------------

def _collections_args(**kwargs):
    base = dict(create_name=None, delete_name=None, collection=None)
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_collections_create(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_collections(_collections_args(create_name="Rock"), db) == 0
    assert 'Created collection "Rock"' in capsys.readouterr().out


def test_collections_delete_found(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    db.create_collection("Rock")
    assert handle_collections(_collections_args(delete_name="Rock"), db) == 0
    assert 'Deleted collection "Rock"' in capsys.readouterr().out


def test_collections_delete_missing_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_collections(_collections_args(delete_name="Ghost"), db) == 1
    assert "Collection not found" in capsys.readouterr().err


def test_collections_show_populated(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    pid = _playlist(db)
    db.tag_playlist(pid, "Rock")
    assert handle_collections(_collections_args(collection="Rock"), db) == 0
    out = capsys.readouterr().out
    assert 'Collection "Rock" (1 playlists)' in out
    assert "- Mix" in out


def test_collections_show_empty(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_collections(_collections_args(collection="Empty"), db) == 0
    assert "No playlists" in capsys.readouterr().out


def test_collections_list_none(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_collections(_collections_args(), db) == 0
    assert "No collections." in capsys.readouterr().out


def test_collections_list_with_counts(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    pid = _playlist(db)
    db.tag_playlist(pid, "Rock")
    assert handle_collections(_collections_args(), db) == 0
    out = capsys.readouterr().out
    assert "Collections:" in out
    assert "Rock (1 playlists)" in out


# --- folders dispatch --------------------------------------------------

def test_folders_unknown_action_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_folders(SimpleNamespace(action=None), db) == 1
    assert "Usage: tuneshift folders" in capsys.readouterr().err


def test_folders_move_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    args = SimpleNamespace(action="move", playlist="Nope", to="Rock")
    assert handle_folders(args, db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_folders_move_missing_folder_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _playlist(db)
    args = SimpleNamespace(action="move", playlist="Mix", to="Ghost")
    assert handle_folders(args, db) == 1
    assert "Folder not found in cache" in capsys.readouterr().err


def test_folders_move_success(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _playlist(db)
    db.cache_tidal_folder("trn:folder:abc", "Rock")
    args = SimpleNamespace(action="move", playlist="Mix", to="Rock")
    assert handle_folders(args, db) == 0
    assert 'Assigned "Mix" to folder "Rock"' in capsys.readouterr().out


def test_folders_unassign_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    args = SimpleNamespace(action="unassign", playlist="Nope")
    assert handle_folders(args, db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_folders_unassign_success(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _playlist(db)
    args = SimpleNamespace(action="unassign", playlist="Mix")
    assert handle_folders(args, db) == 0
    assert 'Unassigned "Mix"' in capsys.readouterr().out


def test_folders_status(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    pid = _playlist(db, "Assigned")
    _playlist(db, "Loose")
    db.cache_tidal_folder("trn:folder:abc", "Rock")
    db.set_playlist_tidal_folder(pid, "trn:folder:abc")
    assert handle_folders(SimpleNamespace(action="status"), db) == 0
    out = capsys.readouterr().out
    assert "[Rock]" in out
    assert "(root)" in out
    assert "- Loose" in out


def test_folders_list_not_logged_in_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(folders_cmd, "_get_tidal_client", lambda: None)
    assert handle_folders(SimpleNamespace(action="list"), db) == 1


def test_folders_create_not_logged_in_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    monkeypatch.setattr(folders_cmd, "_get_tidal_client", lambda: None)
    assert handle_folders(SimpleNamespace(action="create", name="Rock"), db) == 1
