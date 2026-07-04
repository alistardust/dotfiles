"""Chunk 5 Task 5.5 — AC-L4: the resolved selection is authoritative everywhere.

The main sync loop resolves each track through ``reconcile_track`` (which honours
the per-playlist effective lock and the interactive approval decision) and pushes
only the approved ids. The auto-reorder re-push must mirror *that same resolved
set*, just re-ordered — it must never independently re-read the global
``platform_tracks`` table, which would resurrect a rejected substitute or a
release the per-playlist override lock replaced.

Regression guard for the bypass where the reorder re-push read global mappings
directly and so pushed content the resolver/user had excluded.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from tuneshift.commands.sync_cmd import handle_sync
from tuneshift.db import Database
from tuneshift.models import PlaylistInfo, Track
from tuneshift.reconcile import ReconcileResult


def _mock_client() -> MagicMock:
    client = MagicMock()
    client.platform_name = "tidal"
    client.load_session.return_value = True
    client.find_playlist_by_name.return_value = PlaylistInfo(
        platform_id="tidal-pl-1", name="Reorder Me", num_tracks=1,
    )
    client.replace_playlist_tracks.return_value = None
    return client


def _pushed_ids(client: MagicMock) -> list[str]:
    """Every id passed to replace_playlist_tracks across all calls."""
    ids: list[str] = []
    for call in client.replace_playlist_tracks.call_args_list:
        ids.extend(call.args[1])
    return ids


def _setup(tmp_db: Path) -> tuple[Database, int, int]:
    db = Database(tmp_db)
    pid = db.create_playlist("Reorder Me")
    tid = db.insert_track(Track(title="Song", artist="Artist"))
    db.add_track_to_playlist(pid, tid, 0)
    db.link_platform_playlist(pid, "tidal", "tidal-pl-1")
    db.set_auto_reorder(pid, True, "wave")
    return db, pid, tid


@patch("tuneshift.sequencer.sequence_playlist")
@patch("tuneshift.commands.sync_cmd.reconcile_track")
@patch("tuneshift.commands.ingest_cmd._load_client")
def test_reorder_repush_excludes_rejected_divergent(
    mock_load, mock_reconcile, mock_sequence, tmp_db: Path
) -> None:
    """A user-rejected divergent substitute is never resurrected by the reorder push."""
    db, pid, tid = _setup(tmp_db)
    client = _mock_client()
    mock_load.return_value = client
    mock_sequence.return_value = [tid]
    mock_reconcile.return_value = ReconcileResult(
        platform_track_id="DIVERGENT_ID", score=90, confidence="high",
        is_divergent=True, divergence_note="live version", from_cache=False,
    )

    args = Namespace(playlist="Reorder Me", platform="tidal", all=False,
                     reconcile=False, auto=False)
    # Reject the divergent substitute at the interactive prompt.
    with patch("builtins.input", return_value="n"):
        handle_sync(args, db)

    # The rejected substitute must not be pushed by ANY push (main or reorder).
    assert "DIVERGENT_ID" not in _pushed_ids(client)


@patch("tuneshift.sequencer.sequence_playlist")
@patch("tuneshift.commands.sync_cmd.reconcile_track")
@patch("tuneshift.commands.ingest_cmd._load_client")
def test_reorder_repush_pushes_approved_selection(
    mock_load, mock_reconcile, mock_sequence, tmp_db: Path
) -> None:
    """An approved match IS carried through to the reorder push (happy path guard)."""
    db, pid, tid = _setup(tmp_db)
    client = _mock_client()
    mock_load.return_value = client
    mock_sequence.return_value = [tid]
    mock_reconcile.return_value = ReconcileResult(
        platform_track_id="RESOLVED_ID", score=98, confidence="high",
    )

    args = Namespace(playlist="Reorder Me", platform="tidal", all=False,
                     reconcile=False, auto=False)
    handle_sync(args, db)

    # Pushed by the main sync AND re-pushed after the auto-reorder.
    assert _pushed_ids(client) == ["RESOLVED_ID", "RESOLVED_ID"]
