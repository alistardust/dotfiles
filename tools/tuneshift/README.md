# tuneshift

Canonical playlist manager with cross-platform distribution.

Manages a local SQLite library of tracks and playlists, then distributes them
to Tidal, Spotify, and YouTube Music with intelligent version matching and
cached reconciliation.

## Install

```bash
cd tools/tuneshift
uv venv && uv pip install -e ".[dev]"
```

## Usage

```bash
# Authenticate with platforms
tuneshift login tidal
tuneshift login spotify
tuneshift login ytmusic

# Import an existing playlist from a platform
tuneshift ingest tidal <playlist-id>
tuneshift ingest spotify <playlist-id>

# Manage tracks
tuneshift add "Diamond Dogs" "Diamond Dogs" "David Bowie" --album "Diamond Dogs"
tuneshift rm "Diamond Dogs" 3        # by position
tuneshift rm "Diamond Dogs" "Rebel"  # by title match

# View state
tuneshift list
tuneshift status "Diamond Dogs"
tuneshift diff "Diamond Dogs" spotify

# Sync to platforms (reconcile + push)
tuneshift sync "Diamond Dogs" spotify
tuneshift sync "Diamond Dogs" --all
tuneshift sync --all

# Reorder by energy arc
tuneshift order "Diamond Dogs" --arc wave
```

## Architecture

- **Database**: SQLite in `tools/tuneshift/tuneshift.db` (committed to repo)
- **Matching**: Normalized title/artist/album comparison with scoring
- **Reconciliation**: ISRC lookup, then text search, with cached results
- **Platforms**: Protocol-based abstraction (Tidal, Spotify, YTMusic)
- **Sequencer**: Energy-arc-based track ordering (migrated from tidal-importer)

## Shell Completions

```bash
# Generate for your shell
tuneshift --print-completion bash >> ~/.bash_completion
tuneshift --print-completion zsh >> ~/.zshrc
tuneshift --print-completion fish >> ~/.config/fish/completions/tuneshift.fish
```

## Database Location

The DB lives in the repo at `tools/tuneshift/tuneshift.db` and is committed
to git for cross-machine sync. Auth tokens live separately in
`~/.local/share/tuneshift/` (never committed).

## Architecture

TuneShift follows a **canonical-first, push-only** model:

- **`tuneshift.db` is the product.** The SQLite database is the single source of
  truth for all playlists, tracks, metadata, and platform mappings. It is
  intentionally committed to git for versioning and cross-machine sync.
- **Platforms are distribution targets.** Changes flow one direction: edit locally,
  push to platforms. Platforms never overwrite local state.
- **Credentials are never committed.** Auth tokens live in
  `~/.local/share/tuneshift/` with 0700 permissions.
- **Schema migrations are automatic.** The DB's `user_version` pragma drives
  migrations in `db.py:_migrate_schema()`.

### Module Layout

```
tuneshift/
  cli.py              # Argument parsing, command dispatch
  db.py               # SQLite schema, migrations, all persistence
  models.py           # Shared dataclasses (Track, Playlist, etc.)
  matching.py         # Fuzzy title/artist matching, version scoring
  reconcile.py        # Find platform equivalents for canonical tracks
  commands/           # One file per CLI subcommand
  platforms/          # Platform API clients (tidal, spotify, ytmusic)
  sequencer/          # Track ordering (energy arcs, pinning, 2-opt)
  identity/           # Cross-platform track identity resolution
```
