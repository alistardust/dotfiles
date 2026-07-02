"""Tests for the export command handler (no network)."""

import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace

from tuneshift.cli import main
from tuneshift.commands.export_cmd import handle_export
from tuneshift.db import Database
from tuneshift.models import Track


def _seed(db: Database, name: str = "Mix") -> int:
    playlist_id = db.create_playlist(name)
    track_id = db.insert_track(
        Track(
            title="Song One",
            artist="Artist A",
            album="Album X",
            isrc="US1234567890",
            duration_seconds=200,
            tempo=120,
            key="Am",
        )
    )
    db.set_playlist_tracks(playlist_id, [track_id])
    return playlist_id


def test_export_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    args = SimpleNamespace(playlist="Nope", format="text", output="-")
    assert handle_export(args, db) == 1
    assert "Playlist not found: Nope" in capsys.readouterr().err


def test_export_empty_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    db.create_playlist("Empty")
    args = SimpleNamespace(playlist="Empty", format="text", output="-")
    assert handle_export(args, db) == 1
    assert "is empty" in capsys.readouterr().err


def test_export_text_to_stdout(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    db.close()

    assert main(["--db", str(tmp_db), "export", "Mix", "-f", "text"]) == 0
    out = capsys.readouterr().out
    assert "# Mix" in out
    assert "Artist A - Song One [Album X]" in out


def test_export_csv_to_file(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "e.db"
    db = Database(db_path)
    _seed(db)
    db.close()

    out_file = tmp_path / "out.csv"
    assert main(
        ["--db", str(db_path), "export", "Mix", "-f", "csv", "-o", str(out_file)]
    ) == 0
    assert "Exported" in capsys.readouterr().out

    rows = list(csv.reader(io.StringIO(out_file.read_text())))
    assert rows[0] == ["Position", "Title", "Artist", "Album", "ISRC", "Duration_s", "BPM", "Key"]
    assert rows[1][:3] == ["1", "Song One", "Artist A"]


def test_export_json_to_stdout_is_valid(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    db.close()

    assert main(["--db", str(tmp_db), "export", "Mix", "-f", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "Mix"
    assert data["track_count"] == 1
    assert data["tracks"][0]["title"] == "Song One"


def test_export_soundiiz_and_tunemymusic_headers(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    db.close()

    assert main(["--db", str(tmp_db), "export", "Mix", "-f", "soundiiz"]) == 0
    soundiiz = capsys.readouterr().out
    assert soundiiz.splitlines()[0] == "Title,Artist,Album,ISRC"

    assert main(["--db", str(tmp_db), "export", "Mix", "-f", "tunemymusic"]) == 0
    tunemymusic = capsys.readouterr().out
    assert tunemymusic.splitlines()[0] == "Track Name,Artist Name,Album Name"


def test_export_unknown_format_falls_back_to_text(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    args = SimpleNamespace(playlist="Mix", format="bogus", output="-")
    assert handle_export(args, db) == 0
    assert "# Mix" in capsys.readouterr().out
