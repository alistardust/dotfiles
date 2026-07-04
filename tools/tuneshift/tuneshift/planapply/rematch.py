"""Re-match plan builder (AC-P1, routing table row "Re-doctor / re-match").

A per-playlist re-match is ROUTED: it never mutates a playlist mapping inline.
Instead it runs the selection engine for every track on the playlist (via
``reconcile_track``, which already honours per-playlist preferences and locks)
and emits ``playlist_track_mappings`` ``current -> proposed`` changes into a
:class:`~tuneshift.planapply.models.Plan`. The plan is then reviewed and applied
through the shared apply engine, so re-matching gets journaling, rollback, and
the AC-P3 locked-row exclusion for free.
"""

from __future__ import annotations

from tuneshift.db import Database
from tuneshift.planapply.models import Plan, PlanChange, row_key_for
from tuneshift.planapply.plan import assign_change_ids, new_plan_id
from tuneshift.reconcile import reconcile_track

# Confidence levels a re-match will actually propose applying. Anything else is
# surfaced for human judgement rather than written.
_CONFIDENT = frozenset({"high"})


def build_rematch_plan(
    db: Database,
    playlist_id: int,
    client: object,
    *,
    platform: str = "tidal",
    force: bool = False,
) -> Plan:
    """Build (but do not apply) a re-match plan for one playlist.

    For each track: run the selection engine, compare the proposed release to the
    current per-playlist mapping (falling back to the global mapping as the
    baseline), and emit a change. Confident improvements are actionable; matches
    equal to the current release are ``unchanged`` no-ops; ambiguous/not-found
    results are ``needs-human-judgment`` and left for triage.
    """
    plan = Plan(
        plan_id=new_plan_id(),
        kind="rematch",
        scope=_playlist_scope(db, playlist_id),
    )

    for track in db.get_playlist_tracks(playlist_id):
        change = _change_for_track(
            db, playlist_id, track.id, client, platform, force=force
        )
        if change is not None:
            plan.changes.append(change)

    assign_change_ids(plan)
    return plan


def _playlist_scope(db: Database, playlist_id: int) -> str:
    row = db.conn.execute(
        "SELECT name FROM playlists WHERE id = ?", (playlist_id,)
    ).fetchone()
    return row["name"] if row is not None else str(playlist_id)


def _change_for_track(
    db: Database,
    playlist_id: int,
    track_id: int,
    client: object,
    platform: str,
    *,
    force: bool,
) -> PlanChange | None:
    playlist_mapping = db.get_playlist_track_mapping(playlist_id, track_id, platform)
    global_mapping = db.get_platform_mapping(track_id, platform)

    current_id = ""
    if playlist_mapping is not None:
        current_id = playlist_mapping["platform_track_id"]
    elif global_mapping is not None:
        current_id = global_mapping.platform_track_id

    # A user_approved row at either scope is a lock (AC-P3). The playlist-scoped
    # approval takes precedence, then the global default.
    locked = bool(
        (playlist_mapping and playlist_mapping["user_approved"])
        or (global_mapping and global_mapping.user_approved)
    )

    result = reconcile_track(
        db, track_id, client, force=force, playlist_id=playlist_id
    )

    op = "update" if playlist_mapping is not None else "insert"
    row_key = row_key_for(
        playlist_id=playlist_id, track_id=track_id, platform=platform
    )
    current_state = (
        {"platform_track_id": current_id} if current_id else None
    )

    # Not confidently matched -> never write; surface for human judgement.
    if result.confidence not in _CONFIDENT or not result.platform_track_id:
        return PlanChange(
            op=op,
            table="playlist_track_mappings",
            row_key=row_key,
            current=current_state,
            proposed=None,
            reason=f"no confident match ({result.confidence})",
            provenance="reconcile_track",
            classification="needs-human-judgment",
            locked=locked,
            status="skipped",
        )

    proposed_id = result.platform_track_id
    if proposed_id == current_id:
        return PlanChange(
            op=op,
            table="playlist_track_mappings",
            row_key=row_key,
            current=current_state,
            proposed={
                "playlist_id": playlist_id,
                "track_id": track_id,
                "platform": platform,
                "platform_track_id": proposed_id,
                "source": result.match_type or "matched",
                "user_approved": 0,
            },
            reason="already matched to the proposed release",
            provenance="reconcile_track",
            classification="unchanged",
            locked=locked,
            status="skipped",
        )

    return PlanChange(
        op=op,
        table="playlist_track_mappings",
        row_key=row_key,
        current=current_state,
        proposed={
            "playlist_id": playlist_id,
            "track_id": track_id,
            "platform": platform,
            "platform_track_id": proposed_id,
            "source": result.match_type or "matched",
            "user_approved": 0,
        },
        reason=_improve_reason(current_id, result),
        provenance="reconcile_track",
        classification="improved",
        locked=locked,
    )


def _improve_reason(current_id: str, result) -> str:
    if not current_id:
        return f"first confident match -> {result.platform_track_id}"
    return (
        f"re-matched {current_id} -> {result.platform_track_id} "
        f"(score {result.score})"
    )
