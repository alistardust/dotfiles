# Design Review: TuneShift Reconciliation & Data Integrity Overhaul

**Reviewer:** GitHub Copilot CLI  
**Date:** 2026-06-11  
**Spec:** `/Users/alice.thomas/dotfiles/docs/superpowers/specs/2026-06-09-tuneshift-reconciliation-overhaul-design.md`

---

## Executive Summary

**Verdict: PASS with 2 MINOR concerns and 4 recommendations**

The design is sound, addresses all stated problems, and is technically feasible. The multi-strategy reconciler elegantly solves the "unavailable but exists" problem, and the data integrity fixes close real gaps. Platform client methods are confirmed feasible via API capability checks.

Two minor concerns require clarification before implementation, and four recommendations would improve robustness.

---

## Problem Coverage Analysis

### ✅ All Six Failure Modes Addressed

| Failure Mode | Solution | Status |
|--------------|----------|--------|
| 1. Featured artist mismatch | `_FEAT_RE` normalization in `normalize_title()` | ✅ Complete |
| 2. Search too narrow | Multi-strategy cascade (6 strategies) | ✅ Complete |
| 3. Wrong version selected | Album lookup strategy + existing duration/version penalties | ✅ Complete |
| 4. No escape hatch | `map`/`unmap` CLI commands | ✅ Complete |
| 5. Tracks dropped during reorder | Authoritative DB reload in sequencer | ✅ Complete |
| 6. `rm` doesn't cascade | New `remove_track_from_playlist()` with pin cleanup | ✅ Complete |

---

## MINOR CONCERNS

### 1. Sequencer Authoritative Reload Logic (Migration Step 6)

**File:** `tuneshift/sequencer/optimizer.py:286-298`  
**Issue:** The proposed authoritative reload logic has a chicken-and-egg problem:

```python
def sequence_playlist(db, track_ids, arc="wave", profile="default") -> list[int]:
    # Reload authoritative membership from DB to prevent stale references
    playlist_row = db.conn.execute(
        "SELECT playlist_id FROM playlist_tracks WHERE track_id = ? LIMIT 1",
        (track_ids[0],),
    ).fetchone()
```

**Problem:** If `track_ids[0]` is stale (the track was deleted), the query returns `None` and the reload never happens. The fix needs to work even when *all* caller-provided track_ids are stale.

**Recommendation:** The caller should pass `playlist_id` explicitly, not infer it from track_ids:

```python
def sequence_playlist(db, playlist_id: int, arc="wave", profile="default") -> list[int]:
    # Reload authoritative membership from DB
    track_ids = db.get_playlist_track_ids(playlist_id)
    
    # ... rest of function uses authoritative track_ids ...
```

This requires updating all call sites (likely `commands/order_cmd.py` and auto-reorder paths). The design should acknowledge this caller-side change.

---

### 2. `add --replace` Pin Inheritance Ambiguity (Migration Step 7)

**File:** `tuneshift/commands/add_cmd.py` (proposed)  
**Spec Section:** 4c, line 306-317

**Issue:** The spec says "inherits position and any pins" but doesn't specify what happens if the old track has a `closer` pin and the new position is mid-playlist.

**Example:**
- Playlist has 10 tracks
- Track #10 is pinned as `closer`
- User runs: `tuneshift add MyPlaylist "New Song" "Artist" --replace "Old Closer"`
- Does the new track become the new closer, or does it go to position 10 (breaking the closer invariant)?

**Recommendation:** Clarify the inheritance rules:
- `position` pins: always inherited (unambiguous)
- `anchor` groups: inherited (track stays in its group)
- `opener`: inherited only if old position was index 0
- `closer`: inherited only if old position was last index

Or consider: `--replace` clears all pins from the old track and lets the user re-pin the new one explicitly. This avoids subtle inheritance bugs.

---

## Technical Feasibility

### ✅ Platform Client Methods (Migration Step 1)

**Verified via API inspection:**

| Method | Tidal (`tidalapi`) | YTMusic (`ytmusicapi`) | Implementation Path |
|--------|-------------------|------------------------|---------------------|
| `search_album()` | `session.search(query, models=[Album])` ✅ | `search(query, filter="albums")` ✅ | Trivial wrapper |
| `get_album_tracks()` | `album.tracks()` ✅ | `get_album(album_id)["tracks"]` ✅ | Trivial wrapper |
| `search_artist()` | `session.search(query, models=[Artist])` ✅ | `search(query, filter="artists")` ✅ | Trivial wrapper |
| `get_artist_albums()` | `artist.get_albums()` ✅ | `get_artist(artist_id)["albums"]` ✅ | Trivial wrapper |
| `get_track()` | `session.track(track_id)` ✅ | Requires workaround¹ | Needs care |

¹ **YTMusic `get_track()` note:** ytmusicapi doesn't have a direct `get_track(video_id)` method. Workaround: `search(video_id, limit=1)` or use `get_song(video_id)` (requires browsing endpoint). This is feasible but slightly more complex than Tidal. The design should note this in Section 5.

**Existing precedent:** `tuneshift/platforms/tidal.py:220-240` already has `get_track_metadata()` that calls `session.track()`, so extending to `get_track()` that returns `TrackResult` is a natural refactor.

---

### ✅ Featured Artist Normalization (Migration Step 2)

**File:** `tuneshift/matching.py:17-23`  
**Current:** `normalize_title()` already strips edition parens via `_EDITION_PARENS_RE`.  
**Proposed:** Add `_FEAT_RE` regex and apply before `strip().casefold()`.

**Validation:**
- "Louder (feat. Icona Pop)" → "Louder"
- "Track (ft. Artist)" → "Track"
- "Song (with Friends)" → "Song"
- "Title [Featuring Someone]" → "Title"

The regex pattern `r"\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s+[^\)\]]+[\)\]]"` is correctly greedy within brackets and handles both `()` and `[]` delimiters.

**Edge case to test:** Ensure it doesn't strip legitimate titles like "With or Without You" (no parens, shouldn't match).

---

### ✅ Cascade Delete Implementation (Migration Step 5)

**File:** `tuneshift/db.py:580-591` (current `remove_playlist_track_by_position`)  
**Proposed:** New method `remove_track_from_playlist(playlist_id, track_id)` with three operations in one transaction:

1. `DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?`
2. `DELETE FROM playlist_pins WHERE playlist_id = ? AND track_id = ?`
3. Recompact positions

**Validation:**
- Schema at `db.py:108-116` shows `playlist_pins` has no FK constraint with `ON DELETE CASCADE`, so explicit delete is correct.
- Schema at `db.py:67-72` shows `playlist_tracks` already has FK to tracks and playlists, so enabling `PRAGMA foreign_keys=ON` (already enabled at line 182) won't break this.
- Position recompaction is critical; current code at line 586-590 does this correctly.

**No issues found.** The implementation is sound.

---

## Strategy Cascade Gap Analysis

### ✅ No Critical Gaps

The six-strategy cascade is comprehensive:

1. **Album Lookup** (when album known) → highest precision, catches wrong-version issues
2. **ISRC** → perfect match when available
3. **Title + Artist** → current baseline
4. **Title Only** → broadens net for unusual artists
5. **Album in Query** → alternate search formulation
6. **Artist Browse** → expensive but exhaustive fallback

**Edge cases covered:**
- Missing album field: strategies 2-5 still work
- No ISRC: strategies 1, 3-6 compensate
- Unusual artist name (G.L.O.S.S., Left at London): strategy 4 (title-only) and strategy 6 (browse) compensate
- Multiple versions on same album: tiebreaker at lines 93-97 handles this

**Potential gap (ACCEPTABLE):** A track with a completely wrong title on the platform (e.g., misspelled, different language) won't be found. This is unfixable via automated reconciliation and is the correct use case for the `map` command.

---

## Data Integrity Fixes

### ✅ Foreign Key Enforcement (Migration Step 8)

**File:** `tuneshift/db.py:182`  
**Current state:** `PRAGMA foreign_keys=ON` is already executed in `Database.conn` property.

**Proposed:** "Enable SQLite foreign key enforcement" + migration to clean orphans.

**Issue:** The design says "enable" but it's already enabled. The real work is the orphan cleanup migration.

**Recommendation:** Clarify step 8 as:
- "Add migration to clean orphaned `playlist_pins` and `platform_tracks` rows before FK constraint validation"
- Query: Find pins/mappings referencing deleted tracks, log them, delete them
- This is a one-time data cleanup, not a feature addition

---

### ✅ Sequencer Guarantees

**Spec:** "Tracks without metadata still appear in output" (line 394)  
**Current code:** `optimizer.py:474-475` already appends `missing_ids` to the output.

**The bug is upstream:** The issue isn't that the sequencer drops metadata-less tracks; it's that the caller passes stale `track_ids` (includes deleted track IDs).

**The fix (authoritative reload)** addresses root cause correctly, but see **MINOR CONCERN #1** above for the implementation issue.

---

## Migration Plan Ordering

### ✅ Dependencies Correctly Ordered

| Step | Depends On | Risk | Validation |
|------|-----------|------|------------|
| 1. Platform client methods | None | Low | Can test in isolation, non-breaking |
| 2. Featured artist normalization | None | Low | Pure addition to existing function |
| 3. Multi-strategy reconciler | Step 1 | Medium | Replaces internals of `reconcile_track()` |
| 4. `map`/`unmap` CLI | Step 3 (for verify flag) | Low | New commands, no existing callers |
| 5. Cascade delete | None | Medium | Refactors `rm` command behavior |
| 6. Sequencer reload | None | Medium | Changes `sequence_playlist` signature? |
| 7. `add --replace` | Step 5 (uses cascade delete) | Low | New flag, optional |
| 8. FK pragma + migration | Steps 5-6 (ensure no new orphans) | High | One-way data change |
| 9. Duration proximity bonus | Step 3 (needs multi-strategy results) | Low | Scoring refinement |

**Issue:** Step 6 (sequencer reload) should come *before* step 8 (FK enforcement) to ensure the sequencer doesn't create any new inconsistencies before FK constraints are fully enforced.

**Recommended order:**
1-5 unchanged, then **6 (sequencer), 7 (add --replace), 9 (duration bonus), 8 (FK migration last)**.

---

## Recommendations

### 1. Add Rate Limit Tracking to Reconciler (Section 6)

**Spec line 376-384** mentions rate limiting considerations but doesn't specify implementation.

**Recommendation:** Add a `ReconcileStats` return value or side-channel that tracks:
- API calls made per strategy
- Strategies short-circuited (score >= 90 early exit)
- Total reconcile time

This enables:
- `--dry-run` mode to preview API cost before full sync
- Warning when approaching Tidal/YTM rate limits (e.g., "Artist browse made 50 API calls this run")

### 2. Version Penalty Tweak for Featured Artists

**Current:** `version_penalty()` at `matching.py:154-184` doesn't penalize featured artist versions.  
**After spec:** Featured artists are normalized away, so "Louder" and "Louder (feat. X)" score identically.

**Recommendation:** Keep the normalization, but add a *small* penalty (e.g., -2 points) when the platform track has a featured artist and the canonical doesn't. This ensures that when both the plain and featured versions exist, the plain version is preferred (all else equal).

This is **optional** — the current design is correct, but this refinement mimics user preference for "original" over "featured" when both are available.

### 3. Test Album Lookup Tiebreaker Against Real Data

**Spec lines 93-97** define tiebreaker rules for same-title tracks on the same album.

**Recommendation:** Before merging, test against a known pathological case:
- Tidal album: "Youthquake" by Dead or Alive
- Contains: "You Spin Me Round (Like a Record)" at track 1 (3:19) and track 6 (7:23 extended)

Ensure the album lookup strategy + tiebreaker selects the 3:19 version when canonical duration is ~200 seconds.

### 4. Document `map --verify` Failure Behavior

**Spec lines 211-214:** If `--verify` fails (track ID not found), the command returns 1 and prints an error.

**Recommendation:** Clarify whether the mapping is written to the DB anyway (with `user_approved=True` but stale platform_track_id) or not written at all.

**Suggested behavior:** Don't write the mapping if `--verify` fails. This prevents the DB from storing known-bad mappings.

---

## Contradictions / Unclear Areas

### None Found

The design is internally consistent. All references to other files/functions are accurate based on current codebase state.

---

## Testing Strategy Validation

**Spec Section:** Testing Strategy table (lines 386-397)

**Coverage is appropriate** but missing one critical test:

| Missing Test | Why It Matters |
|--------------|---------------|
| **Cascade delete integration test with sequencer** | Verifies that `rm` + reorder doesn't resurrect deleted tracks (the root bug from failure mode #5) |

**Recommendation:** Add to integration test suite:
1. Create playlist with 5 tracks, pin track 3 as closer
2. Remove track 2 via `rm`
3. Trigger auto-reorder (or manual `order`)
4. Assert: track 2 is not in final sequence, positions are 0-3 (not 0-4 with gap)

---

## Final Checklist

- [x] All stated problems addressed
- [x] No gaps in strategy cascade (acceptable edge case documented)
- [x] Data integrity fixes are sound (with sequencer signature clarification needed)
- [x] Platform client methods feasible (confirmed via API inspection)
- [x] Migration plan mostly correct (step 6/8 swap recommended)
- [x] No contradictions
- [⚠️] Two minor concerns require clarification (sequencer caller changes, pin inheritance)

---

## Summary

**The design is ready for implementation** after addressing the two minor concerns:

1. **Sequencer:** Clarify that `sequence_playlist()` signature changes to accept `playlist_id` directly, and document caller-side updates required.

2. **`add --replace` pins:** Define pin inheritance rules explicitly, especially for `opener`/`closer` edge cases.

All other aspects—strategy cascade, platform feasibility, data integrity fixes, and migration ordering—are sound. The recommendations are enhancements, not blockers.

**Estimated implementation effort:** 3-4 focused work sessions (one per major section: reconciler, CLI commands, DB fixes, testing).
