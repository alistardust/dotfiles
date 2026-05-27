# tidal-importer

Import CSV playlists (Soundiiz format) into Tidal with fuzzy matching and playlist sync.

## Install

```bash
cd scripts/tidal-importer
pip install -e .
```

## Usage

### 1. Login

```bash
tidal-importer login
```

Opens a browser URL for Tidal OAuth. Session is saved locally.

### 2. Reconcile

Match CSV tracks against the Tidal catalog:

```bash
tidal-importer reconcile playlists/lc-vibes.csv
```

Options:
- `-o PATH` : Output JSON path (default: `<csv>.reconciled.json`)
- `--playlist-id ID` : Diff against existing playlist (marks already-present tracks)

### 3. Import

Create or sync a Tidal playlist from reconciled results:

```bash
# Create new playlist
tidal-importer import lc-vibes.reconciled.json --name "LC Vibes"

# Sync existing playlist (add missing, remove extras, reorder)
tidal-importer import lc-vibes.reconciled.json --name "LC Vibes" --playlist-id abc123

# Keep extra tracks (don't remove)
tidal-importer import lc-vibes.reconciled.json --name "LC Vibes" --playlist-id abc123 --no-remove

# Dry run (preview changes)
tidal-importer import lc-vibes.reconciled.json --name "LC Vibes" --dry-run
```

## Matching

- Title: 50 points (exact after normalization) or fuzzy (30/15)
- Artist: 30 points (exact) or fuzzy (20)
- Album: 20 points (exact) or 10 (fuzzy ratio >= 0.75)
- High confidence: score >= 80 AND next-best < 70
- Remasters preferred on tied scores

## Playlist Sync

When updating an existing playlist:
1. Fetches current tracks
2. Identifies missing, extra, and out-of-order tracks
3. Removes extras (unless `--no-remove`)
4. Adds missing tracks
5. Reorders to match CSV sequence

## Security

- Session stored at `~/.local/share/tidal-importer/session.json` (0600)
- No symlink following on credential paths
- Token redaction in all error output
- ANSI sanitization on API responses

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
