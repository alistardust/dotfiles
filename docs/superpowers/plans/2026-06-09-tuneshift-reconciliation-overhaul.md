# TuneShift Reconciliation & Data Integrity Overhaul - Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-strategy reconciler with a multi-strategy cascade, add manual mapping, fix data integrity bugs in the rm/add/order pipeline, and improve matching scoring.

**Architecture:** Strategy pattern for reconciliation (6 search strategies, deduplicate, score uniformly). New platform client methods for album/artist browsing. Cascade delete in rm. Sequencer takes playlist_id directly. Featured artist normalization in matching.

**Tech Stack:** Python 3.10+, SQLite, tidalapi, ytmusicapi, pytest, ruff

**Spec:** `docs/superpowers/specs/2026-06-09-tuneshift-reconciliation-overhaul-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `tuneshift/models.py` | Modify | Add `AlbumResult`, `ArtistResult` dataclasses |
| `tuneshift/matching.py` | Modify | Featured artist normalization, duration proximity bonus |
| `tuneshift/reconcile.py` | Rewrite | Multi-strategy pipeline with dedup and uniform scoring |
| `tuneshift/platforms/tidal.py` | Modify | Add `search_album`, `get_album_tracks`, `search_artist`, `get_artist_albums`, `get_track` |
| `tuneshift/platforms/ytmusic.py` | Modify | Add same methods for YTM equivalents |
| `tuneshift/commands/map_cmd.py` | Create | `handle_map` and `handle_unmap` commands |
| `tuneshift/commands/rm_cmd.py` | Modify | Use new cascade delete method |
| `tuneshift/commands/add_cmd.py` | Modify | Add `--replace` flag |
| `tuneshift/commands/order_cmd.py` | Modify | Pass `playlist_id` to sequencer |
| `tuneshift/sequencer/optimizer.py` | Modify | Change `sequence_playlist` signature to accept `playlist_id` |
| `tuneshift/sequencer/__init__.py` | Modify | Update re-export if needed |
| `tuneshift/cli.py` | Modify | Add `map`/`unmap` subparsers, `--replace` to add |
| `tuneshift/db.py` | Modify | Add `remove_track_from_playlist`, enable FK pragma, add `get_playlist_track_ids` |
| `tests/test_matching.py` | Modify | Featured artist normalization tests |
| `tests/test_reconcile.py` | Modify | Multi-strategy tests |
| `tests/test_map_cmd.py` | Create | map/unmap command tests |
| `tests/test_rm_cascade.py` | Create | Cascade delete tests |
| `tests/test_sequencer_integrity.py` | Create | No-drop guarantee tests |
| `tests/test_tidal_client.py` | Modify | New method tests |

---

## Pre-Execution Notes

**Existing test files:** `tests/test_matching.py`, `tests/test_tidal_client.py`, and
`tests/test_add_cmd.py` already exist in the repo. New tests are ADDED to them, not
creating new files.

**FK pragma ordering:** The pragma is enabled in `__init__` BUT the orphan cleanup
migration runs in `_migrate_schema()` which is called from `__init__` BEFORE the
pragma takes effect on subsequent operations. The cleanup migration itself does not
need FK enforcement (it's just DELETEs). The pragma protects future writes.

**Schema version:** Current version is 4. Migration to 5 adds orphan cleanup.

**Position inheritance with cascade:** When `--replace` removes the old track, it
captures the position BEFORE the cascade delete. After deletion + recompaction, the
target position may shift. The implementation inserts at the captured position value
directly (before recompaction runs for the new insert, positions are already 0-based
contiguous after the old track's removal).

**`db.find_track()`:** This method already exists in db.py (search by normalized
title+artist+album).

---

## Chunk 1: Models and Matching Improvements

### Task 1: Add AlbumResult and ArtistResult models

**Files:**
- Modify: `tuneshift/models.py`

- [ ] **Step 1: Add AlbumResult dataclass**

```python
@dataclass
class AlbumResult:
    """An album search result from any platform."""

    platform_id: str
    title: str
    artist: str
    track_count: int = 0
    release_year: int | None = None


@dataclass
class ArtistResult:
    """An artist search result from any platform."""

    platform_id: str
    name: str
```

Add these after the `PlaylistInfo` class (before `PlaylistPin`).

- [ ] **Step 2: Run tests to verify no breakage**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All existing tests pass (models are additive).

- [ ] **Step 3: Commit**

```bash
git add tuneshift/models.py
git commit -m "feat(tuneshift): add AlbumResult and ArtistResult models"
```

---

### Task 2: Add featured artist normalization to matching

**Files:**
- Modify: `tuneshift/matching.py`
- Modify: `tests/test_matching.py`

- [ ] **Step 1: Write failing tests for featured artist stripping**

In `tests/test_matching.py`, add:

```python
import pytest
from tuneshift.matching import normalize_title


@pytest.mark.parametrize("raw,expected", [
    ("Louder (feat. Icona Pop)", "louder"),
    ("Revolution! (ft. Someone)", "revolution!"),
    ("Together (with Dua Lipa)", "together"),
    ("Hello (featuring Adele)", "hello"),
    ("Normal Title", "normal title"),
    ("Title [feat. Artist]", "title"),
    ("Already (Deluxe Remastered) (feat. X)", "already"),
])
def test_normalize_title_strips_featured_artists(raw, expected):
    assert normalize_title(raw) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_matching.py::test_normalize_title_strips_featured_artists -v`
Expected: Some parametrized cases FAIL (featured artists not stripped yet).

- [ ] **Step 3: Implement featured artist stripping**

In `tuneshift/matching.py`, add the regex after `_THE_PREFIX_RE` (line 14):

```python
_FEAT_RE = re.compile(
    r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s+[^\)\]]+[\)\]]",
    re.IGNORECASE,
)
```

Update `normalize_title()`:

```python
def normalize_title(title: str) -> str:
    """Normalize a track/album title for comparison."""
    if not title:
        return ""
    title = unicodedata.normalize("NFC", title)
    title = _EDITION_PARENS_RE.sub("", title)
    title = _FEAT_RE.sub("", title)
    return title.strip().casefold()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_matching.py::test_normalize_title_strips_featured_artists -v`
Expected: All PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass. The normalization change may affect existing `score_match` tests if they relied on featured artist text being present; fix any legitimate regressions.

- [ ] **Step 6: Commit**

```bash
git add tuneshift/matching.py tests/test_matching.py
git commit -m "feat(tuneshift): strip featured artist parentheticals in title normalization"
```

---

### Task 3: Add duration proximity bonus

**Files:**
- Modify: `tuneshift/matching.py`
- Modify: `tests/test_matching.py`

- [ ] **Step 1: Write failing tests**

```python
from tuneshift.matching import duration_proximity_bonus


@pytest.mark.parametrize("candidate,canonical,expected", [
    (200, 200, 10),      # exact match
    (195, 200, 10),      # within 5%
    (180, 200, 5),       # within 15% (10% diff)
    (150, 200, 0),       # too different (25% diff)
    (None, 200, 0),      # missing candidate duration
    (200, None, 0),      # missing canonical duration
])
def test_duration_proximity_bonus(candidate, canonical, expected):
    assert duration_proximity_bonus(candidate, canonical) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_matching.py::test_duration_proximity_bonus -v`
Expected: FAIL (function does not exist yet).

- [ ] **Step 3: Implement duration_proximity_bonus**

In `tuneshift/matching.py`, after `duration_penalty()`:

```python
def duration_proximity_bonus(
    candidate_duration: int | None,
    canonical_duration: int | None,
) -> int:
    """Bonus 0-10 for duration proximity to canonical track.

    Rewards candidates whose duration closely matches what we expect.
    """
    if not candidate_duration or not canonical_duration:
        return 0
    if canonical_duration < 30:
        return 0
    diff_pct = abs(candidate_duration - canonical_duration) / canonical_duration
    if diff_pct < 0.05:
        return 10
    if diff_pct < 0.15:
        return 5
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_matching.py::test_duration_proximity_bonus -v`
Expected: All PASS.

- [ ] **Step 5: Integrate into score_match_with_version**

Update `score_match_with_version` to add the bonus:

```python
def score_match_with_version(
    source_title: str,
    source_artist: str,
    source_album: str | None,
    result_title: str,
    result_artist: str,
    result_album: str,
    result_duration: int | None = None,
    reference_duration: int | None = None,
    all_durations: list[int] | None = None,
) -> int:
    """Score a search result with version preference applied."""
    base = score_match(
        source_title, source_artist, source_album,
        result_title, result_artist, result_album,
    )
    penalty = version_penalty(result_title, result_album)
    dur_pen = duration_penalty(result_duration, reference_duration, all_durations)
    dur_bonus = duration_proximity_bonus(result_duration, reference_duration)
    return max(0, min(100, base - penalty - dur_pen + dur_bonus))
```

- [ ] **Step 6: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add tuneshift/matching.py tests/test_matching.py
git commit -m "feat(tuneshift): add duration proximity bonus to match scoring"
```

---

## Chunk 2: Platform Client Extensions

### Task 4: Add album/artist methods to TidalClient

**Files:**
- Modify: `tuneshift/platforms/tidal.py`
- Modify: `tests/test_tidal_client.py`

- [ ] **Step 1: Write tests for new methods**

In `tests/test_tidal_client.py`, add tests using mocked tidalapi:

```python
def test_search_album(tidal_client, mock_session):
    """search_album returns AlbumResult list."""
    mock_album = MagicMock()
    mock_album.id = 12345
    mock_album.name = "Youthquake"
    mock_album.artist.name = "Dead or Alive"
    mock_album.num_tracks = 10
    mock_album.year = 1985
    mock_session.search.return_value = {"albums": [mock_album]}

    results = tidal_client.search_album("Youthquake Dead or Alive", limit=5)
    assert len(results) == 1
    assert results[0].platform_id == "12345"
    assert results[0].title == "Youthquake"
    assert results[0].artist == "Dead or Alive"


def test_get_album_tracks(tidal_client, mock_session):
    """get_album_tracks returns TrackResult list for all tracks on album."""
    mock_track = MagicMock()
    mock_track.id = 999
    mock_track.name = "You Spin Me Round"
    mock_track.artist.name = "Dead or Alive"
    mock_track.album.name = "Youthquake"
    mock_track.duration = 200
    mock_track.isrc = "GBAYE8500123"
    mock_album = MagicMock()
    mock_album.tracks.return_value = [mock_track]
    mock_session.album.return_value = mock_album

    results = tidal_client.get_album_tracks("12345")
    assert len(results) == 1
    assert results[0].title == "You Spin Me Round"


def test_search_artist(tidal_client, mock_session):
    """search_artist returns ArtistResult list."""
    mock_artist = MagicMock()
    mock_artist.id = 777
    mock_artist.name = "Big Freedia"
    mock_session.search.return_value = {"artists": [mock_artist]}

    results = tidal_client.search_artist("Big Freedia", limit=3)
    assert len(results) == 1
    assert results[0].platform_id == "777"
    assert results[0].name == "Big Freedia"


def test_get_artist_albums(tidal_client, mock_session):
    """get_artist_albums returns AlbumResult list."""
    mock_album = MagicMock()
    mock_album.id = 456
    mock_album.name = "3rd Ward Bounce"
    mock_album.artist.name = "Big Freedia"
    mock_album.num_tracks = 12
    mock_album.year = 2018
    mock_artist = MagicMock()
    mock_artist.get_albums.return_value = [mock_album]
    mock_session.artist.return_value = mock_artist

    results = tidal_client.get_artist_albums("777", limit=20)
    assert len(results) == 1
    assert results[0].title == "3rd Ward Bounce"


def test_get_track(tidal_client, mock_session):
    """get_track returns a single TrackResult by ID."""
    mock_track = MagicMock()
    mock_track.id = 122361821
    mock_track.name = "Louder"
    mock_track.artist.name = "Big Freedia"
    mock_track.album.name = "3rd Ward Bounce"
    mock_track.duration = 195
    mock_track.isrc = "USRC12345678"
    mock_session.track.return_value = mock_track

    result = tidal_client.get_track("122361821")
    assert result is not None
    assert result.title == "Louder"
    assert result.platform_id == "122361821"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_tidal_client.py -v -k "search_album or get_album_tracks or search_artist or get_artist_albums or get_track"`
Expected: FAIL (methods don't exist).

- [ ] **Step 3: Implement the methods in TidalClient**

In `tuneshift/platforms/tidal.py`, add after `search_isrc()`:

```python
def search_album(self, query: str, limit: int = 5) -> list["AlbumResult"]:
    """Search for albums on Tidal."""
    from tuneshift.models import AlbumResult
    self._ensure_session()

    def _search() -> list[AlbumResult]:
        assert self._session is not None
        results = self._session.search(query, models=[tidalapi.album.Album], limit=limit)
        albums = results.get("albums", []) or []
        return [
            AlbumResult(
                platform_id=str(album.id),
                title=album.name or "",
                artist=album.artist.name if getattr(album, "artist", None) else "",
                track_count=int(album.num_tracks or 0),
                release_year=getattr(album, "year", None),
            )
            for album in albums
        ]

    return self._call_with_retry(_search)

def get_album_tracks(self, album_id: str) -> list[TrackResult]:
    """Get all tracks from a Tidal album."""
    self._ensure_session()

    def _get_tracks() -> list[TrackResult]:
        assert self._session is not None
        album = self._session.album(int(album_id))
        return [self._track_to_result(track) for track in album.tracks()]

    return self._call_with_retry(_get_tracks)

def search_artist(self, query: str, limit: int = 3) -> list["ArtistResult"]:
    """Search for artists on Tidal."""
    from tuneshift.models import ArtistResult
    self._ensure_session()

    def _search() -> list[ArtistResult]:
        assert self._session is not None
        results = self._session.search(query, models=[tidalapi.artist.Artist], limit=limit)
        artists = results.get("artists", []) or []
        return [
            ArtistResult(
                platform_id=str(artist.id),
                name=artist.name or "",
            )
            for artist in artists
        ]

    return self._call_with_retry(_search)

def get_artist_albums(self, artist_id: str, limit: int = 20) -> list["AlbumResult"]:
    """Get albums for a Tidal artist."""
    from tuneshift.models import AlbumResult
    self._ensure_session()

    def _get_albums() -> list[AlbumResult]:
        assert self._session is not None
        artist = self._session.artist(int(artist_id))
        albums = artist.get_albums()[:limit]
        return [
            AlbumResult(
                platform_id=str(album.id),
                title=album.name or "",
                artist=album.artist.name if getattr(album, "artist", None) else "",
                track_count=int(album.num_tracks or 0),
                release_year=getattr(album, "year", None),
            )
            for album in albums
        ]

    return self._call_with_retry(_get_albums)

def get_track(self, track_id: str) -> TrackResult | None:
    """Fetch a single track by platform ID. Returns None if not found."""
    self._ensure_session()

    def _get_track() -> TrackResult | None:
        assert self._session is not None
        try:
            track = self._session.track(int(track_id))
        except Exception:
            return None
        return self._track_to_result(track)

    return self._call_with_retry(_get_track)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_tidal_client.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add tuneshift/platforms/tidal.py tests/test_tidal_client.py
git commit -m "feat(tuneshift): add album/artist search and browse to TidalClient"
```

---

### Task 5: Add album/artist methods to YTMusicClient

**Files:**
- Modify: `tuneshift/platforms/ytmusic.py`

- [ ] **Step 1: Implement the methods**

The `ytmusicapi` library supports:
- `ytmusic.search(query, filter="albums")` for album search
- `ytmusic.get_album(browseId)` for album tracks
- `ytmusic.search(query, filter="artists")` for artist search
- `ytmusic.get_artist(channelId)` for artist details including albums

Add after `search_isrc()`:

```python
def search_album(self, query: str, limit: int = 5) -> list["AlbumResult"]:
    """Search for albums on YouTube Music."""
    from tuneshift.models import AlbumResult
    ytmusic = self._ensure_session()
    items = self._call_api(lambda: ytmusic.search(query, filter="albums", limit=limit))
    results: list[AlbumResult] = []
    for item in items:
        browse_id = item.get("browseId", "")
        if not browse_id:
            continue
        artists = item.get("artists", [])
        artist_name = artists[0]["name"] if artists else ""
        results.append(AlbumResult(
            platform_id=browse_id,
            title=item.get("title", ""),
            artist=artist_name,
            track_count=0,
            release_year=_parse_year(item.get("year")),
        ))
    return results

def get_album_tracks(self, album_id: str) -> list[TrackResult]:
    """Get all tracks from a YouTube Music album."""
    ytmusic = self._ensure_session()
    album = self._call_api(lambda: ytmusic.get_album(album_id))
    tracks = album.get("tracks", [])
    return [self._to_result(t) for t in tracks if t.get("videoId")]

def search_artist(self, query: str, limit: int = 3) -> list["ArtistResult"]:
    """Search for artists on YouTube Music."""
    from tuneshift.models import ArtistResult
    ytmusic = self._ensure_session()
    items = self._call_api(lambda: ytmusic.search(query, filter="artists", limit=limit))
    results: list[ArtistResult] = []
    for item in items:
        browse_id = item.get("browseId", "")
        if not browse_id:
            continue
        results.append(ArtistResult(
            platform_id=browse_id,
            name=item.get("artist", item.get("title", "")),
        ))
    return results

def get_artist_albums(self, artist_id: str, limit: int = 20) -> list["AlbumResult"]:
    """Get albums for a YouTube Music artist."""
    from tuneshift.models import AlbumResult
    ytmusic = self._ensure_session()
    artist_data = self._call_api(lambda: ytmusic.get_artist(artist_id))
    albums_section = artist_data.get("albums", {})
    albums = albums_section.get("results", [])[:limit]
    results: list[AlbumResult] = []
    for album in albums:
        browse_id = album.get("browseId", "")
        if not browse_id:
            continue
        results.append(AlbumResult(
            platform_id=browse_id,
            title=album.get("title", ""),
            artist=artist_data.get("name", ""),
            track_count=0,
            release_year=_parse_year(album.get("year")),
        ))
    return results

def get_track(self, track_id: str) -> TrackResult | None:
    """Fetch a single track by video ID. Returns None if not found."""
    ytmusic = self._ensure_session()
    try:
        song = self._call_api(lambda: ytmusic.get_song(track_id))
    except Exception:
        return None
    details = song.get("videoDetails", {})
    if not details:
        return None
    return TrackResult(
        platform_id=track_id,
        title=details.get("title", ""),
        artist=details.get("author", ""),
        album="",
        duration_seconds=int(details.get("lengthSeconds", 0)) or None,
    )
```

Also add a helper at module level:

```python
def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 2: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass (new methods are additive).

- [ ] **Step 3: Commit**

```bash
git add tuneshift/platforms/ytmusic.py
git commit -m "feat(tuneshift): add album/artist search and browse to YTMusicClient"
```

---

## Chunk 3: Multi-Strategy Reconciler

### Task 6: Rewrite reconcile.py with strategy pipeline

**Files:**
- Rewrite: `tuneshift/reconcile.py`
- Modify: `tests/test_reconcile.py`

- [ ] **Step 1: Write tests for multi-strategy behavior**

Add to `tests/test_reconcile.py`:

```python
def test_reconcile_finds_track_via_album_lookup(mock_client, db_with_track):
    """When title+artist search fails, album lookup finds the track."""
    db, track_id = db_with_track
    # title+artist search returns nothing
    mock_client.search_track.return_value = []
    # But album search finds it
    mock_album = AlbumResult(platform_id="alb1", title="3rd Ward Bounce", artist="Big Freedia", track_count=12)
    mock_client.search_album.return_value = [mock_album]
    mock_client.get_album_tracks.return_value = [
        TrackResult(platform_id="t1", title="Louder", artist="Big Freedia", album="3rd Ward Bounce", duration_seconds=195),
    ]

    result = reconcile_track(db, track_id, mock_client, force=True)
    assert result.confidence == "high"
    assert result.platform_track_id == "t1"


def test_reconcile_deduplicates_across_strategies(mock_client, db_with_track):
    """Same platform_id from multiple strategies is only scored once."""
    db, track_id = db_with_track
    same_track = TrackResult(platform_id="t1", title="Louder", artist="Big Freedia", album="3rd Ward Bounce", duration_seconds=195)
    mock_client.search_track.return_value = [same_track]
    mock_client.search_album.return_value = []
    mock_client.search_artist.return_value = []

    result = reconcile_track(db, track_id, mock_client, force=True)
    assert result.platform_track_id == "t1"


def test_reconcile_short_circuits_on_high_confidence(mock_client, db_with_track):
    """Album lookup score >= 90 skips later strategies."""
    db, track_id = db_with_track
    mock_album = AlbumResult(platform_id="alb1", title="3rd Ward Bounce", artist="Big Freedia", track_count=12)
    mock_client.search_album.return_value = [mock_album]
    mock_client.get_album_tracks.return_value = [
        TrackResult(platform_id="t1", title="Louder", artist="Big Freedia", album="3rd Ward Bounce", duration_seconds=195),
    ]
    # search_track should NOT be called due to short-circuit
    mock_client.search_track.side_effect = AssertionError("Should not be called")

    result = reconcile_track(db, track_id, mock_client, force=True)
    assert result.platform_track_id == "t1"
```

- [ ] **Step 2: Run to verify tests fail**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_reconcile.py -v -k "album_lookup or deduplicates or short_circuits"`
Expected: FAIL (old reconciler doesn't support these).

- [ ] **Step 3: Rewrite reconcile.py**

Replace the body of `reconcile_track` (after the cache/mapping checks) with the strategy pipeline. Keep the function signature and `ReconcileResult` unchanged. Key structure:

```python
"""Track reconciliation: match canonical tracks to platform-specific IDs."""
import sys
from dataclasses import dataclass, field

from tuneshift.db import Database
from tuneshift.matching import (
    classify_results,
    duration_proximity_bonus,
    is_remaster,
    normalize_title,
    score_match_with_version,
)
from tuneshift.models import AlbumResult, ArtistResult, PlatformMapping, TrackResult


@dataclass
class ReconcileResult:
    """Result of reconciling a track against a platform."""

    platform_track_id: str = ""
    platform_title: str = ""
    platform_artist: str = ""
    platform_album: str = ""
    score: int = 0
    confidence: str = "not_found"
    is_divergent: bool = False
    divergence_note: str | None = None
    alternatives: list[TrackResult] = field(default_factory=list)
    from_cache: bool = False


# --- Strategy functions ---

def _strategy_album_lookup(track, client) -> list[TrackResult]:
    """Search for the album, get its tracklist."""
    if not track.album:
        return []
    try:
        query = f"{track.album} {track.artist}"
        albums: list[AlbumResult] = client.search_album(query, limit=5)
        # Prefer standard editions
        albums = sorted(albums, key=lambda a: _edition_score(a.title))
        results: list[TrackResult] = []
        for album in albums[:3]:
            tracklist = client.get_album_tracks(album.platform_id)
            results.extend(tracklist)
        return results
    except Exception:
        return []


def _strategy_isrc(track, client) -> list[TrackResult]:
    """Direct ISRC lookup."""
    if not track.isrc:
        return []
    try:
        result = client.search_isrc(track.isrc)
        return [result] if result else []
    except Exception:
        return []


def _strategy_title_artist(track, client) -> list[TrackResult]:
    """Standard title + artist text search."""
    try:
        return client.search_track(f"{track.title} {track.artist}", limit=10)
    except Exception:
        return []


def _strategy_title_only(track, client) -> list[TrackResult]:
    """Broader title-only search."""
    try:
        return client.search_track(track.title, limit=10)
    except Exception:
        return []


def _strategy_album_in_query(track, client) -> list[TrackResult]:
    """Search with title + album name."""
    if not track.album:
        return []
    try:
        return client.search_track(f"{track.title} {track.album}", limit=10)
    except Exception:
        return []


def _strategy_artist_browse(track, client) -> list[TrackResult]:
    """Browse artist discography for the right album."""
    if not track.album:
        return []
    try:
        artists: list[ArtistResult] = client.search_artist(track.artist, limit=3)
        if not artists:
            return []
        albums: list[AlbumResult] = client.get_artist_albums(artists[0].platform_id, limit=20)
        for album in albums:
            if _album_name_matches(album.title, track.album):
                return client.get_album_tracks(album.platform_id)
        return []
    except Exception:
        return []


# Strategy execution order, with short-circuit threshold
_STRATEGIES = [
    (_strategy_album_lookup, 90),    # short-circuit if score >= 90
    (_strategy_isrc, 100),           # ISRC is definitive
    (_strategy_title_artist, 90),
    (_strategy_title_only, None),    # no short-circuit, always continue
    (_strategy_album_in_query, None),
    (_strategy_artist_browse, None),
]


def reconcile_track(
    db: Database,
    track_id: int,
    client: object,
    force: bool = False,
    cached_mapping: PlatformMapping | None = None,
) -> ReconcileResult:
    """Reconcile a canonical track to a platform ID using multi-strategy cascade."""
    track = db.get_track(track_id)
    if track is None:
        return ReconcileResult(confidence="not_found")

    platform_name = client.platform_name

    # Cache/mapping checks (unchanged from original)
    if not force:
        mapping = cached_mapping or db.get_platform_mapping(track_id, platform_name)
        tier, _, _ = db.get_resolution_state(track_id)
        if tier is not None and mapping is not None:
            if mapping.status == "unavailable":
                return ReconcileResult(confidence="not_found", from_cache=True)
            return ReconcileResult(
                platform_track_id=mapping.platform_track_id,
                score=mapping.match_score or 100,
                confidence="high",
                is_divergent=mapping.is_divergent,
                divergence_note=mapping.divergence_note,
                from_cache=True,
            )
        if mapping and mapping.user_approved:
            if mapping.status == "unavailable":
                return ReconcileResult(confidence="not_found", from_cache=True)
            return ReconcileResult(
                platform_track_id=mapping.platform_track_id,
                score=mapping.match_score or 100,
                confidence="high",
                is_divergent=mapping.is_divergent,
                divergence_note=mapping.divergence_note,
                from_cache=True,
            )

    # Multi-strategy candidate collection
    all_candidates: list[TrackResult] = []
    seen_ids: set[str] = set()
    best_so_far = 0

    for strategy_fn, threshold in _STRATEGIES:
        new_candidates = strategy_fn(track, client)
        for c in new_candidates:
            if c.platform_id not in seen_ids:
                seen_ids.add(c.platform_id)
                all_candidates.append(c)

        # Score what we have so far to check short-circuit
        if threshold is not None and all_candidates:
            top_score = _quick_top_score(track, all_candidates)
            if top_score >= threshold:
                best_so_far = top_score
                break

    if not all_candidates:
        return ReconcileResult(confidence="not_found")

    # Score all candidates uniformly
    all_durations = [r.duration_seconds for r in all_candidates if r.duration_seconds]
    scored: list[tuple[int, TrackResult]] = []
    for r in all_candidates:
        s = score_match_with_version(
            track.title, track.artist, track.album,
            r.title, r.artist, r.album,
            result_duration=r.duration_seconds,
            reference_duration=track.duration_seconds,
            all_durations=all_durations,
        )
        # Add duration proximity bonus
        s = min(100, s + duration_proximity_bonus(r.duration_seconds, track.duration_seconds))
        scored.append((s, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    scores = [s for s, _ in scored]
    confidence = classify_results(scores)

    if confidence == "not_found":
        return ReconcileResult(confidence="not_found", alternatives=[r for _, r in scored[:3]])

    best_score, best_result = scored[0]
    is_div = _check_divergence(track.album, best_result.album)
    div_note = f"Version differs: {best_result.album}" if is_div else None

    # ISRC duration sanity check
    if (
        track.duration_seconds
        and best_result.duration_seconds
        and best_result.duration_seconds > track.duration_seconds * 1.6
    ):
        is_div = True
        div_note = (
            f"Duration suspicious: "
            f"{best_result.duration_seconds}s vs expected ~{track.duration_seconds}s"
        )

    return ReconcileResult(
        platform_track_id=best_result.platform_id,
        platform_title=best_result.title,
        platform_artist=best_result.artist,
        platform_album=best_result.album,
        score=best_score,
        confidence=confidence,
        is_divergent=is_div,
        divergence_note=div_note,
        alternatives=[r for _, r in scored[1:4]],
    )


def _quick_top_score(track, candidates: list[TrackResult]) -> int:
    """Quick score check for short-circuit decision."""
    best = 0
    for c in candidates:
        s = score_match_with_version(
            track.title, track.artist, track.album,
            c.title, c.artist, c.album,
            result_duration=c.duration_seconds,
            reference_duration=track.duration_seconds,
        )
        s = min(100, s + duration_proximity_bonus(c.duration_seconds, track.duration_seconds))
        if s > best:
            best = s
    return best


def _edition_score(album_name: str) -> int:
    """Lower score = preferred. Standard editions score 0, deluxe/expanded score higher."""
    name_lower = album_name.lower()
    score = 0
    if "deluxe" in name_lower:
        score += 10
    if "expanded" in name_lower:
        score += 10
    if "anniversary" in name_lower:
        score += 5
    if "special edition" in name_lower:
        score += 5
    if "remaster" in name_lower:
        score += 2
    return score


def _album_name_matches(platform_album: str, canonical_album: str) -> bool:
    """Check if a platform album name matches the canonical album."""
    norm_platform = normalize_title(platform_album)
    norm_canonical = normalize_title(canonical_album)
    if not norm_platform or not norm_canonical:
        return False
    if norm_platform == norm_canonical:
        return True
    from difflib import SequenceMatcher
    return SequenceMatcher(None, norm_platform, norm_canonical).ratio() >= 0.75


def _check_divergence(source_album: str | None, result_album: str) -> bool:
    """Check if the result is a different version/remaster."""
    if not source_album:
        return False
    norm_src = normalize_title(source_album)
    norm_res = normalize_title(result_album)
    if norm_src == norm_res:
        return False
    if is_remaster(result_album) != is_remaster(source_album or ""):
        return True
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, norm_src, norm_res).ratio()
    return ratio < 0.7
```

- [ ] **Step 4: Run reconcile tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_reconcile.py -v`
Expected: All pass (old tests + new tests).

- [ ] **Step 5: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 6: Lint**

Run: `cd tools/tuneshift && .venv/bin/ruff check .`
Expected: No violations.

- [ ] **Step 7: Commit**

```bash
git add tuneshift/reconcile.py tests/test_reconcile.py
git commit -m "feat(tuneshift): multi-strategy reconciler with album lookup and artist browse"
```

---

## Chunk 4: Data Integrity Fixes

### Task 7: Add cascade delete to rm command

**Files:**
- Modify: `tuneshift/db.py`
- Modify: `tuneshift/commands/rm_cmd.py`
- Create: `tests/test_rm_cascade.py`

- [ ] **Step 1: Write failing test for cascade behavior**

Create `tests/test_rm_cascade.py`:

```python
"""Tests for cascade delete behavior in rm command."""
import pytest

from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture
def db_with_pinned_track(tmp_path):
    """Create DB with a playlist containing a pinned track."""
    db = Database(tmp_path / "test.db")
    track = Track(title="Family Tree (Intro)", artist="Ethel Cain", album="Preacher's Daughter")
    track_id = db.add_track(track)
    playlist_id = db.create_playlist("Test Playlist")
    db.add_track_to_playlist(playlist_id, track_id, position=0)
    db.set_pin(playlist_id, track_id, pin_type="opener")
    return db, playlist_id, track_id


def test_remove_track_from_playlist_cleans_pins(db_with_pinned_track):
    """Removing a track also removes its pins."""
    db, playlist_id, track_id = db_with_pinned_track
    db.remove_track_from_playlist(playlist_id, track_id)

    # Track should be gone from playlist
    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 0

    # Pin should also be gone
    pins = db.get_pins(playlist_id)
    assert len(pins) == 0


def test_remove_track_recompacts_positions(tmp_path):
    """After removal, positions are recompacted (no gaps)."""
    db = Database(tmp_path / "test.db")
    playlist_id = db.create_playlist("Test")
    ids = []
    for i, title in enumerate(["A", "B", "C", "D"]):
        t = Track(title=title, artist="Artist")
        tid = db.add_track(t)
        db.add_track_to_playlist(playlist_id, tid, position=i)
        ids.append(tid)

    # Remove track at position 1 ("B")
    db.remove_track_from_playlist(playlist_id, ids[1])

    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 3
    # Positions should be 0, 1, 2 with no gap
    positions = [
        db.conn.execute(
            "SELECT position FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, t.id),
        ).fetchone()[0]
        for t in tracks
    ]
    assert positions == [0, 1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_rm_cascade.py -v`
Expected: FAIL (`remove_track_from_playlist` does not exist).

- [ ] **Step 3: Add `remove_track_from_playlist` to db.py**

In `tuneshift/db.py`, add method to the `Database` class:

```python
def remove_track_from_playlist(self, playlist_id: int, track_id: int) -> None:
    """Remove track from playlist with cascade cleanup of pins and positions."""
    with self.conn:
        self.conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        self.conn.execute(
            "DELETE FROM playlist_pins WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        # Recompact positions (0-indexed, no gaps)
        rows = self.conn.execute(
            "SELECT rowid FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        for idx, (rowid,) in enumerate(rows):
            self.conn.execute(
                "UPDATE playlist_tracks SET position = ? WHERE rowid = ?",
                (idx, rowid),
            )
```

- [ ] **Step 4: Run cascade tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_rm_cascade.py -v`
Expected: All PASS.

- [ ] **Step 5: Update rm_cmd to use new method**

In `tuneshift/commands/rm_cmd.py`, modify `_remove_and_sync()`:

Replace:
```python
db.remove_playlist_track_by_position(playlist.id, position)
```
With:
```python
db.remove_track_from_playlist(playlist.id, track.id)
```

- [ ] **Step 6: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add tuneshift/db.py tuneshift/commands/rm_cmd.py tests/test_rm_cascade.py
git commit -m "fix(tuneshift): cascade delete pins and recompact positions on rm"
```

---

### Task 8: Fix sequencer to accept playlist_id and never drop tracks

**Files:**
- Modify: `tuneshift/sequencer/optimizer.py`
- Modify: `tuneshift/commands/order_cmd.py`
- Modify: `tuneshift/sequencer/__init__.py`
- Create: `tests/test_sequencer_integrity.py`

- [ ] **Step 1: Write failing test for no-drop guarantee**

Create `tests/test_sequencer_integrity.py`:

```python
"""Tests for sequencer data integrity guarantees."""
import pytest

from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.sequencer import sequence_playlist


@pytest.fixture
def db_with_playlist(tmp_path):
    """Create DB with a 5-track playlist, one without energy metadata."""
    db = Database(tmp_path / "test.db")
    playlist_id = db.create_playlist("Test")
    track_ids = []
    for i, (title, energy) in enumerate([
        ("Track A", 0.8),
        ("Track B", 0.5),
        ("Track C", None),  # No metadata
        ("Track D", 0.3),
        ("Track E", 0.9),
    ]):
        t = Track(title=title, artist="Artist", energy=energy, valence=0.5)
        tid = db.add_track(t)
        db.add_track_to_playlist(playlist_id, tid, position=i)
        track_ids.append(tid)
    return db, playlist_id, track_ids


def test_sequence_playlist_never_drops_tracks(db_with_playlist):
    """All tracks appear in output, including those without metadata."""
    db, playlist_id, track_ids = db_with_playlist
    result = sequence_playlist(db, playlist_id, arc="wave")
    assert set(result) == set(track_ids)
    assert len(result) == 5


def test_sequence_playlist_uses_authoritative_list(db_with_playlist):
    """Sequencer loads from DB, ignoring stale caller state."""
    db, playlist_id, track_ids = db_with_playlist
    # Remove track C from playlist
    db.remove_track_from_playlist(playlist_id, track_ids[2])
    # Call with the old (stale) track_ids would have 5, but DB now has 4
    result = sequence_playlist(db, playlist_id, arc="wave")
    assert len(result) == 4
    assert track_ids[2] not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_sequencer_integrity.py -v`
Expected: FAIL (signature mismatch, `sequence_playlist` expects `track_ids` not `playlist_id`).

- [ ] **Step 3: Update sequence_playlist signature**

In `tuneshift/sequencer/optimizer.py`, change `sequence_playlist`:

```python
def sequence_playlist(
    db: Database,
    playlist_id: int,
    arc: str = "wave",
    profile: str = "default",
) -> list[int]:
    """Sequence playlist tracks using tuneshift's database as metadata source.

    Loads the authoritative track list from the DB. Tracks without energy/valence
    metadata are appended at the end (never dropped).
    """
    track_ids = db.get_playlist_track_ids(playlist_id)
    if len(track_ids) <= 1:
        return list(track_ids)

    profile_config = get_profile(profile)
    resolved_arc = arc or profile_config.arc
    metadata_map = get_track_metadata_map(db, track_ids)
    metadata_tracks = [metadata_map[track_id] for track_id in track_ids if track_id in metadata_map]
    missing_ids = [track_id for track_id in track_ids if track_id not in metadata_map]

    if not metadata_tracks:
        return list(track_ids)

    if len(metadata_tracks) == 1:
        return [metadata_tracks[0].track_id] + missing_ids

    # Load pins
    from tuneshift.models import PlaylistPin
    pins: list[PlaylistPin] = db.get_pins(playlist_id)

    ordered_tracks = optimize_sequence(
        metadata_tracks,
        profile_config.weights,
        arc=resolved_arc,
        artist_min_separation=profile_config.artist_min_separation,
        bold_jump_chance=profile_config.bold_jump_chance,
        narrative_mode=profile_config.narrative_mode,
        context_window=profile_config.context_window,
        penalty_overrides=profile_config.penalty_overrides,
        pins=pins,
    )

    result = [track.track_id for track in ordered_tracks] + missing_ids

    if missing_ids:
        print(
            f"  Warning: {len(missing_ids)} track(s) without sequencer metadata appended at end",
            file=__import__("sys").stderr,
        )

    return result
```

- [ ] **Step 4: Add `get_playlist_track_ids` to db.py if missing**

Check if this method exists; if not, add:

```python
def get_playlist_track_ids(self, playlist_id: int) -> list[int]:
    """Return ordered track IDs for a playlist."""
    rows = self.conn.execute(
        "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
        (playlist_id,),
    ).fetchall()
    return [row[0] for row in rows]
```

- [ ] **Step 5: Update order_cmd.py to pass playlist_id**

In `tuneshift/commands/order_cmd.py`, change:

```python
track_ids = [track.id for track in tracks if track.id is not None]
reordered = sequence_playlist(db, track_ids, arc=arc)
```

To:

```python
reordered = sequence_playlist(db, playlist.id, arc=arc)
```

- [ ] **Step 6: Update sequencer/__init__.py re-export if needed**

Check the import path. If `from tuneshift.sequencer import sequence_playlist` works, no change needed. If it imports from a different location, update.

- [ ] **Step 7: Update existing sequencer tests**

Any tests that call `sequence_playlist(db, track_ids, ...)` must be updated to pass `playlist_id` instead. Check `tests/test_optimizer.py` and `tests/test_sequencer.py`.

- [ ] **Step 8: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 9: Commit**

```bash
git add tuneshift/sequencer/optimizer.py tuneshift/sequencer/__init__.py tuneshift/commands/order_cmd.py tuneshift/db.py tests/test_sequencer_integrity.py tests/test_optimizer.py tests/test_sequencer.py
git commit -m "fix(tuneshift): sequencer takes playlist_id, never drops tracks"
```

---

### Task 9: Enable FK pragma and clean orphans

**Files:**
- Modify: `tuneshift/db.py`

- [ ] **Step 1: Add FK pragma to Database.__init__**

Find the line where `self.conn` is created and add immediately after:

```python
self.conn.execute("PRAGMA foreign_keys = ON")
```

- [ ] **Step 2: Add orphan cleanup migration**

In `_migrate_schema()`, add a migration for schema version 5 that cleans orphaned `playlist_pins` and `playlist_tracks` entries:

```python
if current_version < 5:
    # Clean orphaned playlist_pins (track no longer in playlist_tracks)
    self.conn.execute("""
        DELETE FROM playlist_pins
        WHERE NOT EXISTS (
            SELECT 1 FROM playlist_tracks
            WHERE playlist_tracks.playlist_id = playlist_pins.playlist_id
            AND playlist_tracks.track_id = playlist_pins.track_id
        )
    """)
    self.conn.execute("PRAGMA user_version = 5")
```

Update `_SCHEMA_VERSION = 5`.

- [ ] **Step 3: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add tuneshift/db.py
git commit -m "fix(tuneshift): enable FK pragma and clean orphaned pins on migration"
```

---

## Chunk 5: Manual Mapping CLI and Add --replace

### Task 10: Create map/unmap command

**Files:**
- Create: `tuneshift/commands/map_cmd.py`
- Modify: `tuneshift/cli.py`
- Create: `tests/test_map_cmd.py`

- [ ] **Step 1: Write tests**

Create `tests/test_map_cmd.py`:

```python
"""Tests for tuneshift map/unmap commands."""
import argparse
import pytest
from unittest.mock import MagicMock, patch

from tuneshift.commands.map_cmd import handle_map, handle_unmap
from tuneshift.db import Database
from tuneshift.models import Track, TrackResult


@pytest.fixture
def db_with_playlist_and_track(tmp_path):
    db = Database(tmp_path / "test.db")
    track = Track(title="Louder", artist="Big Freedia", album="3rd Ward Bounce")
    track_id = db.add_track(track)
    playlist_id = db.create_playlist("Trans Wrath")
    db.add_track_to_playlist(playlist_id, track_id, position=0)
    return db, playlist_id, track_id


def test_handle_map_stores_approved_mapping(db_with_playlist_and_track):
    """map command stores user-approved platform mapping."""
    db, playlist_id, track_id = db_with_playlist_and_track
    args = argparse.Namespace(
        playlist="Trans Wrath",
        title="Louder",
        tidal="122361821",
        ytmusic=None,
        verify=False,
    )
    result = handle_map(args, db)
    assert result == 0

    mapping = db.get_platform_mapping(track_id, "tidal")
    assert mapping is not None
    assert mapping.platform_track_id == "122361821"
    assert mapping.user_approved is True


def test_handle_map_with_verify_checks_platform(db_with_playlist_and_track):
    """map --verify fetches track from platform before storing."""
    db, playlist_id, track_id = db_with_playlist_and_track
    args = argparse.Namespace(
        playlist="Trans Wrath",
        title="Louder",
        tidal="122361821",
        ytmusic=None,
        verify=True,
    )
    mock_client = MagicMock()
    mock_client.get_track.return_value = TrackResult(
        platform_id="122361821",
        title="Louder (feat. Icona Pop)",
        artist="Big Freedia",
        album="3rd Ward Bounce",
        duration_seconds=195,
    )
    mock_client.load_session.return_value = True

    with patch("tuneshift.commands.map_cmd._load_client", return_value=mock_client):
        result = handle_map(args, db)

    assert result == 0
    mapping = db.get_platform_mapping(track_id, "tidal")
    assert mapping.platform_title == "Louder (feat. Icona Pop)"


def test_handle_map_verify_fails_on_invalid_id(db_with_playlist_and_track):
    """map --verify returns 1 if track not found on platform."""
    db, playlist_id, track_id = db_with_playlist_and_track
    args = argparse.Namespace(
        playlist="Trans Wrath",
        title="Louder",
        tidal="999999999",
        ytmusic=None,
        verify=True,
    )
    mock_client = MagicMock()
    mock_client.get_track.return_value = None
    mock_client.load_session.return_value = True

    with patch("tuneshift.commands.map_cmd._load_client", return_value=mock_client):
        result = handle_map(args, db)

    assert result == 1


def test_handle_unmap_clears_mapping(db_with_playlist_and_track):
    """unmap command removes platform mapping."""
    db, playlist_id, track_id = db_with_playlist_and_track
    # First, set a mapping
    db.set_platform_mapping(track_id, "tidal", "122361821", user_approved=True)

    args = argparse.Namespace(
        playlist="Trans Wrath",
        title="Louder",
        tidal=True,
        ytmusic=False,
    )
    result = handle_unmap(args, db)
    assert result == 0

    mapping = db.get_platform_mapping(track_id, "tidal")
    assert mapping is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_map_cmd.py -v`
Expected: FAIL (module doesn't exist).

- [ ] **Step 3: Create map_cmd.py**

Create `tuneshift/commands/map_cmd.py`:

```python
"""Map command: manually link a track to a platform ID."""
import sys

from tuneshift.db import Database


def handle_map(args, db: Database) -> int:
    """Store a user-approved platform mapping for a track."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    track = _find_track_by_title(db, playlist.id, args.title)
    if not track:
        print(f"Track not found: {args.title}", file=sys.stderr)
        return 1

    platform, platform_id = _extract_platform_args(args)
    if not platform:
        print("Specify --tidal or --ytmusic with a track ID", file=sys.stderr)
        return 1

    platform_title = None
    platform_artist = None
    platform_album = None

    if args.verify:
        from tuneshift.commands.ingest_cmd import _load_client

        client = _load_client(platform)
        if not client or not client.load_session():
            print(f"Not logged in to {platform}. Run: tuneshift login {platform}", file=sys.stderr)
            return 1

        result = client.get_track(platform_id)
        if not result:
            print(f"Track ID {platform_id} not found on {platform}", file=sys.stderr)
            return 1

        platform_title = result.title
        platform_artist = result.artist
        platform_album = result.album
        duration = f" ({result.duration_seconds}s)" if result.duration_seconds else ""
        print(f"Found: {result.title} - {result.artist} [{result.album}]{duration}")

    db.set_platform_mapping(
        track_id=track.id,
        platform=platform,
        platform_track_id=platform_id,
        user_approved=True,
        platform_title=platform_title,
        platform_artist=platform_artist,
        platform_album=platform_album,
        match_score=100,
    )
    print(f'Mapped "{track.title}" -> {platform}:{platform_id}')
    return 0


def handle_unmap(args, db: Database) -> int:
    """Remove a platform mapping, forcing re-reconcile on next sync."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        print(f"Playlist not found: {args.playlist}", file=sys.stderr)
        return 1

    track = _find_track_by_title(db, playlist.id, args.title)
    if not track:
        print(f"Track not found: {args.title}", file=sys.stderr)
        return 1

    platform = _extract_unmap_platform(args)
    if not platform:
        print("Specify --tidal or --ytmusic", file=sys.stderr)
        return 1

    db.delete_platform_mapping(track.id, platform)
    print(f'Unmapped "{track.title}" from {platform}')
    return 0


def _find_track_by_title(db: Database, playlist_id: int, title: str):
    """Find a track in a playlist by title substring match."""
    tracks = db.get_playlist_tracks(playlist_id)
    title_lower = title.lower()
    matches = [t for t in tracks if title_lower in t.title.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        # Prefer exact match
        exact = [t for t in matches if t.title.lower() == title_lower]
        if len(exact) == 1:
            return exact[0]
        print(f"Multiple matches for \"{title}\":", file=sys.stderr)
        for t in matches:
            print(f"  - {t.title} - {t.artist}", file=sys.stderr)
        return None
    return None


def _extract_platform_args(args) -> tuple[str | None, str | None]:
    """Extract platform name and ID from args."""
    if getattr(args, "tidal", None):
        return "tidal", args.tidal
    if getattr(args, "ytmusic", None):
        return "ytmusic", args.ytmusic
    return None, None


def _extract_unmap_platform(args) -> str | None:
    """Extract platform name for unmap."""
    if getattr(args, "tidal", False):
        return "tidal"
    if getattr(args, "ytmusic", False):
        return "ytmusic"
    return None
```

- [ ] **Step 4: Add `set_platform_mapping` and `delete_platform_mapping` to db.py**

If `set_platform_mapping` doesn't exist with the right signature, add/update:

```python
def set_platform_mapping(
    self,
    track_id: int,
    platform: str,
    platform_track_id: str,
    user_approved: bool = False,
    platform_title: str | None = None,
    platform_artist: str | None = None,
    platform_album: str | None = None,
    match_score: int | None = None,
) -> None:
    """Insert or replace a platform track mapping."""
    with self.conn:
        self.conn.execute(
            """INSERT OR REPLACE INTO platform_tracks
               (track_id, platform, platform_track_id, platform_title,
                platform_artist, platform_album, match_score, user_approved)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (track_id, platform, platform_track_id, platform_title,
             platform_artist, platform_album, match_score, int(user_approved)),
        )


def delete_platform_mapping(self, track_id: int, platform: str) -> None:
    """Remove a platform mapping for a track."""
    with self.conn:
        self.conn.execute(
            "DELETE FROM platform_tracks WHERE track_id = ? AND platform = ?",
            (track_id, platform),
        )
```

- [ ] **Step 5: Add map/unmap subparsers to cli.py**

In `tuneshift/cli.py`, after the `pin` subparser:

```python
# map
p_map = sub.add_parser("map", help="Manually map a track to a platform ID")
p_map.add_argument("playlist", help="Playlist name")
p_map.add_argument("title", help="Track title (substring match)")
p_map.add_argument("--tidal", help="Tidal track ID")
p_map.add_argument("--ytmusic", help="YouTube Music video ID")
p_map.add_argument("--verify", action="store_true", help="Verify ID exists on platform")

# unmap
p_unmap = sub.add_parser("unmap", help="Remove a manual platform mapping")
p_unmap.add_argument("playlist", help="Playlist name")
p_unmap.add_argument("title", help="Track title (substring match)")
p_unmap.add_argument("--tidal", action="store_true", help="Remove Tidal mapping")
p_unmap.add_argument("--ytmusic", action="store_true", help="Remove YouTube Music mapping")
```

And in the command dispatch section, add:

```python
elif args.command == "map":
    from tuneshift.commands.map_cmd import handle_map
    return handle_map(args, db)
elif args.command == "unmap":
    from tuneshift.commands.map_cmd import handle_unmap
    return handle_unmap(args, db)
```

- [ ] **Step 6: Run map tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_map_cmd.py -v`
Expected: All PASS.

- [ ] **Step 7: Run full suite + lint**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q && .venv/bin/ruff check .`
Expected: All pass, no lint violations.

- [ ] **Step 8: Commit**

```bash
git add tuneshift/commands/map_cmd.py tuneshift/cli.py tuneshift/db.py tests/test_map_cmd.py
git commit -m "feat(tuneshift): add map/unmap commands for manual platform ID linking"
```

---

### Task 11: Add --replace flag to add command

**Files:**
- Modify: `tuneshift/commands/add_cmd.py`
- Modify: `tuneshift/cli.py`
- Modify: `tests/test_add_cmd.py`

- [ ] **Step 1: Write failing test**

In `tests/test_add_cmd.py`, add:

```python
def test_add_with_replace_swaps_track(tmp_path):
    """--replace removes old track and puts new one at same position."""
    db = Database(tmp_path / "test.db")
    playlist_id = db.create_playlist("Test")
    old_track = Track(title="American Dream", artist="Shea Diamond", album="Seen")
    old_id = db.add_track(old_track)
    db.add_track_to_playlist(playlist_id, old_id, position=0)
    # Add another track after it
    other = Track(title="Other", artist="Other")
    other_id = db.add_track(other)
    db.add_track_to_playlist(playlist_id, other_id, position=1)
    # Pin the old track as opener
    db.set_pin(playlist_id, old_id, pin_type="opener")

    args = argparse.Namespace(
        playlist="Test",
        title="I Am America",
        artist="Shea Diamond",
        album="Seen",
        replace="American Dream",
    )
    result = handle_add(args, db)
    assert result == 0

    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 2
    # New track should be at position 0 (inherited)
    assert tracks[0].title == "I Am America"
    assert tracks[1].title == "Other"

    # Pin should transfer to new track
    pins = db.get_pins(playlist_id)
    assert len(pins) == 1
    assert pins[0].track_id == tracks[0].id
    assert pins[0].pin_type == "opener"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_add_cmd.py -v -k "replace"`
Expected: FAIL.

- [ ] **Step 3: Implement --replace logic in add_cmd.py**

In `handle_add()`, after finding/creating the new track but before adding to playlist:

```python
def handle_add(args, db: Database) -> int:
    """Add a track to a playlist."""
    playlist = db.find_playlist_by_name(args.playlist)
    if not playlist:
        playlist_id = db.create_playlist(args.playlist)
        print(f"Created playlist: {args.playlist}")
    else:
        playlist_id = playlist.id

    # Find or create canonical track
    existing = db.find_track(args.title, args.artist, getattr(args, "album", None))
    if existing:
        track_id = existing.id
    else:
        track = Track(
            title=args.title,
            artist=args.artist,
            album=getattr(args, "album", None),
        )
        track_id = db.add_track(track)

    # Handle --replace: inherit position and pins from old track
    replace_target = getattr(args, "replace", None)
    position = None
    if replace_target:
        tracks = db.get_playlist_tracks(playlist_id)
        target_lower = replace_target.lower()
        old_matches = [t for t in tracks if target_lower in t.title.lower()]
        if not old_matches:
            print(f"Replace target not found: {replace_target}", file=sys.stderr)
            return 1
        old_track = old_matches[0]
        # Get position of old track
        row = db.conn.execute(
            "SELECT position FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, old_track.id),
        ).fetchone()
        position = row[0] if row else None
        # Transfer pins
        db.transfer_pins(playlist_id, old_track.id, track_id)
        # Remove old track (cascade)
        db.remove_track_from_playlist(playlist_id, old_track.id)
        print(f'Replacing "{old_track.title}" with "{args.title}"')

    if position is None:
        tracks = db.get_playlist_tracks(playlist_id)
        position = len(tracks)

    db.add_track_to_playlist(playlist_id, track_id, position)
    print(f'Added "{args.title}" by {args.artist} to "{args.playlist}" at position {position}')

    # Sync to linked platforms
    had_failures = _sync_add_to_platforms(db, playlist_id, track_id, args.title, args.artist)
    return 1 if had_failures else 0
```

- [ ] **Step 4: Add `transfer_pins` to db.py**

```python
def transfer_pins(self, playlist_id: int, from_track_id: int, to_track_id: int) -> None:
    """Transfer all pins from one track to another within a playlist."""
    with self.conn:
        self.conn.execute(
            """UPDATE playlist_pins SET track_id = ?
               WHERE playlist_id = ? AND track_id = ?""",
            (to_track_id, playlist_id, from_track_id),
        )
```

- [ ] **Step 5: Add --replace to CLI parser**

In `tuneshift/cli.py`, add to the `add` subparser:

```python
p_add.add_argument("--replace", help="Title of track to replace (inherits position and pins)")
```

- [ ] **Step 6: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_add_cmd.py -v`
Expected: All pass.

- [ ] **Step 7: Run full suite + lint**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q && .venv/bin/ruff check .`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add tuneshift/commands/add_cmd.py tuneshift/cli.py tuneshift/db.py tests/test_add_cmd.py
git commit -m "feat(tuneshift): add --replace flag to swap tracks with pin inheritance"
```

---

## Final Verification

- [ ] **Run full test suite**: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -v`
- [ ] **Run linter**: `cd tools/tuneshift && .venv/bin/ruff check .`
- [ ] **Verify CLI help shows new commands**: `.venv/bin/python -m tuneshift --help`
- [ ] **Smoke test map command**: `.venv/bin/python -m tuneshift map --help`
- [ ] **Smoke test unmap command**: `.venv/bin/python -m tuneshift unmap --help`
