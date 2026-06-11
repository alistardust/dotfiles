# CLAUDE.md

Agent instructions for TuneShift.

## Commands

```bash
cd tools/tuneshift
.venv/bin/python -m pytest tests/ -x -q   # run tests
.venv/bin/ruff check .                     # lint
.venv/bin/python -m tuneshift --help       # CLI help
.venv/bin/python -m tuneshift list         # list all playlists
.venv/bin/python -m tuneshift status <name> # playlist sync status
.venv/bin/python -m tuneshift pin <name> --list  # show pins
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

### DB Schema (key tables)

| Table | Purpose |
|-------|---------|
| `tracks` | Canonical track metadata (title, artist, album, ISRC, energy, etc.) |
| `playlists` | Playlist definitions (name, auto_reorder flag, reorder_arc) |
| `playlist_tracks` | Track membership and position (playlist_id, track_id, position) |
| `playlist_pins` | Sequencer constraints (opener, closer, position, anchor groups) |
| `platform_tracks` | Platform-specific track IDs and match metadata |
| `platform_playlists` | Links canonical playlists to platform playlist IDs |
| `evidence` | Identity resolution evidence from MusicBrainz/Discogs |
| `sync_log` | Sync history |

## Pin System

The sequencer respects four pin types:

| Pin Type | Effect | CLI |
|----------|--------|-----|
| `opener` | Track is always first | `--opener TITLE` |
| `closer` | Track is always last | `--closer TITLE` |
| `position` | Track locked to specific 0-based index | `--position INDEX TITLE` |
| `anchor` | Group of tracks stays together in order | `--adjacent T1 T2 T3 [--group NAME]` |

Position 0 overrides opener; last-index position overrides closer. The optimizer
removes pinned tracks from the free pool, builds the sequence, then inserts
position-pinned tracks at their target indices. Post-optimization (2-opt, artist
distribution) protects all pinned positions.

## Version Matching Rules

The reconcile pipeline selects platform tracks in this priority:
1. **ISRC match** (score=100, but flags divergence if duration is >1.6x expected)
2. **Title+artist search** scored with `score_match_with_version`:
   - Base similarity (title: 0-50, artist: 0-30, album: 0-20)
   - Version penalty (live: -20, remix: -20, tribute: -20, compilation: -15, acoustic: -10, remaster: -10, deluxe: -5)
   - Duration penalty (>1.4x shortest: -10, >1.6x: -15, >2.0x: -20)
3. **User-approved mappings** are never re-reconciled

Key patterns caught by version penalty:
- Live recordings, concert versions
- Performance Mix, Extended Mix, Club Mix, 12" versions
- Instrumentals, dub mixes
- Compilations (Greatest Hits, Best Of, etc.)
- Tributes and reimaginings

### Known Tidal Pitfalls

- "Deluxe Remastered" albums bundle BBC/live recordings on bonus discs that share
  the same album name in metadata. The ISRC differs but album field is identical.
  Don't trust album name alone for studio vs. live determination.
- Track numbers matter: same album can have the single edit (track 1) and an
  extended mix (track 6) under the same album name (e.g., Youthquake).
- tidalapi returns whatever version Tidal's search ranks highest, which is often
  the extended/deluxe version. Duration comparison is essential.

## Platform Integration

| Platform | Client | Session File | Notes |
|----------|--------|-------------|-------|
| Tidal | `tidalapi` | `~/.local/share/tidal-importer/session.json` | Full CRUD, reorder works |
| YouTube Music | `ytmusicapi` | `~/.local/share/tuneshift/ytmusic_oauth.json` | Push works, reorder gets 403 (scope issue) |
| Spotify | Not yet implemented | - | Planned |

### YTM API Quirks
- Reorder requires `playlistItems.delete` permission which returns 403
- Track matching is by video ID, not ISRC
- Some tracks unavailable due to regional/licensing differences

## Testing

- **Run:** `.venv/bin/python -m pytest tests/ -x -q`
- **Lint:** `.venv/bin/ruff check .`
- Tests use real DB for integration, mocks for platform clients
- Bug fixes require regression tests
- New features require unit tests for the core logic

## Sequencer

The sequencer orders tracks by energy arc profiles (wave, narrative, descending).
It uses greedy nearest-neighbor construction, 2-opt local optimization, and
artist redistribution. Tracks can be pinned (opener, closer, position, adjacency
groups) which constrain the optimizer.

Key functions in `sequencer/optimizer.py`:
- `_resolve_pins`: Parse pins into opener/closer/position/anchor data
- `_select_endpoints`: Choose opener/closer (pinned or auto-selected)
- `_prepare_free_pool`: Separate free tracks from adjacency blocks
- `_greedy_build`: Construct sequence via nearest-neighbor with energy targets
- `optimize_sequence`: Top-level orchestrator
- `sequence_playlist`: DB-aware entry point (loads pins, metadata, calls optimizer)

## Error Handling Contract

All commands that push to platforms propagate failures as non-zero exit codes.
Platform errors go to stderr. The CLI top-level handler catches `TuneShiftError`
for clean messages and unexpected exceptions with opt-in traceback
(`TUNESHIFT_DEBUG=1`).

Exception handlers use specific exception types (not bare `except Exception`):
- Platform API errors: `OSError`, `RuntimeError`, `ValueError`, `KeyError`
- MusicBrainz: `MusicBrainzError` (from musicbrainzngs)
- Anthropic (classifier): `APIError` via `self._api_errors` tuple
