from pathlib import Path
from types import SimpleNamespace

from tuneshift.commands.compose_cmd import handle_compose
from tuneshift.db import Database
from tuneshift.models import Track


def _build_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "compose.db")
    playlist_id = db.create_playlist("Narrative Mix")
    first_id = db.add_track(Track(title="Soft Start", artist="A"))
    second_id = db.add_track(Track(title="Rage Song", artist="B"))
    db.add_track_to_playlist(playlist_id, first_id, 0)
    db.add_track_to_playlist(playlist_id, second_id, 1)
    db.update_track_metadata(
        first_id,
        {"emotional_intensity": 0.2, "narrator_stance": "vulnerable", "vibes": ["gentle"]},
    )
    db.update_track_metadata(
        second_id,
        {"emotional_intensity": 0.9, "narrator_stance": "defiant", "vibes": ["fury"]},
    )
    return db


def test_handle_compose_playlist_not_found(tmp_path: Path, capsys) -> None:
    db = Database(tmp_path / "missing.db")
    args = SimpleNamespace(
        playlist="Missing",
        analyze=False,
        reorder=False,
        fill_gaps=False,
        dry_run=False,
        apply=False,
    )

    result = handle_compose(args, db)

    assert result == 1
    assert "Playlist not found" in capsys.readouterr().err


def test_handle_compose_requires_narrative(tmp_path: Path, capsys) -> None:
    db = _build_db(tmp_path)
    args = SimpleNamespace(
        playlist="Narrative Mix",
        analyze=False,
        reorder=False,
        fill_gaps=False,
        dry_run=False,
        apply=False,
    )

    result = handle_compose(args, db)

    assert result == 1
    assert "No narrative set" in capsys.readouterr().err


def test_handle_compose_analyze_mode(tmp_path: Path, capsys) -> None:
    db = _build_db(tmp_path)
    playlist = db.find_playlist_by_name("Narrative Mix")
    assert playlist is not None
    db.set_narrative(
        playlist.id,
        (
            "OPENING (1): Gentle vulnerable introduction.\n"
            "WRATH (2): Fury and defiance. Required: Rage Song."
        ),
    )
    args = SimpleNamespace(
        playlist="Narrative Mix",
        analyze=True,
        reorder=False,
        fill_gaps=False,
        dry_run=False,
        apply=False,
    )

    result = handle_compose(args, db)

    assert result == 0
    output = capsys.readouterr().out
    assert "Assignments:" in output
    assert "Gaps:" in output
    assert "WRATH" in output
