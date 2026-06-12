# TuneShift Skill

Use this skill when working on TuneShift (the canonical playlist manager at `tools/tuneshift/`).

## What TuneShift Is

TuneShift is a CLI tool that manages a canonical playlist database and syncs to
multiple streaming platforms (Tidal, YouTube Music). The SQLite database IS the
product: it is committed to git and represents the authoritative source of truth
for all playlists.

## Architecture

```
tools/tuneshift/
  tuneshift/
    cli.py                    # Argparse entry point
    db.py                     # SQLite database (schema + migrations + queries)
    models.py                 # Dataclasses: Track, Playlist, PlaylistPin, TrackResult, etc.
    matching.py               # Fuzzy matching, title normalization, scoring
    reconcile.py              # Multi-strategy reconciler (6 strategies, short-circuit at 90)
    platforms/
      tidal.py                # Tidal API client (tidalapi)
      ytmusic.py              # YouTube Music client (ytmusicapi)
    sequencer/
      __init__.py             # Re-exports sequence_playlist
      metadata.py             # TrackMetadata dataclass (30+ fields)
      classifier.py           # LLM-based track classification (populates metadata)
      scoring.py              # Pairwise scoring dimensions (energy, key, transition, narrative, etc.)
      modifiers.py            # Score modifiers (intensity arc, chapter break, duration pacing)
      optimizer.py            # Greedy sequence builder + pin resolution + moments
      profiles.py             # Weight profiles (default, narrative, etc.)
      intent.py               # Deterministic playlist intent inference
    commands/
      *.py                    # One file per CLI command
  tests/
    conftest.py               # tmp_db fixture, shared helpers
    test_*.py                 # pytest test files
  tuneshift.db                # The live database (committed to git)
  .venv/                      # Python virtual environment (not committed)
```

## Key Design Decisions

- **DB is committed**: `tuneshift.db` is the product. It is version-controlled.
- **Canonical tracks**: Tracks exist once in `tracks` table. Platform mappings link
  to specific platform IDs. Playlists reference tracks by ID.
- **Multi-strategy reconciliation**: Album lookup, ISRC, title+artist, title-only,
  album-in-query, artist-browse. Short-circuits at score >= 90.
- **Sequencer never drops tracks**: `sequence_playlist(db, playlist_id, arc=...)`
  loads from DB, sequences tracks with metadata, appends those without metadata at end.
- **Pins**: opener, closer, anchor (adjacency groups), position, moment (climax region).
- **Narrative intelligence**: Intent inference is deterministic (no LLM at runtime).
  The LLM classifier runs offline to populate metadata fields.

## Commands

```bash
# Virtual env and test
cd tools/tuneshift
source .venv/bin/activate
.venv/bin/python -m pytest tests/ -x -q

# CLI usage
tuneshift status                              # Overview of all playlists
tuneshift list                                # List playlist names
tuneshift add "Playlist" "Title" "Artist"     # Add track
tuneshift rm "Playlist" "Title"               # Remove track
tuneshift order "Playlist" --arc narrative     # Reorder by arc
tuneshift order "Playlist" --arc wave --dry-run  # Preview without applying
tuneshift sync "Playlist" tidal --auto        # Push to platform
tuneshift diff "Playlist" tidal               # Show what would change
tuneshift pin "Playlist" --opener "Title"     # Pin as opener
tuneshift pin "Playlist" --moment "Title"     # Pin as narrative moment
tuneshift map "Playlist" "Title" tidal TRACK_ID  # Manual platform mapping
tuneshift enrich "Playlist"                   # Fetch BPM/key from platform
tuneshift resolve "Playlist"                  # MusicBrainz identity resolution
```

## Reconciliation Flow

1. Check cache (approved mapping exists?) -> return immediately
2. Run strategies in order: album_lookup(90), isrc(100), title_artist(90),
   title_only(None), album_in_query(None), artist_browse(None)
3. After each strategy with a threshold, score top candidate. If >= threshold, stop.
4. Score all candidates uniformly. Return best with confidence level.

## Sequencer Flow

1. Load track IDs from DB
2. Build metadata map (TrackMetadata from tracks.metadata JSON column)
3. Resolve pins (opener, closer, adjacency, position, moment)
4. Infer intent (if arc == "narrative")
5. Select endpoints (opener/closer, pinned or auto-selected)
6. Build free pool (exclude pinned, opener, closer)
7. Greedy build with scoring (pairwise similarity + modifiers + arc curve)
8. Insert position-pinned tracks at target indices
9. 2-opt optimization + artist distribution (protect pinned positions)

## Platform Credentials

- Tidal: OAuth session at `~/.local/share/tuneshift/tidal_session.json`
- YouTube Music: OAuth at `~/.local/share/tuneshift/oauth.json` (ytmusicapi)

## Important Patterns

- All DB writes go through `Database` methods (never raw SQL in commands)
- `run()` wrapper is NOT used here (that is setup.sh convention)
- FK pragma is enabled on every connection
- Schema version is tracked; migrations run on open
- Platform clients expose: search_track, search_album, get_album_tracks,
  search_artist, get_artist_albums, search_isrc, get_track
- Test fixtures use `tmp_path` for isolated DB instances

## Known Constraints

- The classifier requires an LLM API call (configured via TUNESHIFT_CLASSIFIER_MODEL
  env var). It populates metadata offline, not at sequencing time.
- Narrative sequencing quality depends on metadata richness. Without classifier
  data, it falls back to pure sonic similarity.
- Manual/curated ordering should NOT be overwritten by the sequencer without
  explicit user intent. The `--dry-run` flag exists for previewing.
- No Soundiiz integration yet (candidate for future middleware layer).
- Artist separation enforcement can conflict with narrative intent when an artist
  dominates a playlist (e.g., Ethel Cain in Trans Wrath).
