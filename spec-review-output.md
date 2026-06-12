# Spec Review: TuneShift Reconciliation v2, Curation Layer, and Sequencer v2

## Summary

This is a comprehensive and ambitious spec that attempts to integrate three major subsystems. The design philosophy is sound, and the overall architecture is well-thought-out. However, there are several **blocking issues** that must be resolved before implementation can proceed, along with significant concerns that should be addressed to avoid implementation pitfalls.

---

## Critical Issues (BLOCKERS)

### [BLOCKER] Section 2.4: Incomplete Schema Migration Path

**Issue**: The spec proposes migration v7 adding six new columns to `playlists`, but the current schema is at v6 (per `db.py:_SCHEMA_VERSION = 6`). The spec does not specify:
- How to handle the transition from v6 to v7
- What the default values should be for existing playlists when these columns are added
- How to handle NULL values during the grace period before users provide `description` and `goal`

**Current state**: The existing `playlists` table has `id`, `name`, `description`, `narrative`, `auto_reorder`, `reorder_arc`. The spec proposes adding `goal`, `playlist_type`, `weights`, `mood_profile`, `constraints` but `description` already exists (added in an earlier migration).

**Resolution**: 
1. Clarify that migration v7 adds five new columns (not six), since `description` already exists.
2. Specify the ALTER TABLE statements for the migration:
   ```sql
   ALTER TABLE playlists ADD COLUMN goal TEXT;
   ALTER TABLE playlists ADD COLUMN playlist_type TEXT;
   ALTER TABLE playlists ADD COLUMN weights TEXT;
   ALTER TABLE playlists ADD COLUMN mood_profile TEXT;
   ALTER TABLE playlists ADD COLUMN constraints TEXT;
   ```
3. Define the migration code in `_migrate_schema()` with explicit version check `if current_version < 7:`.
4. Specify how commands should handle playlists where `goal` is NULL: either prompt interactively, reject the operation, or use a default like "general listening".

---

### [BLOCKER] Section 3.4: Preferences Storage Schema Undefined

**Issue**: The spec mentions three storage locations for version preferences:
- Global: `~/.config/tuneshift/preferences.toml`
- Playlist: `playlists.preferences` column (JSON)
- Track: `playlist_tracks.version_override` (JSON)

But:
1. The `playlists.preferences` column does not exist in the schema (Section 2.4 or current schema).
2. The `playlist_tracks.version_override` column does not exist in the current schema.
3. The spec does not define the schema for these preference objects.

**Resolution**:
1. Add to migration v7 (or create v8 if v7 is already crowded):
   ```sql
   ALTER TABLE playlists ADD COLUMN preferences TEXT;  -- JSON version preferences
   ALTER TABLE playlist_tracks ADD COLUMN version_override TEXT;  -- JSON version override
   ```
2. Define the JSON schema for preferences:
   ```json
   {
     "prefer": ["studio", "explicit"],
     "avoid": ["live", "remix"],
     "duration_tolerance_percent": 15,
     "tiebreak": {
       "order": ["newest-remaster", "original-release"]
     }
   }
   ```
3. Clarify how cascade resolution works: if a track-level override exists, use it entirely, or merge with playlist/global preferences?

---

### [BLOCKER] Section 5.2: Missing `DIMENSION_SCORERS` Registry

**Issue**: Section 5.5 references `DIMENSION_SCORERS[dimension](a, b)` as a registry mapping dimension names to scorer functions. This registry does not exist in the current codebase. The existing `scoring.py` has individual functions (`theme_score`, `energy_score`, etc.) but no registry or dispatch mechanism.

**Resolution**:
1. Add to `scoring.py`:
   ```python
   DIMENSION_SCORERS: dict[str, Callable[[TrackMetadata, TrackMetadata], float]] = {
       "narrative_arc": narrative_connection_score,
       "energy_flow": energy_score,
       "mood_continuity": theme_score,
       "sonic_texture": instrumentation_score,
       "lyrical_thread": narrative_connection_score,
       "emotional_arc": emotional_arc_score,
       "groove_coherence": bpm_score,
       "era_mood": theme_score,  # uses era_mood field
       "variety": lambda a, b: 1.0 - theme_score(a, b),
       "artist_separation": lambda a, b: 0.0 if a.artist == b.artist else 1.0,
   }
   ```
2. Some dimensions need new scorer functions (e.g., `sonic_texture` needs a dedicated scorer that looks at `sonic_texture`, `space`, `density` fields).
3. Specify which existing TrackMetadata fields are used for each dimension in the spec (Section 5.2 partially does this, but not completely).

---

### [BLOCKER] Section 5.4: Narrative Section Assignment Algorithm Undefined

**Issue**: The spec states "Before sequencing, each track is assigned to its best-fit section based on classification data + narrative section descriptions" but provides no algorithm for:
- Parsing narrative text to extract section boundaries
- Scoring track-to-section fit
- Handling tracks that don't fit any section well
- What happens if a section has zero assigned tracks

**Resolution**:
1. Define the narrative format. Example:
   ```
   INTRO (0-10%): Setting the stage, low energy introspection
   BUILD (10-40%): Rising tension, defiance emerging
   WRATH (40-60%): Peak intensity, anger and catharsis
   EXHALE (60-100%): Coming down, resolution, reflection
   ```
2. Specify the parser: regex pattern to extract section name, range, and description.
3. Specify the scoring function: LLM prompt that takes (track classification, section description) and returns 0.0-1.0 fit score.
4. Specify the assignment algorithm: greedy (each track goes to highest-scoring section) or global optimization (minimize total misfit).
5. Specify fallback: if narrative parsing fails or a section has zero tracks, fall back to continuous sequencing without hard breaks.

---

### [BLOCKER] Section 4.4: Curation Scoring Data Sources Unspecified

**Issue**: Section 4.4 references classification dimensions like `lyrical_subject`, `narrator_stance`, `sonic_texture`, `space`, `density`, `instruments`, `emotional_intensity`, `vibes`, `era_mood`. The spec does not specify:
- Where this data comes from (are these new columns in `tracks`? JSON fields in `metadata`?)
- The current `tracks` table has only `energy`, `valence`, `tempo`, `key`, `themes` (JSON array)
- How to migrate existing data or backfill these fields

**Resolution**:
1. Define whether these are top-level columns or nested in the existing `metadata` JSON field.
2. If they are in `metadata`, specify the expected JSON structure:
   ```json
   {
     "lyrical_subject": "identity, self-discovery, defiance",
     "narrator_stance": "defiant",
     "sonic_texture": "raw",
     "space": "intimate",
     "density": "dense",
     "instruments": ["electric guitar", "drums", "bass"],
     "emotional_intensity": 0.8,
     "vibes": ["punk", "anthemic"],
     "era_mood": "2010s indie punk"
   }
   ```
3. Reference the existing classifier system (Section 7 mentions "see classifier.py") to clarify that these fields are populated by the classification subsystem.
4. Specify whether curation can proceed gracefully when these fields are missing or incomplete.

---

## Major Concerns (Should be addressed)

### [CONCERN] Section 3.5: Search Flow Step 2b Infeasible

**Issue**: Step 2b states "For each result, fetch its album's tracklist (to confirm identity)". If a title+artist search returns 10 results, this means 10 separate album API calls, which:
- May hit rate limits on platforms like Spotify/Tidal
- Significantly slows down reconciliation
- May not be necessary if ISRC or title+artist scoring is already high confidence

**Suggested resolution**:
- Add a confidence threshold: only fetch album tracklists for results scoring >= 70 on initial title+artist match.
- Or limit album fetches to top 3 results.
- Document the performance vs. accuracy tradeoff.

---

### [CONCERN] Section 3.6: CLI Command Ambiguity

**Issue**: `tuneshift prefs set version.prefer studio,explicit` - is this setting a global preference or does it need `--playlist` to be playlist-scoped? The dotted key notation (`version.prefer`) is inconsistent with the TOML structure shown in 3.4, which uses `[version_preferences]` as a section header and `prefer = [...]` as an array.

**Suggested resolution**:
- Clarify CLI syntax: either use TOML path notation (`tuneshift prefs set version_preferences.prefer studio,explicit`) or nested key notation.
- Show full examples for all three scopes (global, playlist, track).
- Specify how to set track-level overrides via CLI (the spec shows playlist-level but not track-level).

---

### [CONCERN] Section 4.2: `--strategy` Flag Overrides Auto-Selection

**Issue**: Section 4.2 shows `--strategy deep` and `--strategy quick` flags, but Section 4.7 defines auto-selection logic. It's unclear:
- Does `--strategy` override the auto-selection entirely?
- Is `manual` a valid strategy value (it's mentioned in 4.7 but not 4.2)?
- What happens if the user forces `deep` on a 200-track playlist (which auto-selects `quick`)?

**Suggested resolution**:
- Clarify that `--strategy` is an override that bypasses auto-selection.
- Add all valid values to Section 4.2: `hybrid`, `quick`, `deep`, `manual`.
- Warn if the user's choice conflicts with recommendations (e.g., "Warning: deep strategy on 200-track playlist may take 20+ minutes").

---

### [CONCERN] Section 4.5: Auto-Decision Threshold "0.2 on ALL dimensions" Too Strict

**Issue**: "A track scores below 0.2 on ALL dimensions (obvious misfit)" - if a track has 6 dimensions and scores 0.15 on all of them, it's auto-cut. But what if dimension data is sparse? If 4 dimensions are missing data, does it only need to score <0.2 on the 2 available dimensions?

**Suggested resolution**:
- Specify minimum data coverage requirement: "A track must have data for at least 3 dimensions to be auto-decided. If data is too sparse, present for user decision."
- Or use a weighted threshold: sum(score * weight) < 0.2 across all applicable dimensions.

---

### [CONCERN] Section 5.3: Preset Weights Don't Sum to Same Total

**Issue**: The weight presets have different total weights:
- `narrative-queen`: sum ≈ 5.8
- `energy-wave`: sum ≈ 4.2
- `mood-bath`: sum ≈ 5.6

This means the same pairwise score of 0.8 will be weighted differently depending on the preset. Is this intentional (some presets are "stronger" than others), or should weights be normalized?

**Suggested resolution**:
- Clarify whether weights should sum to a constant (e.g., 10.0 or 1.0) or if different totals are acceptable.
- If different totals are intentional, explain the semantic difference (e.g., higher total = more opinionated sequencing, lower total = more tolerant of suboptimal transitions).

---

### [CONCERN] Section 5.4: "Chapter boundaries are hard breaks" Conflicts with Transition Scoring

**Issue**: If sections are sequenced independently and concatenated, the transition score at section boundaries is ignored. This may create jarring transitions between sections (e.g., high-energy track at end of WRATH followed by low-energy track at start of EXHALE, but no transition score to smooth it).

**Suggested resolution**:
- Either: Accept this as a feature (section breaks are meant to be noticeable).
- Or: Add a "boundary transition" mode where the last track of section N and the first track of section N+1 are scored together and potentially swapped to improve the boundary transition.
- Or: Specify that narrative section descriptions should include guidance about the boundary (e.g., "EXHALE opens with space and silence, expecting a hard cut from WRATH's peak").

---

### [CONCERN] Section 6.2: Dependency Order Assumes No Circular Dependencies

**Issue**: The implementation order states "Curation needs 1 (playlist identity model), Sequencer needs 1". But curation uses LLM for gap analysis (4.6) which may want to invoke the sequencer to test if adding a suggested track improves flow. And sequencer may want to invoke curation to trim tracks that hurt the sequence. Is there a risk of circular dependency?

**Suggested resolution**:
- Clarify that curation and sequencing are separate, sequential phases with no back-edges.
- Or allow a "full pipeline" mode where they iterate: curate → sequence → identify weak spots → re-curate.

---

## Minor Suggestions

### [SUGGESTION] Section 2.3: Add Example for `null` Hard Limit

The spec shows `"hard_limit": null` for track_count but doesn't explain what this means. Suggest adding a note: "null means no hard limit, tolerance is advisory only."

---

### [SUGGESTION] Section 3.2: Clarify "Version Graph" Terminology

"Version graph" is introduced but never referenced again. Is this a data structure that's persisted? Or is it ephemeral during reconciliation? Suggest renaming to "version candidates" if it's just a working set.

---

### [SUGGESTION] Section 4.6: Specify LLM Model and Prompt Template

The spec mentions LLM integration but doesn't specify:
- Which model (GPT-4, Claude, etc.)?
- Prompt templates for each use case (borderline assessment, gap identification, suggestion generation)?
- Fallback if API is unavailable?

Given that the codebase already has a classifier (per CLAUDE.md), this should reference or extend that system.

---

### [SUGGESTION] Section 5.6: Add `--weights reset` Command

Users may want to clear custom weights and return to defaults. Suggest adding:
```bash
tuneshift weights reset <playlist>  # clear custom weights, use auto-selection
```

---

### [SUGGESTION] Section 8: Add Regression Test for Existing Behavior

Success criteria 1-5 are all new features. Suggest adding:
6. Existing playlists with v6 schema continue to work without migration until `description`/`goal` are needed.
7. Reconciliation continues to work for tracks that succeeded before (no regressions from album graph changes).

---

## Implementation Feasibility Assessment

**Incremental path**: The spec's suggested implementation order (Section 6.2) is reasonable, but:
- Step 1 (playlist identity model) must include complete migration v7 with all column additions and default handling.
- Step 2 (reconciliation v2) is independent and can proceed in parallel with 3/4 if preferred.
- Steps 3 and 4 (curation and sequencer v2) have a soft dependency: sequencer v2's `score_pair` refactor should happen first, then curation can reuse those scorers.

**Estimated complexity**:
- Reconciliation v2: 3-5 days (album graph, preference cascade, CLI)
- Curation layer: 8-12 days (scoring, LLM integration, trim/fill logic, CLI)
- Sequencer v2: 5-7 days (weight vector, dimension scorers, narrative section breaks, CLI)
- Integration: 2-3 days (wire commands together, end-to-end testing)

**Total**: 18-27 days for a single developer, assuming no major blockers discovered during implementation.

---

## Testability

**Good**: Success criteria in Section 8 are specific and measurable.

**Needs work**:
- Criterion 1: "finds the correct version" - define "correct" (user must manually verify? or compare against a golden dataset?).
- Criterion 2: "correctly identifies which tracks serve the narrative" - this is subjective without ground truth.
- Criterion 4: "produces a coherent 90-minute playlist" - define "coherent" (score threshold? manual listening test?).

**Suggested additions**:
- Add unit test criteria: "Each dimension scorer returns 0.0-1.0 for all valid inputs."
- Add integration test criteria: "Reconciliation succeeds for 95% of tracks in the test dataset (N=500 tracks across 10 albums)."
- Add performance criteria: "Curation of a 200-track playlist completes in <2 minutes on M1 Mac."

---

## Verdict

**CONDITIONAL APPROVAL**: This spec is well-designed and implementable, but the **five blocking issues** must be resolved before proceeding to planning:

1. ✅ Complete the schema migration v7 with explicit ALTER TABLE statements and default value handling.
2. ✅ Define the preferences storage schema (`playlists.preferences`, `playlist_tracks.version_override`).
3. ✅ Implement the `DIMENSION_SCORERS` registry in `scoring.py`.
4. ✅ Define the narrative section assignment algorithm (parser + scorer + assignment).
5. ✅ Specify where curation scoring dimensions are stored (`metadata` JSON structure).

Once these are addressed, the spec will be ready for detailed planning and phased implementation.

---

## Recommended Next Steps

1. Author revises spec to address the 5 blockers.
2. Add a "Data Model" appendix showing the complete post-v7 schema for `playlists`, `tracks`, and `playlist_tracks` tables.
3. Add a "Classification Tags" appendix listing all expected metadata fields and their types/ranges.
4. Add a "CLI Reference" appendix with complete command examples for all new commands.
5. After revision, proceed to planning phase with detailed task breakdown per Section 6.2.
