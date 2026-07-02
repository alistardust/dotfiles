"""Tests for handle_batch dispatch (the batch command orchestrator).

Plan/backup directories are redirected to tmp paths so the real user plan
store is never touched, and input() is stubbed for confirm prompts.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import tuneshift.commands.batch_cmd as batch_cmd
from tuneshift.commands.batch_cmd import BatchPlan, PlanOperation, handle_batch
from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture(autouse=True)
def _isolate_plan_store(tmp_path, monkeypatch):
    """Redirect plan dir so tests never touch ~/.local/share."""
    monkeypatch.setattr(batch_cmd, "_PLAN_DIR", tmp_path / "plans")


def _batch_args(**over):
    base = dict(
        show_plan=False,
        discard=False,
        history=False,
        undo=False,
        id=None,
        apply=False,
        sweep_banned=False,
        plan=False,
        playlist=None,
        interactive=False,
        from_stdin=False,
        rm=None,
        add=None,
        plan_file=None,
        dedupe=False,
        cap=1,
        rm_artist=None,
        review_findings=False,
        split=None,
        filter=None,
        rebuild=False,
        count=50,
        fresh=False,
        structure=False,
        narrative_file=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _seed(db: Database, *, titles=("Alpha", "Beta"), artist="A") -> int:
    playlist_id = db.create_playlist("Mix")
    ids = [db.insert_track(Track(title=t, artist=artist)) for t in titles]
    db.set_playlist_tracks(playlist_id, ids)
    return playlist_id


# --- plan lifecycle ----------------------------------------------------

def test_show_plan_when_none_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_batch(_batch_args(show_plan=True), db) == 1
    assert "No plan exists" in capsys.readouterr().out


def test_show_plan_renders_saved_plan(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    pid = _seed(db)
    BatchPlan(playlist_name="Mix", playlist_id=pid, operations=[]).save()
    assert handle_batch(_batch_args(show_plan=True), db) == 0
    assert "Mix" in capsys.readouterr().out


def test_discard_with_plan(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    BatchPlan(playlist_name="Mix", playlist_id=1, operations=[]).save()
    assert handle_batch(_batch_args(discard=True), db) == 0
    assert "Plan discarded." in capsys.readouterr().out


def test_discard_without_plan(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_batch(_batch_args(discard=True), db) == 0
    assert "No plan to discard." in capsys.readouterr().out


def test_history_empty(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_batch(_batch_args(history=True), db) == 0
    assert "No batch history found." in capsys.readouterr().out


def test_undo_nothing_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_batch(_batch_args(undo=True), db) == 1
    assert "Nothing to undo." in capsys.readouterr().err


def test_apply_without_plan_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_batch(_batch_args(apply=True), db) == 1
    assert "No plan to apply" in capsys.readouterr().err


def test_apply_cancelled_by_user(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    pid = _seed(db)
    BatchPlan(playlist_name="Mix", playlist_id=pid, operations=[]).save()
    monkeypatch.setattr("builtins.input", lambda *a: "n")
    assert handle_batch(_batch_args(apply=True), db) == 0
    assert "Cancelled." in capsys.readouterr().out


def test_apply_then_history_then_undo_roundtrip(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    pid = _seed(db)
    tracks = db.get_playlist_tracks(pid)
    op = PlanOperation(
        action="rm",
        track_title=tracks[0].title,
        track_artist=tracks[0].artist,
        track_id=tracks[0].id,
        position=0,
        previous_position=0,
        reason="test removal",
    )
    BatchPlan(playlist_name="Mix", playlist_id=pid, operations=[op]).save()

    monkeypatch.setattr("builtins.input", lambda *a: "y")
    assert handle_batch(_batch_args(apply=True), db) == 0
    assert "1 removed" in capsys.readouterr().out
    assert [t.title for t in db.get_playlist_tracks(pid)] == ["Beta"]
    assert BatchPlan.load() is None  # plan discarded after apply

    # history now shows the applied plan
    assert handle_batch(_batch_args(history=True), db) == 0
    assert "1 removals" in capsys.readouterr().out

    # undo reverses it
    assert handle_batch(_batch_args(undo=True), db) == 0
    assert "Undone" in capsys.readouterr().out
    assert sorted(t.title for t in db.get_playlist_tracks(pid)) == ["Alpha", "Beta"]


# --- plan generation guards -------------------------------------------

def test_plan_generation_requires_playlist(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_batch(_batch_args(rm=["x"]), db) == 1
    assert "Playlist name required" in capsys.readouterr().err


def test_plan_generation_missing_playlist_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    assert handle_batch(_batch_args(playlist="Ghost", rm=["x"]), db) == 1
    assert "Playlist not found: Ghost" in capsys.readouterr().err


def test_interactive_and_stdin_mutually_exclusive(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    args = _batch_args(playlist="Mix", interactive=True, from_stdin=True)
    assert handle_batch(args, db) == 1
    assert "mutually exclusive" in capsys.readouterr().err


def test_split_without_filter_returns_1(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    args = _batch_args(playlist="Mix", split="New", filter=[])
    assert handle_batch(args, db) == 1
    assert "--split requires --filter" in capsys.readouterr().err


def test_structure_without_llm_or_file_returns_1(tmp_db: Path, capsys, monkeypatch) -> None:
    db = Database(tmp_db)
    _seed(db)

    class _NoLLM:
        available = False

    monkeypatch.setattr("tuneshift.sequencer.classifier.TrackClassifier", lambda *a, **k: _NoLLM())
    args = _batch_args(playlist="Mix", structure=True, narrative_file=None)
    assert handle_batch(args, db) == 1
    assert "requires an LLM backend" in capsys.readouterr().err


# --- plan generation results ------------------------------------------

def test_no_ops_reports_no_changes(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, titles=("Alpha", "Beta"), artist="A")  # unique titles, cap 1 per artist=2 -> keep+rm
    # dedupe with cap high enough that nothing is removed
    args = _batch_args(playlist="Mix", dedupe=True, cap=5)
    assert handle_batch(args, db) == 0
    assert "No changes needed." in capsys.readouterr().out


def test_rm_via_cli_flag_builds_and_saves_plan(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    args = _batch_args(playlist="Mix", rm=["Alpha - A"], plan=True)
    assert handle_batch(args, db) == 0
    out = capsys.readouterr().out
    assert "Plan saved" in out
    saved = BatchPlan.load()
    assert saved is not None
    assert any(op.action == "rm" and op.track_title == "Alpha" for op in saved.operations)


def test_rm_artist_builds_plan(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, titles=("Alpha", "Beta"), artist="A")
    args = _batch_args(playlist="Mix", rm_artist="A", plan=True)
    assert handle_batch(args, db) == 0
    saved = BatchPlan.load()
    assert saved is not None
    assert len(saved.operations) == 2


# --- sweep banned ------------------------------------------------------

def test_sweep_banned_none_found(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db)
    assert handle_batch(_batch_args(sweep_banned=True), db) == 0
    assert "No banned artists found." in capsys.readouterr().out


def test_sweep_banned_single_playlist_saves_plan(tmp_db: Path, capsys) -> None:
    db = Database(tmp_db)
    _seed(db, artist="Bad Guy")
    db.ban_artist("Bad Guy", reason="test")
    args = _batch_args(playlist="Mix", sweep_banned=True, plan=True)
    assert handle_batch(args, db) == 0
    out = capsys.readouterr().out
    assert "batch --apply" in out
    assert BatchPlan.load() is not None
