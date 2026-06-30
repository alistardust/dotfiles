# Platform Metadata Enrichment + Track/Playlist Tagging

**Date:** 2026-06-29
**Status:** Draft
**Context:** During playlist organization, the AI agent lacks the metadata needed to make informed decisions about playlist classification (e.g., "is this playlist all Dolby Atmos?", "what era are these tracks?", "what genre does Tidal think this is?"). Currently the agent must ask the user or guess, which is unacceptable.

## Problem Statement

TuneShift stores track matching info (platform IDs, match scores) but **never pulls rich catalog metadata from the platforms themselves**. The enrichment pipeline uses external sources (MusicBrainz, Last.fm, Genius) but doesn't ask Tidal "what do you know about this track?" — audio quality tiers, release dates, genre classifications, album types.

This means:
- Cannot determine which playlists are Dolby Atmos without manually checking
- Cannot filter by era/decade without the user's memory
- Cannot auto-classify playlists by genre
- The AI agent is forced to ask obvious questions instead of looking up answers

## Acceptance Criteria

1. **The AI can self-answer "is this playlist Atmos?"** — after running enrichment, querying `track_platform_metadata` reveals audio quality tiers for every resolved track, and the AI can calculate "95% of tracks on this playlist have Atmos available" without asking the user.

2. **The AI can self-answer "what era is this playlist?"** — release year is stored per track, queryable, and aggregatable at playlist level.

3. **The AI can self-answer "what genre is this?"** — platform-assigned genre tags are stored per track and can be aggregated to characterize a playlist.

4. **Batch-friendly** — a single command can enrich all tracks on a playlist (or all playlists), with progress reporting, graceful timeouts, and skip-on-failure semantics.

5. **Track-level tags exist** — tracks can be tagged with arbitrary labels derived from platform metadata or applied manually.

6. **Playlist-level analysis is queryable** — a command produces a summary (era breakdown, genre distribution, quality availability) for any playlist.

## Design

### Part 1: Platform Metadata Pull

#### Storage: `track_platform_metadata` table

```sql
CREATE TABLE track_platform_metadata (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    platform TEXT NOT NULL,            -- 'tidal', 'spotify', 'ytmusic'
    platform_track_id TEXT NOT NULL,   -- the platform's ID for this track
    release_year INTEGER,
    release_date TEXT,                 -- ISO date if available
    genres TEXT,                       -- JSON array of platform genre strings
    audio_qualities TEXT,              -- JSON array: ["LOSSLESS", "HI_RES_LOSSLESS", "DOLBY_ATMOS"]
    album_name TEXT,
    album_type TEXT,                   -- 'album', 'single', 'compilation', 'ep'
    explicit BOOLEAN,
    duration_ms INTEGER,
    popularity INTEGER,                -- platform popularity score if available
    raw_metadata TEXT,                 -- full JSON dump for future use
    fetched_at TEXT NOT NULL,          -- ISO timestamp
    UNIQUE(track_id, platform)
);
```

#### Command Interface

```bash
# Enrich a specific playlist's tracks from Tidal
tuneshift enrich "Playlist Name" --platform tidal

# Enrich all playlists
tuneshift enrich --all --platform tidal

# Re-fetch stale metadata (older than N days)
tuneshift enrich "Playlist" --platform tidal --refresh --stale-days 30
```

#### Behavior

- For each track on the playlist:
  1. If track has a `platform_track_id` in `platform_tracks` → use it
  2. If unmapped → attempt resolution first (existing resolve logic), then fetch
  3. Call Tidal API: get track details (quality tiers, release info, genres)
  4. Upsert into `track_platform_metadata`
- Progress: per-track reporting (`[42/120] Fetching: "Creep" by Radiohead...`)
- Timeout: 300s max per track, graceful skip on failure
- Rate limiting: respect existing `RateLimiter` class
- Batch size: configurable, default all tracks on playlist

#### Tidal API Fields to Fetch

From `tidalapi` track object:
- `track.audio_quality` / `track.audio_modes` → audio_qualities (includes DOLBY_ATMOS)
- `track.album.release_date` → release_year, release_date
- `track.album.name` → album_name
- `track.album.type` → album_type (via album endpoint)
- `track.explicit` → explicit
- `track.duration` → duration_ms

**Artist genres (primary genre source):**
- Fetch via `tidalapi` artist endpoint: `artist.get_bio()` or artist page metadata
- Store on `artists.genres` column (JSON array)
- If artist has no genres on Tidal, fall back to existing MusicBrainz/Last.fm enrichment
- If no genre data from any source: leave empty, track is counted as "genre unknown" in analysis

Genre fetch happens once per artist (not per track). If an artist already has genres populated and they're less than 30 days old, skip.

### Part 2: Track-Level Tagging

#### Storage: `track_tags` table

```sql
CREATE TABLE track_tags (
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    tag TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',  -- 'manual', 'derived', 'platform'
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (track_id, tag)
);
```

#### Command Interface

```bash
# Tag a track manually (requires artist to disambiguate)
tuneshift tag track "Creep" "Radiohead" --add "90s" "alt-rock" "sad"

# Remove a tag
tuneshift tag track "Creep" "Radiohead" --rm "sad"

# Query tracks by tag
tuneshift tag query --tracks --filter "atmos-available"
tuneshift tag query --tracks --filter "90s" --filter "pop"  # AND logic

# List all tags in use
tuneshift tag list-tags
```

If only title is provided and multiple tracks share that title, the command errors and lists matches for disambiguation.

### Part 3: Derive + Analyze

#### Tag Derivation Rules

After platform metadata is pulled, auto-derive tags:

```bash
# Run derivation on a playlist
tuneshift tag derive "Playlist Name"

# Run on all tracks with metadata
tuneshift tag derive --all
```

Built-in derivation rules:
- `audio_qualities` contains "DOLBY_ATMOS" → tag: `atmos-available`
- `release_year` 1960-1969 → tag: `60s`, etc. for each decade
- `album_type` = "single" → tag: `single`
- Platform genres → normalized tag equivalents (e.g., Tidal "Grunge" → tag: `grunge`)

Rules are configurable/extensible but ship with sensible defaults.

**Reconciliation on re-derive:** Derived tags (source='derived') are **replaced** on each run. If metadata changes (e.g., a track gains Atmos availability), the next `tag derive` run adds the tag. If metadata no longer qualifies (unlikely but possible), the stale derived tag is removed. Manual tags (source='manual') are never touched by derivation.

#### Playlist Analysis

```bash
# Analyze a playlist
tuneshift analyze "Playlist Name"
```

Output:
```
=== I Want It That Way (41 tracks, 38 with metadata) ===
  Era: 90% 1996-2000, 10% 2000-2001 (based on 38 tracks with release year)
  Genres: pop (85%), dance-pop (30%), R&B (10%) (based on 35 tracks with genre data)
  Quality: 75% Atmos available, 100% lossless (based on 38 tracks with quality data)
  Album types: 60% album, 30% single, 10% compilation
  Tags: 90s-pop (35 tracks), atmos-available (31 tracks)
  Gaps: 3 tracks unresolved on Tidal (no metadata)
```

**Denominator rules:** Percentages are calculated over tracks that HAVE metadata for that field, not total tracks. The output always shows the denominator ("based on N tracks with X"). Unresolved/unmapped tracks are reported separately as "Gaps".

This data is surfaced for the AI or user to make informed decisions. Playlist auto-tagging via collections is **out of scope for v1** — the AI uses `analyze` output to manually assign collections/folders as needed.

### CLI Namespace

The existing `tuneshift tag`/`untag` commands operate on **playlists** (assigning to collections). The new track-level commands use a subcommand namespace:
- `tuneshift tag "Playlist" "Collection"` — existing, unchanged (playlist → collection)
- `tuneshift tag track "Title" "Artist" --add/--rm` — new, track-level tags
- `tuneshift tag query` — new, search by tags
- `tuneshift tag derive` — new, auto-derive from metadata
- `tuneshift tag list-tags` — new, list all tags

No conflict: `tag track` vs `tag "PlaylistName"` disambiguates by the `track` keyword.

### Integration with Existing Systems

- **Enrichment pipeline** (`tuneshift enrich`): the `--platform` flag already exists but only fetches BPM/key. This extends it to fetch the full catalog metadata.
- **Collections** (`tuneshift tag`/`untag`): remain as playlist-level groupings. Track tags are a new parallel system.
- **Audit** (`tuneshift audit`): can use metadata to flag concept violations (e.g., "this track is from 2003 but the concept says 1996-2000").
- **Folders** (`tuneshift folders`): analysis can suggest folder assignments ("this playlist is 100% Atmos → suggest Atmos folder").

## Non-Goals

- Not building a recommendation engine
- Not replacing the existing enrichment pipeline (MusicBrainz/Last.fm/Genius) — this supplements it with platform-native data
- Not implementing Spotify or YTM metadata pull in v1 (schema supports it, implementation is Tidal-first)

## Decisions

1. **Genre storage:** Artist-level genres are stored on the `artists.genres` column (already exists). The `track_platform_metadata.genres` field stores track-level genre tags IF the platform provides them (Tidal mostly doesn't — it has artist genres). Tag derivation reads from `artists.genres` first, falls back to `track_platform_metadata.genres`. No contradiction: both can coexist, artist genres are the primary source.

2. **Playlist analysis output:** Computed on-the-fly from the metadata tables. It's fast SQL aggregation. No caching needed.

3. **Playlist auto-tagging:** Out of scope for v1. The existing `collections` system handles playlist-level grouping. The `analyze` command surfaces data; the AI or user decides what to do with it. Future work can add auto-collection assignment if needed.

4. **Track selection for tagging:** `tuneshift tag track "Title" "Artist"` requires both title and artist to disambiguate. If only title is provided and multiple tracks match, the command errors with a list of matches. Tags apply to the canonical track (the `tracks` table row), not per-playlist instances.
