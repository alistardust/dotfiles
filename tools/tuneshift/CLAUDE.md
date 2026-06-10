# CLAUDE.md

Agent instructions for TuneShift.

## Commands

```bash
cd tools/tuneshift
.venv/bin/python -m pytest tests/ -x -q   # run tests
.venv/bin/python -m tuneshift --help       # CLI help
```

## Architecture

TuneShift is a canonical playlist manager. The local SQLite database is the
single source of truth; platform services (Tidal, Spotify, YTM) are distribution
targets that receive pushes from the canonical state.

### Critical Design Decisions

**The database is committed to git.** `tuneshift.db` is intentionally tracked in
version control. It IS the product: the curated playlist collection, track
metadata, platform mappings, and sequencer state. This is not an accident or
oversight. Do not suggest gitignoring it, moving it to an external store, or
treating it as generated/ephemeral data.

**Canonical-first, push-only model.** Changes flow one direction: local DB is
edited, then pushed to platforms. Platforms never overwrite local state. The
`ingest` command is the only path that reads from platforms into local state,
and it is a one-time import operation.

**Platform credentials live outside the repo.** Auth tokens are stored in
`~/.local/share/tuneshift/` with restricted permissions. They are never committed.
The separation between committed data (DB) and uncommitted secrets (tokens) is
load-bearing.

**Schema migrations are in-DB.** The `user_version` pragma tracks schema version.
Migrations run automatically on open. New migrations go in `db.py:_migrate_schema()`.

### Module Layout

| Module | Responsibility |
|--------|---------------|
| `db.py` | SQLite schema, migrations, all persistence |
| `cli.py` | Argument parsing, command dispatch |
| `commands/` | One file per CLI subcommand |
| `platforms/` | Platform API clients (tidal, spotify, ytmusic) |
| `sequencer/` | Track ordering algorithm (energy arcs, pinning) |
| `identity/` | Cross-platform track identity resolution |
| `matching.py` | Fuzzy title/artist matching and version scoring |
| `reconcile.py` | Find platform equivalents for canonical tracks |
| `models.py` | Shared dataclasses |

### Sequencer

The sequencer orders tracks by energy arc profiles (wave, narrative, descending).
It uses greedy nearest-neighbor construction, 2-opt local optimization, and
artist redistribution. Tracks can be pinned (opener, closer, adjacency groups)
which constrain the optimizer.

### Error Handling Contract

All commands that push to platforms propagate failures as non-zero exit codes.
Platform errors go to stderr. The CLI top-level handler catches `TuneShiftError`
for clean messages and unexpected exceptions with opt-in traceback
(`TUNESHIFT_DEBUG=1`).
