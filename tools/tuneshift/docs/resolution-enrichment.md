# Resolution & Enrichment

Getting a track from "a title and an artist" to "a fully-identified, metadata-rich,
platform-mapped entry" happens in two stages:

1. **Resolution**: establish *identity*, which real recording is this, and which
   platform release corresponds to it (ISRC, duration, album, MusicBrainz IDs,
   confidence tier).
2. **Enrichment**: *hydrate* everything else, native platform metadata (Dolby
   Atmos, quality, year, genres), audio features (BPM/key/energy/valence), and
   narrative classification.

The pipeline is **library-first**: adding a track enqueues resolution work rather
than blocking on the network. Code lives in `tuneshift/library/`,
`tuneshift/identity/`, and `tuneshift/enrichment/`.

## Library-first add/import (AC-D7)

`add` and `import-text` create the track, add it to the playlist, and **enqueue**
async resolution; they do not block on network calls
(`commands/add_cmd.py`, `commands/import_text_cmd.py`).

The queue is the `resolution_queue` table. Enqueueing:

- sets/keeps `state = 'pending'`,
- resets attempt counters only when reopening a previously *quarantined* row,
- leaves already-resolved or already-pending rows untouched.

```bash
tuneshift add "Road Trip" "Heroes" "David Bowie" --album "\"Heroes\""
tuneshift import-text "Road Trip" tracks.txt
tuneshift resolve "Road Trip" --all      # drain the queue for this playlist
tuneshift resolve --status               # coverage / quarantine stats
```

## The resumable resolution worker

`ResolutionWorker` (`library/worker.py`) drains `resolution_queue` by polling
`next_pending_resolution()`. It is resumable and idempotent: interrupting and
re-running picks up where it left off. `_resolve_one()` handles each track:

| Outcome | Behavior |
|---------|----------|
| Track missing | quarantine with reason `track_missing` |
| Resolver rate-limited | back to `pending` with backoff, increment `transient_attempts` |
| Generic exception | retry with backoff until `max_attempts`, then quarantine |
| No candidates found | immediate quarantine |
| Success | clear stale candidates, persist new ones, hydrate identity metadata, mark row `resolved`, run optional enrichment |

Attempt accounting uses two separate counters so transient rate-limits don't burn
the hard-failure budget: `attempts` (hard failures) and `transient_attempts`
(rate-limits).

`resolve_tracks()` supports scoped re-resolve: it re-enqueues targets and can
force `resolved` rows back to `pending` (used by `resolve --upgrade` / `--force`).

### `--upgrade` vs `--force`

Both re-open already-processed rows, but they target different sets:

| Flag | Targets | Use when |
|------|---------|----------|
| `--upgrade` | tracks **below** the `CONFIRMED` tier (`find_unresolved(below_tier="CONFIRMED")`) | you want to retry only the uncertain/probable matches after a matching improvement |
| `--force` | tracks that are **already resolved** (any tier, including VERIFIED) | you want to re-resolve everything from scratch |

Internally both set `force=True` on the re-enqueue (`commands/resolve.py`); the
difference is purely which tracks are selected. `--platform` defaults to `tidal`
when omitted (both in the CLI parser and `resolve_tracks()`); pass
`--platform spotify` or `--platform ytmusic` to target another platform.

## The resolver pipeline

`TrackResolver.resolve()` (`identity/resolver.py`) runs a staged pipeline:

1. **Cache check**: reuse a prior resolution if present.
2. **ISRC lookup**: a fast discovery path (still scored, never blindly trusted).
3. **MusicBrainz text search**: title/artist search for candidates.
4. **Discogs confirmation**: corroborate the top candidate.
5. **Final evaluation**: assign a confidence tier or record failure.

Thresholds: `CONFIRMED_THRESHOLD = 0.80`, `VERIFIED_THRESHOLD = 0.95`. On success,
`_finalize()` stores `mb_recording_id`, `mb_release_group_id`, `confidence_tier`,
`confidence_score`, and evidence.

`PlatformResolver` (`library/resolvers.py`) is the production resolver the worker
uses: it reuses `gather_candidates()`, preserves discovery order, attaches
`match_score`, and caps persisted candidates at `max_candidates`.

### Candidate persistence

Top-N discovery candidates are persisted to the `track_candidates` table with a
`discovery_rank`, so later selection scoring can reconsider them without re-querying
the platform. Re-resolve clears stale candidate rows first (`db.py`,
`library/worker.py`).

### Metadata hydration

`ResolutionWorker._hydrate_track()` maps candidate metadata onto the `tracks` row
via `hydrate_identity_metadata()`, populating `isrc`, `duration_seconds`, `album`,
and the derived confidence tier/score. This is what turns a bare
title/artist into a fully-identified track.

## Coverage & quarantine (AC-D1 / AC-D6)

- **Coverage** = `resolved / (resolved + quarantined)`. Pending tracks are excluded
  from the denominator (`db.py`).
- **Quarantine**: a track lands in quarantine (`tracks.quarantine_state`) with a
  machine-readable reason (`quarantine_reason` or `resolution_queue.last_error`)
  when it cannot be resolved. Quarantined tracks are **excluded from playlist
  selection** until they are resolved or approved; they never silently produce a
  wrong mapping.

```bash
tuneshift resolve --status     # coverage %, resolved/pending/quarantined counts
tuneshift triage               # surface tracks needing review
```

## The enrichment layer (FL2)

Enrichment runs out-of-band after resolution. `resolve` wires the worker with a
`PlatformResolver` and `make_enricher(...)` so resolved tracks are also enriched
(`commands/resolve.py`). `enrich_track()` (`library/enrichment.py`) does:

- **Artist enrichment**: canonical artist metadata.
- **Grounded classification**: narrative fields (see below).
- **Tidal catalog capture**: Atmos / release year / genres / quality.
- **Energy/valence estimation**: for the sequencer.

### Automatic Atmos/catalog capture

Tidal catalog capture fires automatically on **any** Tidal mapping write:
`capture_tidal_catalog()` is called from `map`, and `_capture_tidal_catalog()` runs
after resolve, so spatial-audio and quality data land in
`track_platform_metadata` without a manual enrich step.

### Grounded classification (no title-only guessing)

`classify_track_grounded()` (`enrichment/pipeline.py`) synthesizes Last.fm tags +
Genius lyrics + an LLM step. It deliberately does **not** classify from the title
alone. Audio features use a guarded ISRC fast-path
(`spotify_audio_features_via_isrc()`), falling back to `estimate_energy_valence()`.

> **LLM timeouts are non-fatal.** The classifier enforces a hard wall-clock timeout
> (default 30s, `TUNESHIFT_LLM_TIMEOUT` env var to override; `sequencer/classifier.py`).
> If the LLM step times out or errors, the track still resolves: ISRC, duration, and
> album are hydrated by the resolver, and only the energy/valence estimate is skipped.
> Re-run `enrich --classify` later to backfill the narrative/audio fields.


### Retry & rate limiting

`enrichment/retry.py` classifies errors as transient vs. permanent, applies
exponential backoff, honors rate-limit headers, and caps per-track time. The
Last.fm and Genius clients are themselves rate-limited and retry-aware.

## The `enrich` command

```bash
tuneshift enrich <playlist> --catalog       # fetch Tidal catalog metadata (Atmos, year, genres, quality)
tuneshift enrich --all                       # catalog-enrich every playlist (slow, retries)
tuneshift enrich <playlist> --classify       # LLM narrative classification
tuneshift enrich <playlist> --classify --model <name>
tuneshift enrich <playlist> --catalog --refresh   # re-fetch even if cached
tuneshift enrich --all --dry-run             # report how many fetches would run, no writes
```

| Flag | Effect |
|------|--------|
| `--catalog` / `--all` | Tidal platform-metadata enrichment |
| `--classify` | LLM classification of narrative fields |
| `--reclassify` | force re-classify all tracks |
| `--model` | override the classifier backend model |
| `--max-retries` | retry attempts per track on rate-limit/transient errors (default 3) |
| `--refresh` | re-fetch/recompute instead of fill-only-if-null |
| `--dry-run` | with `--all`, report fetch count without API calls |
