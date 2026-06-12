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
    db.py                     # SQLite database (schema v7 + migrations + queries)
    models.py                 # Dataclasses: Track, Playlist, PlaylistPin, TrackResult, etc.
    matching.py               # Fuzzy matching, title normalization, scoring
    reconcile.py              # Multi-strategy reconciler (7 strategies incl. album tracklist)
    reconcile_prefs.py        # Version preference model (prefer/avoid/duration tolerance)
    platforms/
      tidal.py                # Tidal API client (tidalapi)
      ytmusic.py              # YouTube Music client (ytmusicapi)
    sequencer/
      __init__.py             # Re-exports sequence_playlist
      metadata.py             # TrackMetadata dataclass (30+ fields)
      classifier.py           # LLM-based track classification (populates metadata)
      scoring.py              # DIMENSION_SCORERS registry (10 dimensions), pairwise scoring
      weights.py              # Named presets (narrative-queen, energy-wave, etc.) + resolution
      modifiers.py            # Score modifiers (intensity arc, chapter break, duration pacing)
      optimizer.py            # Greedy sequence builder + pin resolution + section assignment
      profiles.py             # Weight profiles (default, narrative, etc.)
      intent.py               # Deterministic playlist intent inference
      narrative_parser.py     # Structured NarrativeSection parser
    curation/
      __init__.py
      context.py              # PlaylistContext dataclass
      scoring.py              # CURATION_SCORERS registry (6 dimensions)
      curator.py              # curate_trim, curate_analyze
      gap_analyzer.py         # Section coverage and transition gap detection
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
- **Playlist identity**: Every playlist has a required goal/description and optional
  collection, type, weights, mood_profile, and curation constraints.
- **Pipeline model**: reconcile -> curate -> sequence -> sync (each layer independent).
- **Weight vector model**: 10 sequencing dimensions (narrative_arc, energy_flow,
  mood_continuity, sonic_texture, lyrical_thread, emotional_arc, groove_coherence,
  era_mood, variety, artist_separation), each 0.0-1.0. Named presets as starting
  points (narrative-queen, energy-wave, mood-bath, discovery, workout).
- **Curation**: Score tracks across 6 dimensions (narrative_fit, mood_contribution,
  sonic_role, energy_role, uniqueness, redundancy). Trim by constraint, analyze
  for gaps, suggest fills.
- **Multi-strategy reconciliation**: Album lookup, album tracklist, ISRC,
  title+artist, title-only, album-in-query, artist-browse. Short-circuits at
  score >= 90. Version preferences cascade (global > playlist > per-track).
- **Narrative sections**: Chapter boundaries are HARD BREAKS in sequencer. Tracks
  are assigned to sections via greedy best-fit, then sequenced within each section.
- **Sequencer never drops tracks**: `sequence_playlist(db, playlist_id, arc=...)`
  loads from DB, sequences tracks with metadata, appends those without metadata at end.
- **Pins**: opener, closer, anchor (adjacency groups), position, moment (climax region).
- **Narrative intelligence**: Intent inference is deterministic (no LLM at runtime).
  The LLM classifier runs offline to populate metadata fields.
- **No Grok**: xAI/Grok backends are explicitly blocked in the classifier.

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

# Playlist identity
tuneshift goal "Playlist" "Description of purpose and theme"
tuneshift weights "Playlist" narrative-queen   # Apply named preset
tuneshift weights "Playlist" --set narrative_arc=0.9 mood_continuity=0.7
tuneshift weights "Playlist" --show            # View current weights

# Version preferences (reconciliation)
tuneshift prefs --prefer original             # Global: prefer originals
tuneshift prefs --avoid explicit              # Global: avoid explicit versions
tuneshift prefs --duration-tolerance 15       # Accept +/- 15s

# Curation
tuneshift curate "Playlist" --mode trim --target-duration 90m
tuneshift curate "Playlist" --mode analyze    # Score all tracks
tuneshift curate "Playlist" --mode fill       # Suggest tracks to add (placeholder)
```

## Reconciliation Flow

1. Check cache (approved mapping exists?) -> return immediately
2. Run strategies in order: album_lookup(90), album_tracklist(85), isrc(100),
   title_artist(90), title_only(None), album_in_query(None), artist_browse(None)
3. After each strategy with a threshold, score top candidate. If >= threshold, stop.
4. Score all candidates uniformly. Return best with confidence level.
5. Version preferences are applied as bonus/penalty scoring on top of base score.

## Sequencer Flow

1. Load track IDs from DB
2. Build metadata map (TrackMetadata from tracks.metadata JSON column)
3. Resolve weights (3-level cascade: CLI arg > DB stored > preset default 0.5)
4. Resolve pins (opener, closer, adjacency, position, moment)
5. Infer intent (if arc == "narrative")
6. If narrative text provided: parse sections, assign tracks to sections, sequence within each
7. Select endpoints (opener/closer, pinned or auto-selected)
8. Build free pool (exclude pinned, opener, closer)
9. Greedy build with scoring (pairwise similarity + modifiers + arc curve)
10. Insert position-pinned tracks at target indices
11. 2-opt optimization + artist distribution (protect pinned positions)

## Curation Flow

1. Build PlaylistContext from DB (goal, narrative sections, mood profile, all tracks)
2. Score each track across 6 dimensions using CURATION_SCORERS registry
3. Modes:
   - **analyze**: Return per-track scores and rankings
   - **trim**: Remove lowest-scoring tracks to meet target duration/count constraint
   - **fill** (placeholder): Identify gaps via gap_analyzer and suggest additions

## Weight Vector

10 dimensions, each 0.0-1.0:
- `narrative_arc`: Lyrical story progression
- `energy_flow`: BPM/intensity transitions
- `mood_continuity`: Emotional palette smoothness
- `sonic_texture`: Timbre/instrumentation coherence
- `lyrical_thread`: Thematic vocabulary continuity
- `emotional_arc`: Intensity curve shaping
- `groove_coherence`: Rhythmic compatibility
- `era_mood`: Decade/era mood consistency
- `variety`: Sonic diversity (higher = more contrast)
- `artist_separation`: Spread same-artist tracks apart

Resolution cascade: explicit CLI weights > DB-stored playlist weights > preset defaults > 0.5

## Platform Credentials

- Tidal: OAuth session at `~/.local/share/tuneshift/tidal.json`
- YouTube Music: OAuth at `~/.local/share/tuneshift/ytmusic.json` (ytmusicapi)
  - Client ID/secret: 1Password item "YouTube Data API - TuneShift"
- Spotify: PKCE OAuth at `~/.local/share/tuneshift/spotify.json` (spotipy)
  - Client ID: 1Password item "Spotify API - TuneShift" (credential field)
  - Fallback: `SPOTIPY_CLIENT_ID` env var

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
- Classifier explicitly blocks xAI/Grok models. FUCK ELON.
- Narrative sequencing quality depends on metadata richness. Without classifier
  data, it falls back to pure sonic similarity.
- Manual/curated ordering should NOT be overwritten by the sequencer without
  explicit user intent. The `--dry-run` flag exists for previewing.
- Curation fill mode is a placeholder (returns empty suggestions) pending
  recommendation engine integration.
- Gap analysis requires narrative sections to be defined on the playlist.
- No Soundiiz integration yet (candidate for future middleware layer).
- Artist separation enforcement can conflict with narrative intent when an artist
  dominates a playlist (e.g., Ethel Cain in Trans Wrath).

## Collections

Playlists can be grouped into collections (e.g., "Pride", "Laurel Canyon",
"Artist Spotlights"). Set via `db.set_collection(pid, "Pride")` or future CLI.
Query with `db.list_playlists_by_collection("Pride")`.
