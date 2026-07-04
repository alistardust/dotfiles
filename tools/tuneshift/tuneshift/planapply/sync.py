"""ROUTED remote push for sync (§7.1 routing table, AC-P4 forward-only).

A ``sync`` pushes a playlist's reconciled ordered track list to a streaming
platform. Under the plan/apply architecture that push is not performed inline —
it is a ``remote_push`` change the apply engine executes through a
:data:`~tuneshift.planapply.apply.RemoteExecutor`, journaling it under a
``remote:`` table name. Remote pushes are forward-only: :func:`rollback_plan`
never un-pushes; it surfaces the prior remote state as a compensating plan,
which :func:`build_compensating_plan` turns back into an apply-able re-push.

This module is deliberately thin: plan construction reconciles read-only, the
executor is the only code that mutates a remote platform, and both are testable
with a fake client (no live platform SDK).
"""

from __future__ import annotations

import json

from tuneshift.db import Database
from tuneshift.planapply.apply import REMOTE_TABLE_PREFIX, RemoteExecutor, RollbackReport
from tuneshift.planapply.models import Plan, PlanChange, row_key_for
from tuneshift.planapply.plan import new_plan_id
from tuneshift.platforms.protocol import MusicPlatformClient
from tuneshift.reconcile import reconcile_track


def _playlist_meta(db: Database, playlist_id: int) -> tuple[str, str]:
    row = db.conn.execute(
        "SELECT name, description FROM playlists WHERE id = ?", (playlist_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"No playlist with id {playlist_id}")
    return row["name"], (row["description"] or "")


def _remote_ids(client: MusicPlatformClient, platform_playlist_id: str) -> list[str] | None:
    try:
        return [t.platform_id for t in client.get_playlist_tracks(platform_playlist_id)]
    except Exception:  # noqa: BLE001 - remote read is best-effort context only
        return None


def build_sync_plan(
    db: Database,
    playlist_id: int,
    client: MusicPlatformClient,
    *,
    platform: str = "tidal",
    force: bool = False,
) -> Plan:
    """Plan the forward-only remote push of a playlist's reconciled track list.

    Reconciliation is read-only: it computes the ordered platform ids that would
    be pushed. Tracks that don't confidently resolve are omitted from the push
    (matching today's "unavailable tracks aren't pushed" behavior) rather than
    silently dropped from the library. If the remote already holds exactly the
    proposed ids, the plan is a no-op (AC-P4 idempotency).
    """
    name, description = _playlist_meta(db, playlist_id)
    tracks = db.get_playlist_tracks(playlist_id)
    cached = db.get_platform_mappings_for_tracks([t.id for t in tracks], platform)

    push_ids: list[str] = []
    for track in tracks:
        result = reconcile_track(
            db,
            track.id,
            client,
            force=force,
            cached_mapping=cached.get(track.id),
            playlist_id=playlist_id,
        )
        if result.platform_track_id and result.confidence != "not_found":
            push_ids.append(result.platform_track_id)

    platform_playlist_id = db.get_platform_playlist_id(playlist_id, platform)
    prior_ids = (
        _remote_ids(client, platform_playlist_id) if platform_playlist_id else None
    )

    change = PlanChange(
        op="remote_push",
        table=f"{REMOTE_TABLE_PREFIX}{platform}",
        row_key=row_key_for(playlist_id=playlist_id, platform=platform),
        current={"platform_playlist_id": platform_playlist_id, "track_ids": prior_ids},
        proposed={
            "platform": platform,
            "local_playlist_id": playlist_id,
            "playlist_name": name,
            "description": description,
            "platform_playlist_id": platform_playlist_id,
            "track_ids": push_ids,
        },
        remote=True,
        reason=f"push {len(push_ids)} tracks to {platform}",
        provenance="sync",
        change_id=1,
    )
    # Idempotent no-op: the remote already holds exactly what we would push.
    if prior_ids is not None and prior_ids == push_ids:
        change.status = "skipped"

    return Plan(
        plan_id=new_plan_id(),
        kind="sync",
        scope=f"playlist:{playlist_id} platform:{platform}",
        changes=[change],
    )


def make_sync_executor(
    db: Database, client: MusicPlatformClient, *, platform: str = "tidal"
) -> RemoteExecutor:
    """Build the :data:`RemoteExecutor` that performs a sync push at apply time.

    Resolves (find-or-create + link) the platform playlist if needed, captures
    the prior remote track order for the compensating plan, then replaces the
    remote track list. Playlist creation is deferred to apply time so plan
    construction stays free of remote mutations.
    """

    def _execute(change: PlanChange) -> dict | None:
        proposed = change.proposed or {}
        platform_playlist_id = proposed.get("platform_playlist_id")
        local_playlist_id = proposed.get("local_playlist_id")

        if not platform_playlist_id:
            existing = client.find_playlist_by_name(proposed["playlist_name"])
            if existing is not None:
                platform_playlist_id = existing.platform_id
            else:
                created = client.create_playlist(
                    proposed["playlist_name"], proposed.get("description", "")
                )
                platform_playlist_id = created.platform_id
            if local_playlist_id is not None:
                db.link_platform_playlist(
                    local_playlist_id, platform, platform_playlist_id
                )

        prior_ids = _remote_ids(client, platform_playlist_id)
        client.replace_playlist_tracks(
            platform_playlist_id, list(proposed.get("track_ids", []))
        )
        return {"platform_playlist_id": platform_playlist_id, "track_ids": prior_ids}

    return _execute


def build_compensating_plan(
    report: RollbackReport, *, plan_id: str | None = None
) -> Plan:
    """Turn a rollback's forward-only remote entries into a re-push plan (AC-P4).

    Each remote push that a rollback could not un-push inline becomes a
    ``remote_push`` change that restores the prior remote track order. Applying
    this plan with :func:`make_sync_executor` completes the reversal.
    """
    changes: list[PlanChange] = []
    for change_id, entry in enumerate(report.compensating, start=1):
        prior = entry.prior_value or {}
        row = json.loads(entry.row_key)
        platform = entry.table_name[len(REMOTE_TABLE_PREFIX):]
        changes.append(
            PlanChange(
                op="remote_push",
                table=entry.table_name,
                row_key=entry.row_key,
                current=None,
                proposed={
                    "platform": platform,
                    "local_playlist_id": row.get("playlist_id"),
                    "playlist_name": prior.get("playlist_name", ""),
                    "description": "",
                    "platform_playlist_id": prior.get("platform_playlist_id"),
                    "track_ids": prior.get("track_ids") or [],
                },
                remote=True,
                reason=f"compensating re-push to {platform}",
                provenance="rollback-compensation",
                change_id=change_id,
            )
        )
    return Plan(
        plan_id=plan_id or new_plan_id(),
        kind="compensating",
        changes=changes,
    )
