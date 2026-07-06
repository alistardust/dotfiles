# Plan / Apply

Every mutation that changes platform state or durable mappings in TuneShift goes
through a **plan** first. A plan is a reviewable, editable, rollback-able set of
proposed changes that alters *nothing* until you apply it. Applies are **journaled**
so any plan can be rolled back in one step.

This is the safety backbone of the tool: sync, rematch, migrate, self-heal,
lock/unlock, and map/unmap all route through it. The system lives in
`tuneshift/planapply/` and the `plan` command (`commands/plan_cmd.py`).

## Data model

| Type | Fields | Meaning |
|------|--------|---------|
| `Plan` | `plan_id`, `kind`, `scope`, `changes`, `version`, `created_at` | the proposed changes from one mutating command |
| `PlanChange` | `op`, `table`, `row_key`, `current`, `proposed`, `reason`, `provenance`, `classification`, `locked`, `remote`, `change_id`, `status` | one proposed row-level change |
| `JournalEntry` | `id`, `plan_id`, `table_name`, `row_key`, `op`, `prior_value`, `new_value`, `applied_at` | one recorded, reversible applied change |

(`planapply/models.py`)

- **Ops:** `insert`, `update`, `delete`, `remote_push`.
- **Statuses:** `pending`, `applied`, `skipped`, `rejected`, `failed`.
- `row_key` is stable JSON derived from the target primary key: it is the join key
  between a `PlanChange` and its `JournalEntry`.

### Persistence

- **Plans** are stored as JSON files under `.tuneshift/plans/<plan_id>.json`.
  The `.tuneshift/` directory lives **beside the database file**, not at the repo
  root or cwd: `plans_dir()` resolves to `db_path.parent / ".tuneshift" / "plans"`
  (`planapply/plan.py`). This means a `--db` pointed at a different database keeps
  its own, separate set of plans; the two never share a plan store.
- **The apply journal** is the `apply_journal` DB table: `plan_id`, `table_name`,
  `row_key`, `op`, `prior_value`, `new_value`, `applied_at` (`db.py`).
- **Plan lifecycle.** Plan files are not auto-pruned; applied and rejected plans
  accumulate in `.tuneshift/plans/` until deleted by hand. Automatic expiry/pruning
  is a known gap (see [roadmap](roadmap.md)).

## The apply engine

`apply_plan()` (`planapply/apply.py`) is the **only** path that mutates local state
for a plan. It:

1. Iterates the actionable changes (skipping `rejected` / `applied` / `skipped`).
2. Skips `locked` rows unless `include_locked` is set.
3. Performs each write against an **allowlist** of writable tables
   (`playlist_track_mappings`, `platform_tracks`, `platform_playlists`, `tracks`),
   validating columns before issuing SQL.
4. Records a `JournalEntry` for every successful write.

**Remote pushes** are a special `remote_push` op executed through a
`RemoteExecutor`. They are journaled with `remote:`-prefixed table names so that
rollback does not silently un-push a platform change.

## Rollback

`rollback` reads journal entries **newest-first** and reverses them
(`planapply/apply.py`):

- Journal replay is symmetric: if `prior_value` is `None`, rollback **deletes** the
  row; otherwise it **restores** the prior row state.
- Remote pushes are not undone inline: they are collected into a *compensating
  plan* you can review and apply.
- If no remote entries remain, the journal is cleared.

## The `plan` verbs

```bash
tuneshift plan sync <playlist> <platform>   # build_sync_plan -> one remote_push change
tuneshift plan rematch <playlist>           # build_rematch_plan -> playlist_track_mappings changes
tuneshift plan migrate                      # build_migration_plan -> platform_tracks changes + summary
tuneshift plan heal <playlist>              # build_heal_plan -> locked-row self-heal changes
tuneshift plan list                         # list saved plans
tuneshift plan show <plan-id>               # inspect a plan
tuneshift plan reject <plan-id> <change-id> # mark one change rejected (apply then skips it)
tuneshift plan apply <plan-id>              # apply the plan (journaled)
tuneshift plan rollback <plan-id>           # reverse an applied plan
```

> **What `migrate` means here.** `plan migrate` is *not* a schema migration. It
> re-resolves existing global `platform_tracks` mappings against the engine: it
> re-reconciles non-approved rows read-only and proposes a change only where the
> engine confidently finds a better mapping (an `improved` change). A same-id
> result is `unchanged`; a low-confidence one is left as-is and flagged for human
> judgment. User-approved (locked) rows are bypassed, never rewritten. Use it to
> bulk-upgrade stale or provisional platform mappings after matching improvements.

## Routing: what defaults to a plan

The default for mutating commands is **write a plan, change nothing**: you opt
into mutation explicitly.

| Command | Default | Mutate now |
|---------|---------|------------|
| `sync` | writes a plan, pushes nothing (AC-P1) | `--apply` (`--interactive` to step through) |
| `plan rematch` / `plan migrate` / `plan heal` | write a plan file | `plan apply <id>` |
| `lock` / `unlock` | write a plan | `--apply` (or `--interactive`) |
| `map` / `unmap` | immediate manual path | *(routed lock behavior is via `lock`/`unlock`)* |
| per-playlist rematch | routed through `plan rematch` + `apply_plan()` | (n/a) |

## Integrity rules

- **Forward-only remote pushes.** Remote changes are journaled so rollback produces
  a compensating plan rather than silently reversing a push.
- **Locks are respected.** Locked rows are skipped on apply unless explicitly
  included.
- **No double-apply.** Changes marked `rejected`, `applied`, or `skipped` are never
  re-applied.
- **Single-change rejection.** `plan reject` marks exactly one `change_id` as
  `rejected` in the plan file; the rest of the plan still applies.
