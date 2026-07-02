"""Tests for the narrative command handler (no network)."""

from pathlib import Path
from types import SimpleNamespace

from tuneshift.cli import main
from tuneshift.commands.narrative_cmd import handle_narrative
from tuneshift.db import Database


def _make_playlist(db: Database, name: str = "Mix") -> int:
    return db.create_playlist(name)


def test_narrative_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    args = SimpleNamespace(playlist="Nope", clear=False, file=None, text=None)
    assert handle_narrative(args, db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_narrative_set_from_text_persists(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _make_playlist(db)
    db.close()

    assert main(["--db", str(tmp_db), "narrative", "Mix", "A journey."]) == 0
    assert "Set narrative" in capsys.readouterr().out

    verify = Database(tmp_db)
    playlist = verify.find_playlist_by_name("Mix")
    assert verify.get_narrative(playlist.id) == "A journey."
    verify.close()


def test_narrative_show_current(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    pid = _make_playlist(db)
    db.set_narrative(pid, "The arc")
    db.close()

    assert main(["--db", str(tmp_db), "narrative", "Mix"]) == 0
    out = capsys.readouterr().out
    assert "The arc" in out


def test_narrative_show_when_none_prints_hint(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _make_playlist(db)
    db.close()

    assert main(["--db", str(tmp_db), "narrative", "Mix"]) == 0
    assert "No narrative set" in capsys.readouterr().out


def test_narrative_clear_removes(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    pid = _make_playlist(db)
    db.set_narrative(pid, "gone soon")
    db.close()

    assert main(["--db", str(tmp_db), "narrative", "Mix", "--clear"]) == 0
    assert "Cleared narrative" in capsys.readouterr().out

    verify = Database(tmp_db)
    assert verify.get_narrative(pid) is None
    verify.close()


def test_narrative_from_file_persists(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "n.db"
    db = Database(db_path)
    _make_playlist(db)
    db.close()

    narrative_file = tmp_path / "arc.txt"
    narrative_file.write_text("From a file.\n")

    assert main(
        ["--db", str(db_path), "narrative", "Mix", "-f", str(narrative_file)]
    ) == 0
    assert "from" in capsys.readouterr().out

    verify = Database(db_path)
    playlist = verify.find_playlist_by_name("Mix")
    assert verify.get_narrative(playlist.id) == "From a file."
    verify.close()


def test_narrative_from_missing_file_returns_1(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "n.db"
    db = Database(db_path)
    _make_playlist(db)
    db.close()

    missing = tmp_path / "absent.txt"
    assert main(
        ["--db", str(db_path), "narrative", "Mix", "-f", str(missing)]
    ) == 1
    assert "File not found" in capsys.readouterr().err
