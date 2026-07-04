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
from tuneshift.matching.audit import ReasonCode
from tuneshift.models import PlatformMapping, PlaylistInfo, Track
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


@patch("tuneshift.sequencer.sequence_playlist")
@patch("tuneshift.commands.sync_cmd.reconcile_track")
@patch("tuneshift.commands.ingest_cmd._load_client")
def test_playlist_override_sync_does_not_clobber_global_default(
    mock_load, mock_reconcile, mock_sequence, tmp_db: Path
) -> None:
    """BLOCKER-1 regression: syncing a playlist with a per-playlist override lock
    must NOT rewrite the library-wide ``platform_tracks`` default.

    The override is playlist-scoped storage; every OTHER playlist resolves against
    the global default. Writing the override id back into the global row clobbers
    that default and silently changes unrelated playlists on their next sync.
    """
    db, pid, tid = _setup(tmp_db)
    # The global default that other playlists rely on.
    db.upsert_platform_mapping(PlatformMapping(
        track_id=tid, platform="tidal", platform_track_id="GLOBAL_ID",
        match_score=97, status="matched", user_approved=True,
    ))
    # THIS playlist pins a different release via a per-playlist override lock.
    db.set_playlist_track_mapping(
        pid, tid, "tidal", "OVERRIDE_ID", source="locked", user_approved=True
    )
    client = _mock_client()
    mock_load.return_value = client
    mock_sequence.return_value = [tid]
    mock_reconcile.return_value = ReconcileResult(
        platform_track_id="OVERRIDE_ID", score=98, confidence="high",
    )

    args = Namespace(playlist="Reorder Me", platform="tidal", all=False,
                     reconcile=False, auto=False)
    handle_sync(args, db)

    # Global default untouched; override remains playlist-scoped; override pushed.
    assert db.get_platform_mapping(tid, "tidal").platform_track_id == "GLOBAL_ID"
    assert db.get_playlist_track_mapping(pid, tid, "tidal")["platform_track_id"] == "OVERRIDE_ID"
    assert "OVERRIDE_ID" in _pushed_ids(client)


@patch("tuneshift.sequencer.sequence_playlist")
@patch("tuneshift.commands.sync_cmd.reconcile_track")
@patch("tuneshift.commands.ingest_cmd._load_client")
def test_verify_locks_holds_dead_lock_without_wiping_mapping(
    mock_load, mock_reconcile, mock_sequence, tmp_db: Path
) -> None:
    """BLOCKER-2a regression: ``sync --verify-locks`` on a lock whose platform id
    has gone dead (``LOCK_HELD``) must leave the lock mapping intact.

    The held result carries ``confidence='not_found'``; without an explicit
    interception it hits the not-found handler which overwrites the mapping to
    ``""`` / ``unavailable`` — destroying the lock and defeating AC-L3's routed
    self-heal. It must instead be held and omitted from the push, never wiped.
    """
    db, pid, tid = _setup(tmp_db)
    db.upsert_platform_mapping(PlatformMapping(
        track_id=tid, platform="tidal", platform_track_id="DEAD_LOCK",
        match_score=97, status="matched", user_approved=True,
    ))
    client = _mock_client()
    mock_load.return_value = client
    mock_sequence.return_value = [tid]
    mock_reconcile.return_value = ReconcileResult(
        platform_track_id="", score=0, confidence="not_found",
        reason_code=ReasonCode.LOCK_HELD,
    )

    args = Namespace(playlist="Reorder Me", platform="tidal", all=False,
                     reconcile=False, auto=False, verify_locks=True)
    handle_sync(args, db)

    # The lock is preserved, not wiped to unavailable, and not pushed.
    mapping = db.get_platform_mapping(tid, "tidal")
    assert mapping.platform_track_id == "DEAD_LOCK"
    assert mapping.status == "matched"
    assert _pushed_ids(client) == []


@patch("tuneshift.sequencer.sequence_playlist")
@patch("tuneshift.commands.sync_cmd.reconcile_track")
@patch("tuneshift.commands.ingest_cmd._load_client")
def test_ordinary_sync_does_not_wipe_held_unavailable_lock(
    mock_load, mock_reconcile, mock_sequence, tmp_db: Path
) -> None:
    """Regression: an ordinary (non --verify-locks) sync must not destroy a lock
    already held in the ``unavailable`` state that ``plan heal`` produced.

    A dead lock with no live equivalent is held as ``status='unavailable'``,
    ``user_approved=1`` with the locked id retained. On the next ordinary sync
    ``reconcile_track`` returns ``confidence='not_found'`` with reason_code
    ``LOCKED`` (not ``LOCK_HELD``). Without a lock-aware guard this hits the
    not-found handler and overwrites the id to ``""``, permanently destroying the
    lock and leaving nothing for a future heal. It must be held, never wiped.
    """
    db, pid, tid = _setup(tmp_db)
    # The held-unavailable global lock state produced by `plan heal`.
    db.upsert_platform_mapping(PlatformMapping(
        track_id=tid, platform="tidal", platform_track_id="HELD_LOCK",
        match_score=0, status="unavailable", user_approved=True,
    ))
    client = _mock_client()
    mock_load.return_value = client
    mock_sequence.return_value = [tid]
    # Ordinary sync of a held-unavailable lock: not_found + reason_code LOCKED.
    mock_reconcile.return_value = ReconcileResult(
        platform_track_id="", score=0, confidence="not_found",
        reason_code=ReasonCode.LOCKED,
    )

    args = Namespace(playlist="Reorder Me", platform="tidal", all=False,
                     reconcile=False, auto=False)
    handle_sync(args, db)

    # The locked id survives (not wiped to ""), so a future heal can still act.
    mapping = db.get_platform_mapping(tid, "tidal")
    assert mapping.platform_track_id == "HELD_LOCK"
    assert db.get_effective_lock(tid, "tidal", pid) is not None
    assert _pushed_ids(client) == []
