# TuneShift Reconciliation & Data Integrity Overhaul

**Date:** 2026-06-09
**Scope:** `tools/tuneshift/tuneshift/` (matching, reconcile, commands, platforms, sequencer)
**Status:** Approved

## Problem Statement

The current reconciliation pipeline has critical gaps that cause tracks to be
marked "unavailable" when they exist on the platform, and the rm/add/order
pipeline has data integrity bugs that silently drop tracks during reorder
operations.

### Failure Modes Observed

1. **Featured artist mismatch**: "Louder" by Big Freedia not found because Tidal
   lists it as "Louder (feat. Icona Pop)". The title fuzzy ratio drops below
   threshold.
2. **Search too narrow**: Left at London, Wendy Carlos, and G.L.O.S.S. all exist
   on platforms but aren't found by a single `title + artist` text query.
3. **Wrong version selected**: Extended mixes, performance mixes, and deluxe bonus
   tracks chosen over standard versions (partially fixed by duration penalty, but
   album-level lookup would prevent this entirely).
4. **No escape hatch**: When automated matching fails, there is no CLI command to
   force-link a track to a known platform ID.
5. **Tracks dropped during reorder**: The sequencer's `sequence_playlist` filters
   tracks without metadata into `missing_ids` and appends them, but if track IDs
   become stale (deleted between load and write), tracks disappear silently.
6. **`rm` doesn't cascade**: Removing a track from `playlist_tracks` leaves stale
   entries in `playlist_pins` and stale platform mappings that confuse future
   reconciliation.

## Design

### 1. Multi-Strategy Reconciler

**File:** `tuneshift/reconcile.py`

Replace the current linear ISRC-then-search pipeline with a strategy executor
that tries all available strategies, collects candidates, deduplicates, and
scores uniformly.

```python
def reconcile_track(db, track_id, client, force=False, cached_mapping=None) -> ReconcileResult:
    # ... existing cache/mapping checks unchanged ...

    candidates: list[TrackResult] = []
    candidates += strategy_album_lookup(track, client)
    candidates += strategy_isrc(track, client)
    candidates += strategy_title_artist(track, client)
    candidates += strategy_title_only(track, client)
    candidates += strategy_album_in_query(track, client)
    candidates += strategy_artist_browse(track, client)

    # Deduplicate by platform_id
    seen: set[str] = set()
    unique: list[TrackResult] = []
    for c in candidates:
        if c.platform_id not in seen:
            seen.add(c.platform_id)
            unique.append(c)

    # Score all candidates uniformly
    scored = score_candidates(track, unique)
    return select_best(scored)
```

Each strategy is a standalone function that returns `list[TrackResult]`. If a
strategy errors (rate limit, network, unsupported), it returns an empty list
without failing the pipeline.

#### Strategy: Album Lookup (highest priority when album is known)

```python
def strategy_album_lookup(track: Track, client) -> list[TrackResult]:
    if not track.album:
        return []
    albums = client.search_album(f"{track.album} {track.artist}", limit=5)
    # Prefer standard editions over deluxe/expanded
    albums = sorted(albums, key=lambda a: _edition_penalty(a.name))
    results: list[TrackResult] = []
    for album in albums[:3]:  # Check top 3 album matches
        tracklist = client.get_album_tracks(album.platform_id)
        results.extend(tracklist)
    return results
```

When the canonical track has an album field, this strategy searches for that
album on the platform, retrieves the full tracklist, and returns all tracks as
candidates. The scorer then picks the best match using title similarity +
duration proximity.

**Tiebreaker for same-title tracks on the same album:**
1. Duration closest to canonical `duration_seconds`
2. Exact title match (no parenthetical suffix) over partial
3. Lower track number (standard position over bonus track position)

#### Strategy: ISRC

Unchanged from current behavior. Returns at most one result.

#### Strategy: Title + Artist

Current `search_track(f"{title} {artist}")` behavior. Returns up to 10 results.

#### Strategy: Title Only

`search_track(title, limit=10)` for a broader net. Useful for artists with
unusual names that confuse platform search.

#### Strategy: Album in Query

`search_track(f"{title} {album}")` when album is known. Some platforms surface
the right track when album context is included.

#### Strategy: Artist Browse

```python
def strategy_artist_browse(track: Track, client) -> list[TrackResult]:
    artists = client.search_artist(track.artist, limit=3)
    results: list[TrackResult] = []
    for artist in artists[:1]:  # Top artist match only
        albums = client.get_artist_albums(artist.platform_id, limit=20)
        for album in albums:
            if track.album and _album_matches(album.name, track.album):
                tracklist = client.get_album_tracks(album.platform_id)
                results.extend(tracklist)
                break  # Found the right album
    return results
```

Last resort: find the artist, browse their discography for the right album, then
get its tracklist. Rate-limited and expensive, only reached when other strategies
fail.

### 2. Improved Scoring

**File:** `tuneshift/matching.py`

#### Featured Artist Normalization

Add to `normalize_title()`:

```python
_FEAT_RE = re.compile(
    r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s+[^\)\]]+[\)\]]",
    re.IGNORECASE,
)

def normalize_title(title: str) -> str:
    title = unicodedata.normalize("NFC", title)
    title = _EDITION_PARENS_RE.sub("", title)
    title = _FEAT_RE.sub("", title)  # NEW: strip featured artists
    return title.strip().casefold()
```

Both source and candidate titles get featured artists stripped before comparison.
This means "Louder" and "Louder (feat. Icona Pop)" normalize to the same string.

#### Duration-Based Tiebreaker Enhancement

When multiple candidates score identically on title/artist/album, prefer the one
whose duration is closest to the canonical `duration_seconds`:

```python
def duration_proximity_bonus(candidate_duration: int | None, canonical_duration: int | None) -> int:
    """Bonus 0-10 for duration proximity to canonical."""
    if not candidate_duration or not canonical_duration:
        return 0
    diff_pct = abs(candidate_duration - canonical_duration) / canonical_duration
    if diff_pct < 0.05:  # Within 5%
        return 10
    if diff_pct < 0.15:
        return 5
    return 0
```

This bonus is added AFTER the version penalty, so a short-duration match on a
compilation still loses to a same-duration match on the right album.

### 3. Manual Mapping CLI

**New file:** `tuneshift/commands/map_cmd.py`

```
tuneshift map <playlist> <title> --tidal <TRACK_ID> [--verify]
tuneshift map <playlist> <title> --ytmusic <VIDEO_ID> [--verify]
tuneshift unmap <playlist> <title> --tidal
tuneshift unmap <playlist> <title> --ytmusic
```

**Behavior:**

- `map`: Sets `platform_tracks.user_approved = 1` for the given track+platform
  combination. With `--verify`, calls the platform API to confirm the ID exists
  and displays the track metadata (title, artist, album, duration) for the user
  to confirm.
- `unmap`: Clears the platform mapping for that track+platform, forcing the next
  sync to re-reconcile.

**Implementation:**

```python
def handle_map(args, db: Database) -> int:
    playlist = db.find_playlist_by_name(args.playlist)
    track = _find_track_by_title(db, playlist, args.title)
    platform, platform_id = _extract_platform_args(args)

    if args.verify:
        client = _load_client(platform)
        result = client.get_track(platform_id)
        if not result:
            print(f"Track ID {platform_id} not found on {platform}", file=sys.stderr)
            return 1
        print(f"Found: {result.title} - {result.artist} ({result.album})")
        print(f"Duration: {result.duration_seconds}s")

    db.set_platform_mapping(
        track_id=track.id,
        platform=platform,
        platform_track_id=platform_id,
        user_approved=True,
        platform_title=result.title if args.verify else None,
        platform_artist=result.artist if args.verify else None,
        platform_album=result.album if args.verify else None,
        match_score=100,
    )
    print(f"Mapped \"{track.title}\" -> {platform}:{platform_id}")
    return 0
```

### 4. Data Integrity Fixes

#### 4a. Cascade Delete on `rm`

**File:** `tuneshift/commands/rm_cmd.py` and `tuneshift/db.py`

The `rm` command currently calls `db.remove_playlist_track_by_position()`. This
removes the row from `playlist_tracks` but leaves:
- Stale entries in `playlist_pins` referencing the removed track
- Platform mappings that are no longer relevant

**Fix:** Add `db.remove_track_from_playlist(playlist_id, track_id)` that performs
a cascading delete in one transaction:

```python
def remove_track_from_playlist(self, playlist_id: int, track_id: int) -> None:
    """Remove track from playlist with cascade cleanup."""
    with self.conn:
        self.conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        self.conn.execute(
            "DELETE FROM playlist_pins WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        # Recompact positions
        rows = self.conn.execute(
            "SELECT id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        for idx, row in enumerate(rows):
            self.conn.execute(
                "UPDATE playlist_tracks SET position = ? WHERE id = ?",
                (idx, row[0]),
            )
```

#### 4b. Sequencer Never Drops Tracks

**File:** `tuneshift/sequencer/optimizer.py`

Current `sequence_playlist` (line 474):
```python
metadata_tracks = [metadata_map[track_id] for track_id in track_ids if track_id in metadata_map]
missing_ids = [track_id for track_id in track_ids if track_id not in metadata_map]
```

This is correct in intent (metadata-less tracks go at the end) but the bug is
upstream: `track_ids` comes from the caller and may be stale.

**Fix:** Change `sequence_playlist` signature to accept `playlist_id` directly
(avoids chicken-and-egg problem if `track_ids[0]` is stale):

```python
def sequence_playlist(db, playlist_id: int, arc="wave", profile="default") -> list[int]:
    # Always reload authoritative membership from DB
    track_ids = db.get_playlist_track_ids(playlist_id)
    if len(track_ids) <= 1:
        return list(track_ids)

    # ... rest of function uses authoritative track_ids ...
```

Callers (e.g., `order_cmd.py`) pass `playlist.id` instead of a pre-fetched list.
If any previously-known track_id is absent from the authoritative list, emit a
warning to stderr (surfaces inconsistency instead of hiding it).

#### 4c. `add --replace` for Atomic Swaps

**File:** `tuneshift/commands/add_cmd.py`

New flag: `tuneshift add <playlist> <title> <artist> --replace "Old Title"`

This atomically:
1. Finds the old track by title match
2. Inherits its position and any pins (type-aware: opener/closer/position/anchor
   pins transfer to the new track unchanged; if the old track was a `closer` pin
   but is being replaced at a non-final position, the pin type stays `closer`
   since pins describe sequencer intent, not current position)
3. Inserts the new track at the same position
4. Removes the old track (with cascade cleanup)
5. Syncs both the removal and addition to platforms

This prevents the "add new track, forget to rm old track" pattern that creates
duplicates.

#### 4d. Foreign Key Enforcement

**File:** `tuneshift/db.py`

Enable SQLite foreign key enforcement on connection open:

```python
def __init__(self, path=None):
    self.conn = sqlite3.connect(str(self._path))
    self.conn.execute("PRAGMA foreign_keys = ON")
```

Note: This requires that all existing data satisfies FK constraints. Add a
migration that cleans orphaned rows before enabling.

### 5. Platform Client Extensions

**Files:** `tuneshift/platforms/tidal.py`, `tuneshift/platforms/ytmusic.py`

New methods required by the multi-strategy reconciler:

```python
class TidalClient:
    def search_album(self, query: str, limit: int = 5) -> list[AlbumResult]: ...
    def get_album_tracks(self, album_id: str) -> list[TrackResult]: ...
    def search_artist(self, query: str, limit: int = 3) -> list[ArtistResult]: ...
    def get_artist_albums(self, artist_id: str, limit: int = 20) -> list[AlbumResult]: ...
    def get_track(self, track_id: str) -> TrackResult | None: ...
```

New models:

```python
@dataclass
class AlbumResult:
    platform_id: str
    title: str
    artist: str
    track_count: int
    release_year: int | None = None

@dataclass
class ArtistResult:
    platform_id: str
    name: str
```

The `tidalapi` library already supports `session.search(query, models=[Album])`,
`album.tracks()`, `session.search(query, models=[Artist])`, and
`artist.get_albums()`. The YTM `ytmusicapi` supports equivalent operations via
`search(query, filter="albums")`, `get_album(album_id)`, `search(query,
filter="artists")`, and `get_artist(artist_id)["albums"]`.

### 6. Rate Limiting Considerations

The artist browse strategy is expensive (multiple API calls per track). The
reconciler should:
- Run strategies in order, short-circuiting if a high-confidence match is found
  early (score >= 90 from album lookup or ISRC)
- Track total API calls per reconcile run and warn if approaching rate limits
- Use the existing `RateLimiter` class for all new API calls

**Short-circuit rule:** If album lookup or ISRC returns a candidate scoring >= 90,
skip remaining strategies. This keeps the common case fast while ensuring
difficult tracks still get the full cascade.

## Testing Strategy

| Component | Test Type | Coverage |
|-----------|-----------|----------|
| Strategy functions | Unit (mock client) | Each strategy returns expected candidates |
| Featured artist normalization | Unit | Parameterized: "Louder (feat. X)", "(ft. Y)", "(with Z)" |
| Duration proximity bonus | Unit | Edge cases: None durations, exact match, 2x divergence |
| `map`/`unmap` commands | Integration | DB state before/after, `--verify` with mock client |
| Cascade delete | Integration | Verify playlist_pins cleaned up, positions recompacted |
| Sequencer no-drop guarantee | Unit | Tracks without metadata still appear in output |
| `add --replace` | Integration | Position inheritance, pin transfer, platform sync |
| End-to-end reconcile | Integration | Mock client with multiple strategies needed |

## Migration Plan

1. Add new platform client methods (non-breaking, additive)
2. Add featured artist normalization (improves existing behavior)
3. Implement multi-strategy reconciler (replaces `reconcile_track` internals)
4. Add `map`/`unmap` CLI command
5. Fix cascade delete in `rm`
6. Fix sequencer authoritative reload
7. Add `--replace` flag to `add`
8. Enable FK pragma + migration to clean orphans
9. Add duration proximity bonus to scoring

Each step is independently committable and testable. Steps 1-3 form the core
improvement. Steps 4-9 are complementary fixes.

## Out of Scope

- Spotify platform client (not yet implemented, separate effort)
- YTM reorder fix (403 Forbidden, requires OAuth scope change)
- Soundiiz integration (no public API available)
- Batch re-reconcile of all existing playlists (manual trigger via `sync --reconcile`)
