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


def _build_db_with_fillable_gap(tmp_path: Path) -> Database:
    """DB whose narrative has a CLOSER section with no assignable track,
    plus a library track that matches that gap's fill spec."""
    db = _build_db(tmp_path)
    playlist = db.find_playlist_by_name("Narrative Mix")
    assert playlist is not None
    # A library track (not in the playlist) that matches the CLOSER gap:
    # intensity in (0.05, 0.35), stance "peaceful", keyword overlap "peaceful".
    candidate_id = db.add_track(Track(title="Quiet Coda", artist="C"))
    db.update_track_metadata(
        candidate_id,
        {"emotional_intensity": 0.2, "narrator_stance": "peaceful", "vibes": ["peaceful"]},
    )
    db.set_narrative(
        playlist.id,
        (
            "OPENING (1): Gentle vulnerable introduction.\n"
            "WRATH (2): Fury and defiance. Required: Rage Song.\n"
            "CLOSER (3): Calm peaceful still quiet ending."
        ),
    )
    return db


def test_handle_compose_fill_gaps_analyze_renders_candidates(tmp_path: Path, capsys) -> None:
    """--fill-gaps --analyze must not raise NameError (regression for the
    `gaps` vs `result.gaps` bug) and must render candidates for fillable gaps."""
    db = _build_db_with_fillable_gap(tmp_path)
    args = SimpleNamespace(
        playlist="Narrative Mix",
        analyze=True,
        reorder=False,
        fill_gaps=True,
        dry_run=False,
        apply=False,
    )

    result = handle_compose(args, db)

    assert result == 0
    out = capsys.readouterr().out
    assert "CLOSER" in out
    # candidate computed from result.gaps and rendered under the CLOSER gap
    assert "candidate: C - Quiet Coda" in out


def test_handle_compose_fill_gaps_without_analyze_warns_and_no_mutation(
    tmp_path: Path, capsys
) -> None:
    """--fill-gaps outside analyze mode warns (candidates are suggest-only)
    and never mutates the stored playlist order."""
    db = _build_db_with_fillable_gap(tmp_path)
    playlist = db.find_playlist_by_name("Narrative Mix")
    assert playlist is not None
    before = [t.id for t in db.get_playlist_tracks(playlist.id)]

    args = SimpleNamespace(
        playlist="Narrative Mix",
        analyze=False,
        reorder=False,
        fill_gaps=True,
        dry_run=False,
        apply=False,
    )

    result = handle_compose(args, db)

    assert result == 0
    err = capsys.readouterr().err
    assert "--analyze" in err
    after = [t.id for t in db.get_playlist_tracks(playlist.id)]
    assert after == before
