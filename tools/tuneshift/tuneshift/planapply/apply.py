"""Apply a resolved plan, journaling every write (ACs P1-P4).

Apply is the ONLY component that mutates local state on behalf of a plan. It
walks a plan's actionable changes (honoring the AC-P3 locked exclusion), and for
each one captures the row's prior state, performs the write, and records a
journal entry so :func:`rollback_plan` (Task 4.3) can reverse the whole batch.

**SQL safety.** A plan change names a target ``table`` and carries a ``proposed``
column mapping. To keep every write parameterized and free of injected
identifiers, apply does NOT trust those names blindly: each table is described by
a :class:`_TableSpec` allowlist, and only column names drawn from that spec are
ever interpolated into SQL. A change targeting an unknown table or column is a
hard error, never a silent or dynamic query.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from tuneshift.db import Database
from tuneshift.planapply.models import Plan, PlanChange


class ApplyError(Exception):
    """Raised when a plan change cannot be applied safely."""


@dataclass(frozen=True)
class _TableSpec:
    """Allowlist describing a table apply may write."""

    name: str
    pk: tuple[str, ...]
    columns: tuple[str, ...]

    @property
    def all_columns(self) -> tuple[str, ...]:
        return (*self.pk, *self.columns)


# Tables the plan/apply engine is permitted to mutate. Extend deliberately as
# new routed mutations are added (Tasks 4.4-4.7).
_TABLE_SPECS: dict[str, _TableSpec] = {
    "playlist_track_mappings": _TableSpec(
        name="playlist_track_mappings",
        pk=("playlist_id", "track_id", "platform"),
        columns=("platform_track_id", "source", "user_approved"),
    ),
    "playlist_track_prefs": _TableSpec(
        name="playlist_track_prefs",
        pk=("playlist_id", "track_id", "criterion"),
        columns=("strength", "target"),
    ),
}


@dataclass
class ApplyReport:
    """Outcome of an apply run."""

    plan_id: str
    applied: int = 0
    skipped: int = 0
    skipped_locked: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _spec_for(table: str) -> _TableSpec:
    spec = _TABLE_SPECS.get(table)
    if spec is None:
        raise ApplyError(f"Refusing to apply change to unknown table: {table!r}")
    return spec


def _validate_columns(spec: _TableSpec, row: dict[str, Any]) -> None:
    unknown = set(row) - set(spec.all_columns)
    if unknown:
        raise ApplyError(
            f"Change targets unknown column(s) {sorted(unknown)} on {spec.name!r}"
        )


def _read_row(db: Database, spec: _TableSpec, pk_values: dict[str, Any]) -> dict | None:
    where = " AND ".join(f"{col} = ?" for col in spec.pk)
    cols = ", ".join(spec.all_columns)
    row = db.conn.execute(
        f"SELECT {cols} FROM {spec.name} WHERE {where}",  # noqa: S608 - identifiers from allowlist
        tuple(pk_values[col] for col in spec.pk),
    ).fetchone()
    if row is None:
        return None
    return {col: row[col] for col in spec.all_columns}


def _write_row(db: Database, spec: _TableSpec, proposed: dict[str, Any]) -> None:
    _validate_columns(spec, proposed)
    cols = [c for c in spec.all_columns if c in proposed]
    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    updates = ", ".join(
        f"{c} = excluded.{c}" for c in cols if c not in spec.pk
    )
    pk_list = ", ".join(spec.pk)
    conflict = (
        f" ON CONFLICT({pk_list}) DO UPDATE SET {updates}"
        if updates
        else f" ON CONFLICT({pk_list}) DO NOTHING"
    )
    sql = (
        f"INSERT INTO {spec.name} ({col_list}) VALUES ({placeholders}){conflict}"  # noqa: S608
    )
    db.conn.execute(sql, tuple(proposed[c] for c in cols))


def _delete_row(db: Database, spec: _TableSpec, pk_values: dict[str, Any]) -> None:
    where = " AND ".join(f"{col} = ?" for col in spec.pk)
    db.conn.execute(
        f"DELETE FROM {spec.name} WHERE {where}",  # noqa: S608 - identifiers from allowlist
        tuple(pk_values[col] for col in spec.pk),
    )


def _apply_one(db: Database, plan_id: str, change: PlanChange) -> None:
    """Apply a single LOCAL change and journal it. Caller owns the transaction."""
    spec = _spec_for(change.table)
    pk_values = json.loads(change.row_key)
    prior = _read_row(db, spec, pk_values)

    if change.op in ("insert", "update"):
        if change.proposed is None:
            raise ApplyError(f"{change.op} change has no proposed state")
        _write_row(db, spec, change.proposed)
        new_value = change.proposed
    elif change.op == "delete":
        _delete_row(db, spec, pk_values)
        new_value = None
    else:  # remote_push handled by the sync route (Task 4.6), never here
        raise ApplyError(f"apply_plan does not handle op {change.op!r}")

    db.record_journal_entry(
        plan_id=plan_id,
        table_name=spec.name,
        row_key=change.row_key,
        op=change.op,
        prior_value=prior,
        new_value=new_value,
    )


def apply_plan(
    db: Database,
    plan: Plan,
    *,
    include_locked: bool = False,
) -> ApplyReport:
    """Apply a plan's resolved LOCAL changes, journaling each write (AC-P1/P3/P4).

    Locked changes (touching ``user_approved``/locked rows) are skipped unless
    ``include_locked`` is set. Rejected/skipped/already-applied changes are never
    re-applied, so re-applying a fully-applied plan is a no-op (AC-P4).
    """
    report = ApplyReport(plan_id=plan.plan_id)

    for change in plan.changes:
        if not change.is_actionable:
            report.skipped += 1
            continue
        if change.locked and not include_locked:
            report.skipped_locked += 1
            change.status = "skipped"
            continue
        try:
            with db.conn:
                _apply_one(db, plan.plan_id, change)
            change.status = "applied"
            report.applied += 1
        except Exception as exc:  # noqa: BLE001 - recorded in report, never swallowed
            change.status = "failed"
            report.failed += 1
            report.errors.append(f"change {change.change_id}: {exc}")

    return report
