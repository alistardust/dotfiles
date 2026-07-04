"""Plan builders for the ROUTED map/unmap (lock) and enrichment-overwrite paths.

Per the §7.1 mutation-routing table, these mutations never write inline; they
produce a reviewable, journaled :class:`~tuneshift.planapply.models.Plan` that
the apply engine executes (and rollback reverses):

- ``map`` / ``unmap`` — create or release a per-playlist identity lock on
  ``playlist_track_mappings`` (spec §8, AC-L1). Overwriting or releasing an
  already-``user_approved`` mapping is a locked change (AC-P3): it is excluded
  from apply unless the caller explicitly opts in.
- enrichment overwrite — replace matcher-read fields on ``tracks`` with freshly
  enriched values (routing-table row "Enrichment metadata overwrite"). Only the
  fields the matcher actually reads are writable, and a no-op enrichment (values
  already current) yields an empty plan (AC-P4 idempotency).

The CLI verbs that call these builders are Task 4.8.
"""

from __future__ import annotations

from tuneshift.db import Database
from tuneshift.planapply.apply import _spec_for
from tuneshift.planapply.models import Plan, PlanChange, row_key_for
from tuneshift.planapply.plan import new_plan_id


def build_lock_plan(
    db: Database,
    playlist_id: int,
    track_id: int,
    platform: str,
    platform_track_id: str,
) -> Plan:
    """Plan a per-playlist identity lock to ``platform_track_id`` (map/AC-L1)."""
    current = db.get_playlist_track_mapping(playlist_id, track_id, platform)
    row_key = row_key_for(
        playlist_id=playlist_id, track_id=track_id, platform=platform
    )
    proposed = {
        "playlist_id": playlist_id,
        "track_id": track_id,
        "platform": platform,
        "platform_track_id": platform_track_id,
        "source": "locked",
        "user_approved": 1,
    }
    op = "update" if current is not None else "insert"
    # Overwriting an already-approved mapping touches a locked row (AC-P3).
    locked = bool(current and current["user_approved"])
    change = PlanChange(
        op=op,
        table="playlist_track_mappings",
        row_key=row_key,
        current=_mapping_state(current),
        proposed=proposed,
        reason=f"lock {platform} mapping to {platform_track_id}",
        provenance="user:map",
        locked=locked,
    )
    return _single_change_plan("lock", f"playlist:{playlist_id} track:{track_id}", change)


def build_unlock_plan(
    db: Database, playlist_id: int, track_id: int, platform: str
) -> Plan:
    """Plan the release of a per-playlist identity lock (unmap/AC-L1)."""
    current = db.get_playlist_track_mapping(playlist_id, track_id, platform)
    if current is None:
        # Nothing to release -> empty (no-op) plan.
        return Plan(plan_id=new_plan_id(), kind="unlock")
    row_key = row_key_for(
        playlist_id=playlist_id, track_id=track_id, platform=platform
    )
    change = PlanChange(
        op="delete",
        table="playlist_track_mappings",
        row_key=row_key,
        current=_mapping_state(current),
        proposed=None,
        reason=f"release {platform} lock",
        provenance="user:unmap",
        locked=bool(current["user_approved"]),
    )
    return _single_change_plan(
        "unlock", f"playlist:{playlist_id} track:{track_id}", change
    )


def build_enrich_plan(db: Database, track_id: int, fields: dict[str, object]) -> Plan:
    """Plan an enrichment overwrite of matcher-read ``tracks`` fields.

    Only fields whose new value differs from the stored value are emitted, so a
    re-run against already-enriched data produces an empty (no-op) plan. Fields
    outside the matcher-read allowlist are rejected — enrichment must not touch
    identity columns like ``title``/``artist``.
    """
    spec = _spec_for("tracks")
    writable = set(spec.columns)
    unknown = set(fields) - writable
    if unknown:
        raise ValueError(
            f"Enrichment may only overwrite matcher-read fields; got {sorted(unknown)}"
        )

    cols = ", ".join(spec.columns)
    row = db.conn.execute(
        f"SELECT {cols} FROM tracks WHERE id = ?",  # noqa: S608 - identifiers from allowlist
        (track_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No track with id {track_id}")

    changed = {k: v for k, v in fields.items() if row[k] != v}
    if not changed:
        return Plan(plan_id=new_plan_id(), kind="enrich")

    current_state = {k: row[k] for k in changed}
    proposed = {"id": track_id, **changed}
    change = PlanChange(
        op="update",
        table="tracks",
        row_key=row_key_for(id=track_id),
        current=current_state,
        proposed=proposed,
        reason=f"enrich {sorted(changed)}",
        provenance="enrichment",
    )
    return _single_change_plan("enrich", f"track:{track_id}", change)


def _mapping_state(mapping: dict | None) -> dict | None:
    if mapping is None:
        return None
    return {
        "playlist_id": mapping["playlist_id"],
        "track_id": mapping["track_id"],
        "platform": mapping["platform"],
        "platform_track_id": mapping["platform_track_id"],
        "source": mapping["source"],
        "user_approved": 1 if mapping["user_approved"] else 0,
    }


def _single_change_plan(kind: str, scope: str, change: PlanChange) -> Plan:
    change.change_id = 1
    return Plan(plan_id=new_plan_id(), kind=kind, scope=scope, changes=[change])
