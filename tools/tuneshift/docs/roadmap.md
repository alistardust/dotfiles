# Roadmap

Known future work, deferred improvements, and intentional non-goals for TuneShift.
This is a living register; items here are not commitments, and anything that
changes user-visible behavior should be discussed before it is built.

## Planned / open enhancements

### Legacy preference cleanup
Remove the legacy keyword preference model (`version.prefer`, `version.avoid`,
`version.tiebreak_order`, `version.duration_tolerance_percent`, `version.min_lead`)
once any remaining usage is migrated to the typed `(criterion, strength, target)`
model. The typed model is already canonical; `prefs show`/`clear` still read the
legacy keys for backward compatibility. See [preferences.md](preferences.md).

### Client-side throttle for local operations (shipped)
Shipped as `resolve --throttle OPS_PER_SEC`: caps resolve to N operations/second
for CPU/memory-intensive local work (bulk `resolve --all`, batch re-resolves,
bulk enrichment), independent of upstream API rate limits (default 3.0). A config
key equivalent remains a possible future addition.

### Plan expiry / pruning
Plan JSON files under `.tuneshift/plans/` are never auto-pruned; applied and
rejected plans accumulate until deleted by hand. Proposed: auto-archive or delete
plans older than N days, or a `plan prune` verb. See [plan-apply.md](plan-apply.md).

### Richer coverage reporting
`resolve --status` reports overall coverage and resolved/pending/quarantined counts.
A richer report would help triage: per-playlist coverage breakdown and a histogram
of quarantine reasons. See [resolution-enrichment.md](resolution-enrichment.md).

### Enrichment backfill scheduling
The enrichment worker is resumable, but scheduling is manual: there is no cron-able
or automatic backfill that periodically picks up newly-resolved tracks and fills in
missing catalog/audio/narrative metadata. Proposed: a scheduled backfill entry point
that reuses the existing resumable worker.

### Regional core-text retitle bridging
When a region ships the same recording under a title whose **core text** differs
(not just a trailing subtitle), the base-title blend cannot bridge it. Today such
tracks are matched at low confidence and surfaced for review rather than
mismatched. The intended fix is an ISRC-based title bypass when a shared ISRC
exists across the regional releases. Not built; needs a design decision because it
changes matching behavior. Documented as a known limit in
[matching-known-limits.md](matching-known-limits.md) (section 7).

## Intentional non-goals

These are sometimes proposed but are deliberate design decisions **not** to build.

### Do not unify the four normalizers into one output
TuneShift has four normalization functions serving three distinct concerns
(comparison keys in `matching`, stored/indexed identity keys in `db`, external
search query strings in `identity`, and concept tokenization in `composer`). FL4
already refactored them to build on shared low-level primitives (`fold_accents`,
`strip_version_markers`, and friends), so the code is not duplicated. The non-goal is the
next step some propose: unifying them onto a **single normalization path** so they
all emit **identical output**. They must **not** produce identical output, because
their results mean different things and some are persisted and indexed. Collapsing
them would require a reindex migration and could merge rows the UNIQUE constraint
keeps distinct (for example accented vs unaccented titles). Each normalizer's
distinct output contract is pinned by drift-guard tests
(`tests/matching/test_normalizer_contracts.py`).

### Matching limits that stay surfaced, not auto-resolved
Classical/long-form disambiguation, acoustic fingerprinting, re-record vs original
selection, and multi-disc ordering are deliberately surfaced for review rather than
guessed. The guiding rule is that a "we cannot be sure" is always a visible review
item, never a silent wrong guess. Full rationale and observable behavior for each
is in [matching-known-limits.md](matching-known-limits.md).

## Already shipped (context for stale suggestions)

For reviewers working from older notes, the following are **done**, not pending:

- **Concurrent-DB safety.** `resolve` takes a PID single-flight lock
  (`.tuneshift/resolve.lock`) so concurrent resolve runs cannot corrupt the
  shared SQLite DB, and `import-json` restores a playlist from an
  `export --format json` snapshot (recovery for a clobbered playlist). Operational
  single-writer discipline remains the primary guard; these are the safety net.
- **Bounded network calls.** Every Tidal and MusicBrainz call has a wall-clock
  timeout (`TUNESHIFT_NETWORK_TIMEOUT`, default 45s); a stalled call is a
  transient resolve retry, not an indefinite hang or a wrong quarantine.
- **Resolution wiring (FL1).** The library-first queue, resumable worker, and
  `resolve` are wired end to end; adding a track enqueues async resolution.
- **Metadata hydration (FL2).** Resolution hydrates ISRC, duration, album, and
  confidence tier; Tidal catalog capture (Atmos/quality/year/genres) fires
  automatically on any Tidal mapping write.
- **Multi-target preferences (FL3).** A single axis can carry multiple targets at
  one scope (e.g. `content avoid karaoke` and `content avoid instrumental`
  together), enforced by the `playlist_track_prefs` unique index.
- **Cached candidate scoring.** Steady-state selection scores from the persisted
  `track_candidates` set (`acquire_candidates()`, AC-X3); a live platform gather
  runs only on a cold cache or an explicit refresh (`--live`/self-heal), so
  interactive matching makes no resolution API calls.
