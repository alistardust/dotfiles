# Identity Locks

A **lock** pins a track to a specific platform release so re-syncs, re-matches, and
migrations never silently swap it. Locks are the durable "I have decided this is
the right version" signal: stronger than a [preference](preferences.md), which
only *steers* selection.

Locks live in `tuneshift/identity/` and the `lock` / `unlock` commands
(`commands/lock_cmd.py`). They are routed through [plan/apply](plan-apply.md) by
default.

## Two-level composite locks

Locks exist at two levels, mirroring the two mapping tables:

| Level | Stored in | Meaning |
|-------|-----------|---------|
| **Global default** | `platform_tracks` with `user_approved = 1` | the locked release for this track everywhere |
| **Per-playlist override** | `playlist_track_mappings` with `user_approved = 1` | overrides the global lock for one playlist |

An effective lock carries the `platform_track_id`, its `scope`, the `isrc`, and the
`fingerprint`, plus divergence/status metadata for the global lock.

```bash
# Global default lock (default scope):
tuneshift lock "Focus" "Heroes" --tidal 12345678

# Per-playlist override:
tuneshift lock "Live Set" "Heroes" --tidal 87654321 --scope playlist

# Lock by canonical track id (no playlist/title lookup):
tuneshift lock --track-id 4021 --tidal 12345678
```

## Precedence: the effective lock

`get_effective_lock(track_id, platform, playlist_id)` (`db.py`) resolves which lock
applies:

1. A per-playlist override wins **if** its `playlist_track_mappings` row is
   `user_approved = 1` and has a `platform_track_id`.
2. Otherwise it falls through to the global `platform_tracks` lock
   (`user_approved = 1`).
3. If neither exists, there is no lock.

> An *unapproved* per-playlist row does **not** shadow a global lock; only an
> approved override takes precedence.

Inspect effective locks with precedence:

```bash
tuneshift lock --list                 # all effective locks
tuneshift lock "Focus" --list         # scoped to one playlist
```

## Short-circuiting selection

When a lock is present, `select_version()` short-circuits to `_resolve_lock()`
before the normal filter/score phases (`matching/selection.py`). This is the
AC-S2 / AC-L1 path:

| Situation | Result |
|-----------|--------|
| A candidate matches the lock and is available | locked candidate wins outright, `lock_applied=True` |
| No candidate matches the lock | `needs_review=True`, `review_reason="locked_missing"` |
| Matched candidates all unavailable | `needs_review=True`, `review_reason="locked_unavailable"` |

Locks are honored during identity resolution, sync reorder re-push, and rematch.
A locked track is protected from re-match (AC-L2) and shown as `[LOCKED]`.

## Self-heal of dead locks

A lock is **dead** when its locked platform id no longer resolves on the platform.
`build_heal_plan()` (`planapply/heal.py`) checks `_locked_id_alive(...)` and only
proposes a change when the id is confirmed gone (if it's alive or undeterminable,
nothing is proposed).

| Dead lock case | Heal action |
|----------------|-------------|
| A same-recording equivalent is found | propose a rebind (`reason="lock_healed"`) |
| No equivalent, **global** lock | hold as unavailable (`status="unavailable"`) |
| No equivalent, **playlist override** | surface for review (`status="skipped"`, `reason="lock_held"`) |

Because heal is routed through plan/apply, it changes nothing until you apply it:

```bash
tuneshift plan heal <playlist>    # produce a heal plan
tuneshift plan show <plan-id>     # review
tuneshift plan apply <plan-id>    # rebind/hold
```

## Version-downgrade flagging

When a locked track no longer satisfies an active preference (e.g. a
`spatial=dolbyatmos prefer` is set but the locked release is stereo-only), reconcile
audits flag it rather than silently overriding the lock:

- `ReasonCode.LOCK_HELD` marks a locked recording that is gone/unsatisfying and
  **held** rather than swapped (`matching/audit.py`).
- The review module treats `LOCK_HELD` as a hard-fail reason that requires review
  (`matching/review.py`), so it surfaces in `triage` and re-doctor plans (AC-L5).

## Releasing a lock

```bash
tuneshift unlock "Focus" "Heroes" --tidal            # release Tidal lock (writes a plan)
tuneshift unlock "Focus" "Heroes" --tidal --apply    # release immediately
tuneshift unlock --track-id 4021 --tidal
```

Like `lock`, `unlock` defaults to writing a reviewable plan; add `--apply` to apply
at once, or `--interactive` to step through the change.
