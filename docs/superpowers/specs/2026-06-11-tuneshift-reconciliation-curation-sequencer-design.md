# TuneShift: Reconciliation v2, Curation Layer, and Sequencer v2

**Date:** 2026-06-11
**Status:** Draft
**Scope:** Three integrated features enhancing track matching, playlist curation, and sequencing intelligence.

## 1. Overview

This spec covers three tightly integrated subsystems that together transform TuneShift from a sync tool into an intelligent playlist curator:

1. **Reconciliation v2**: Album-graph-based track matching with version preference hierarchy.
2. **Curation Layer**: Constraint-aware track selection with gap analysis and fill suggestions.
3. **Sequencer v2**: Full-spectrum weighted transition scoring with narrative intelligence.

### Design Philosophy

**Everything optional, nothing prescriptive.** The more context a user provides (goal, narrative, weights, mood profile, constraints), the smarter the system behaves. If minimal context is given, sensible defaults apply. The system degrades gracefully.

**Exception:** Goal/theme and description are always required for every playlist. Even a simple "chill vibes for reading" is sufficient to anchor curation and sequencing decisions.

## 2. Playlist Identity Model

### 2.1 Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `description` | TEXT | What this playlist is (short, free text) |
| `goal` | TEXT | What it's trying to accomplish, who it's for |

### 2.2 Optional Enrichment Layers

| Field | Type | Description |
|-------|------|-------------|
| `narrative` | TEXT | Structural arc with named sections and position ranges |
| `playlist_type` | TEXT | Preset hint: narrative, mood, spotlight, discovery, workout, custom |
| `weights` | JSON | Sequencing weight vector (dimension -> 0.0-1.0) |
| `mood_profile` | JSON | Target mood, texture, energy characteristics |
| `constraints` | JSON | Duration/count targets, tolerances, hard limits |

### 2.3 Constraint Model

```json
{
  "duration": {
    "target_minutes": 90,
    "tolerance_minutes": 10,
    "hard_limit_minutes": 120
  },
  "track_count": {
    "target": 25,
    "tolerance": 5,
    "hard_limit": null
  }
}
```

Behavior: heavily prefer staying close to target. Tolerance allows slight deviation when narrative cost of cutting/adding is high. Hard limit is never exceeded.

### 2.4 Schema Changes

Migration v7 adds columns to `playlists` and `playlist_tracks`:

```sql
-- playlists table: 'description' already exists (v1 schema), reuse it
ALTER TABLE playlists ADD COLUMN goal TEXT;
ALTER TABLE playlists ADD COLUMN playlist_type TEXT;
ALTER TABLE playlists ADD COLUMN weights TEXT;            -- JSON weight vector
ALTER TABLE playlists ADD COLUMN mood_profile TEXT;       -- JSON mood characteristics
ALTER TABLE playlists ADD COLUMN curation_constraints TEXT; -- JSON duration/count limits
ALTER TABLE playlists ADD COLUMN preferences TEXT;        -- JSON version preference overrides

-- playlist_tracks table: per-track version override
ALTER TABLE playlist_tracks ADD COLUMN version_override TEXT;  -- JSON
```

Existing playlists with only a `narrative` remain valid. The `goal` field will be prompted for on next CLI interaction that would benefit from it (curate, order with narrative weights), not retroactively enforced. The existing `description` column is already in use and sufficient.

**Note:** The `description` column already exists in the current schema (v1). It is reused as-is. Only `goal` is new as a required field going forward.

**Data source clarification:** Classification fields (`lyrical_subject`, `narrator_stance`, `sonic_texture`, `emotional_intensity`, `space`, `groove_feel`, `density`, `era_mood`, `vibes`, `instruments`) are stored in the `tracks.metadata` JSON blob, populated by `tuneshift enrich --classify`. The curation and sequencer layers read these from `TrackMetadata` (see `tuneshift/sequencer/metadata.py`). If classification data is missing for a track, that track scores 0.5 (neutral) on any dimension requiring that data, and the system logs a warning suggesting `enrich --classify`.

## 3. Reconciliation v2: Album Graph

### 3.1 Problem Statement

Current reconciliation uses cascade search strategies (ISRC, title+artist, album lookup, artist browse) with heuristic scoring. Failures occur when:

- Track titles have variant formatting (featured artist placement, subtitles)
- Multiple versions exist (studio, live, remix, remaster, deluxe, explicit/clean)
- Platform search returns wrong version silently (same title, different recording)

### 3.2 Album Graph Model

When reconciling a track that has an album specified:

1. Search for the album on the target platform.
2. Fetch the full album tracklist.
3. Fuzzy-match the target track against all album tracks.
4. If multiple versions of the album exist (standard, deluxe, remaster), fetch all and group into a **version graph**.

The version graph groups recordings by identity (same song, different recording) using:
- MusicBrainz release group (when MBID is resolved)
- Title similarity + duration proximity (when MBID unavailable)
- ISRC family (shared first 5 characters = same recording in different releases)

### 3.3 Version Preference Hierarchy

Three levels, cascading (most specific wins):

| Level | Scope | Example | Storage |
|-------|-------|---------|---------|
| Global | All playlists | "Prefer studio originals over remasters" | `~/.config/tuneshift/preferences.toml` |
| Playlist | Single playlist | "Trans Wrath: prefer explicit versions" | `playlists.preferences` column (JSON) |
| Track | Single track in a playlist | "Use the live version of Black Me Out" | `playlist_tracks.version_override` (JSON) |

### 3.4 Preference Rules

```toml
# Global preferences (~/.config/tuneshift/preferences.toml)
[version_preferences]
prefer = ["studio", "original", "explicit"]
avoid = ["live", "remix", "acoustic", "radio-edit", "clean"]
duration_tolerance_percent = 15  # reject versions >15% longer/shorter than expected

[version_preferences.tiebreak]
# When multiple valid versions remain:
order = ["newest-remaster", "original-release", "compilation"]
```

Playlist-level and track-level overrides use the same schema, stored as JSON.

### 3.5 Enhanced Search Flow

```
reconcile_track(track):
  1. Try ISRC (exact match)
  2. Try album lookup:
     a. Search album on platform
     b. Fetch album tracklist
     c. Fuzzy match track title in album
     d. If multiple albums found (versions), apply preference rules
  3. Try title+artist search:
     a. Get search results
     b. For each result, fetch its album's tracklist (to confirm identity)
     c. Score with version awareness
  4. Try artist browse + album filter
  5. Return best match with version metadata
```

### 3.6 CLI Changes

```bash
tuneshift prefs                          # show global preferences
tuneshift prefs set version.prefer studio,explicit
tuneshift prefs set --playlist "Trans Wrath" version.prefer explicit
tuneshift reconcile "Trans Wrath" --force  # re-reconcile with new prefs
```

## 4. Curation Layer

### 4.1 Position in Workflow

```
add tracks -> set goal/narrative -> CURATE -> sequence -> sync
```

### 4.2 CLI Command

```bash
tuneshift curate <playlist>              # auto-detect mode (trim/fill/analyze)
tuneshift curate <playlist> --trim       # force trim mode
tuneshift curate <playlist> --fill       # force gap analysis + suggestions
tuneshift curate <playlist> --analyze    # report only, no changes
tuneshift curate <playlist> --dry-run    # show what would change
tuneshift curate <playlist> --strategy deep   # force LLM-intensive mode
tuneshift curate <playlist> --strategy quick  # tag-only, no LLM
```

### 4.3 Curation Modes

**Trim** (pool exceeds constraints):
1. Score every track's contribution across all dimensions.
2. Auto-cut: tracks scoring below threshold on narrative fit AND mood contribution AND uniqueness.
3. Present borderlines: tracks with mixed scores (high on one dimension, low on another).
4. Apply cuts after user approval.

**Fill/Gap** (sections are thin or transitions need atmosphere):
1. Analyze each narrative section (or the overall mood profile) for coverage.
2. Identify gaps: missing transitions, thin sections, absent atmospheric connective tissue.
3. Search platforms for candidates matching the gap's requirements.
4. Present suggestions with explanation of why they fit.
5. Add approved suggestions to playlist.

**Analyze** (report only):
1. Score all tracks across dimensions.
2. Report: narrative coverage per section, redundancy clusters, constraint status.
3. Identify strongest and weakest fits.
4. No modifications.

### 4.4 Scoring Dimensions

Each track is scored on its contribution to the playlist across these dimensions:

| Dimension | Description | Source |
|-----------|-------------|--------|
| `narrative_fit` | How well does this track serve its section's stated purpose? | narrative + goal + lyrical_subject + narrator_stance |
| `mood_contribution` | Does this track's mood match what the section needs? | mood_profile + emotional_intensity + vibes + era_mood |
| `sonic_role` | Does this provide needed texture/space/density? | sonic_texture + space + density + instruments |
| `energy_role` | Does this serve the energy curve at its position? | energy + valence + BPM |
| `uniqueness` | Does this bring something no other track provides? | cross-track comparison of all tags |
| `redundancy` | Is another track already serving this exact role better? | similarity to neighbors |

**Curation scorer registry** (analogous to DIMENSION_SCORERS in sequencer):

```python
CURATION_SCORERS: dict[str, Callable[[TrackMetadata, PlaylistContext], float]] = {
    "narrative_fit": score_narrative_fit,
    "mood_contribution": score_mood_contribution,
    "sonic_role": score_sonic_role,
    "energy_role": score_energy_role,
    "uniqueness": score_uniqueness,
    "redundancy": score_redundancy,
}

def score_track_contribution(
    track: TrackMetadata,
    context: PlaylistContext,
    all_tracks: list[TrackMetadata],
) -> dict[str, float]:
    """Score a track's contribution across all curation dimensions.

    Returns dict mapping dimension name -> score (0.0-1.0).
    0.0 = no contribution, 1.0 = essential to playlist.
    """
    scores = {}
    for dimension, scorer in CURATION_SCORERS.items():
        scores[dimension] = scorer(track, context, all_tracks)
    return scores
```

`PlaylistContext` bundles: goal, narrative (parsed sections), mood_profile, constraints, and the full track list for cross-comparison. Each scorer returns 0.0-1.0 where 0.0 means "this track adds nothing on this dimension" and 1.0 means "essential."

### 4.5 Sparse Data Handling

Not all tracks will have full classification data. The curation layer handles this gracefully:

- **No classification at all**: Track scores 0.5 (neutral) on all classification-based dimensions. The curator warns: "N tracks lack classification data. Run `tuneshift enrich --classify` for better results."
- **Partial classification**: Available fields score normally; missing fields score 0.5.
- **No narrative**: Narrative-dependent dimensions (narrative_fit, section assignment) are skipped. Curation uses mood_profile and goal only.
- **No constraints**: Analyze mode only (no trim/fill). Report coverage and balance.
- **No goal**: Curation refuses to run. Goal is required: "Set a goal first: `tuneshift goal <playlist> '<text>'`"

### 4.6 Hybrid Automation

The curator auto-decides (no user input needed) when:
- A track scores below 0.2 on ALL dimensions (obvious misfit)
- A track is a near-duplicate of another with higher scores
- A track exceeds duration hard limit on its own

The curator presents for user decision when:
- A track scores high on one dimension but low on others
- Removing it would leave a gap in a narrative section
- Multiple tracks compete for the same role (user picks)

### 4.7 LLM Integration

For `hybrid` and `deep` strategies, the LLM is invoked for:
- Borderline track assessment ("given this playlist's goal and narrative, should this track stay?")
- Gap identification ("what kind of track is missing between section X and Y?")
- Suggestion generation ("find tracks that would serve as atmospheric transition here")

Lyrics API (Genius/Musixmatch) is optional:
- If `TUNESHIFT_LYRICS_API_KEY` is set, fetch real lyrics for deep analysis.
- If unavailable, the LLM reasons from its training knowledge of well-known songs.
- For obscure tracks without lyrics API: rely on classification tags only.

**LLM error handling:**
- Timeout (>30s): fall back to tag-only scoring for that track/decision.
- Rate limit (429): back off exponentially, retry up to 3 times, then fall back to tags.
- Network error: log warning, fall back to tag-only for this invocation.
- Malformed response: log warning, retry once, then fall back to tags.
- The system must always produce a result even if LLM is completely unavailable. Tag-based scoring is the universal fallback.

### 4.8 Curation Strategy Selection

Per-playlist, stored in `playlist_type` or explicitly in `constraints`:

| Strategy | When auto-selected | Behavior |
|----------|-------------------|----------|
| `hybrid` | Playlist has narrative AND constraints | Tags for scoring, LLM for borderlines |
| `quick` | No narrative, no constraints, or >100 tracks | Tags only, no LLM, fast |
| `deep` | Playlist has narrative AND <30 tracks | Full LLM analysis of every track |
| `manual` | User says `--strategy manual` | Skip curation entirely |

## 5. Sequencer v2: Full-Spectrum Weighted Scoring

### 5.1 Weight Vector Model

Instead of fixed arc strategies, each playlist can declare a weight vector:

```json
{
  "narrative_arc": 0.9,
  "energy_flow": 0.3,
  "mood_continuity": 0.7,
  "sonic_texture": 0.5,
  "lyrical_thread": 0.8,
  "emotional_arc": 0.8,
  "groove_coherence": 0.4,
  "era_mood": 0.3,
  "variety": 0.4,
  "artist_separation": 0.6
}
```

### 5.2 Dimension Definitions

| Dimension | What it scores | Data sources |
|-----------|---------------|--------------|
| `narrative_arc` | Respect chapter boundaries, place tracks by section role | narrative text, chapter_boundaries |
| `energy_flow` | Shape energy curve (wave, build, plateau) | energy, valence, BPM |
| `mood_continuity` | Smooth mood transitions between adjacent tracks | vibes, emotional_intensity, era_mood |
| `sonic_texture` | Texture/space/density transitions feel natural | sonic_texture, space, density, instruments |
| `lyrical_thread` | Lyrical subject continuity or intentional contrast | lyrical_subject, narrator_stance |
| `emotional_arc` | Emotional intensity follows intended curve | emotional_intensity, narrator_stance |
| `groove_coherence` | Rhythmic/groove consistency within sections | groove_feel, BPM, density |
| `era_mood` | Aesthetic/era coherence (or intentional anachronism) | era_mood |
| `variety` | Prevent monotony, introduce surprise/contrast | cross-track similarity |
| `artist_separation` | Spread same-artist tracks apart | artist field |

### 5.3 Named Presets

Presets are starting points, fully overridable per-dimension:

```
narrative-queen:
  narrative_arc=0.9, emotional_arc=0.8, lyrical_thread=0.8,
  mood_continuity=0.7, energy_flow=0.3, sonic_texture=0.5,
  variety=0.4, artist_separation=0.6, groove_coherence=0.4, era_mood=0.3

energy-wave:
  energy_flow=0.9, mood_continuity=0.6, sonic_texture=0.5,
  variety=0.5, artist_separation=0.5, groove_coherence=0.6,
  narrative_arc=0.0, lyrical_thread=0.1, emotional_arc=0.3, era_mood=0.2

mood-bath:
  mood_continuity=0.9, sonic_texture=0.8, groove_coherence=0.7,
  energy_flow=0.3, variety=0.3, emotional_arc=0.5,
  narrative_arc=0.0, lyrical_thread=0.2, artist_separation=0.4, era_mood=0.6

discovery:
  variety=0.9, energy_flow=0.6, sonic_texture=0.5,
  mood_continuity=0.4, artist_separation=0.8, groove_coherence=0.3,
  narrative_arc=0.0, lyrical_thread=0.1, emotional_arc=0.2, era_mood=0.3

workout:
  energy_flow=0.9, groove_coherence=0.8, variety=0.3,
  mood_continuity=0.4, sonic_texture=0.3, artist_separation=0.5,
  narrative_arc=0.0, lyrical_thread=0.0, emotional_arc=0.2, era_mood=0.1
```

### 5.4 Narrative Intelligence (when narrative is present)

When `narrative_arc` weight > 0 and a narrative exists:

1. **Chapter boundaries are hard breaks**: The optimizer does not optimize transitions across section boundaries. Each section is sequenced independently, then concatenated.
2. **Section role inference**: The narrative text tells the system what each section needs (e.g., "EXHALE: the body after the storm" implies low energy, spacious, introspective).
3. **Track-section assignment**: Before sequencing, each track is assigned to its best-fit section based on classification data + narrative section descriptions.
4. **Climax placement**: Sections identified as climax (WRATH, ANTHEM, PEAK) get highest-intensity tracks placed at their structural peak point.

### 5.5 Transition Scoring Formula

The existing `score_pair(a, b, weights)` function in `scoring.py` is extended to accept the full weight vector:

```python
# Registry mapping dimension names to scorer functions
DIMENSION_SCORERS: dict[str, Callable[[TrackMetadata, TrackMetadata], float]] = {
    "narrative_arc": score_narrative_arc,       # new: section boundary respect
    "energy_flow": score_energy_transition,     # existing: energy delta scoring
    "mood_continuity": score_mood_continuity,   # new: vibes + emotional_intensity
    "sonic_texture": score_sonic_texture,       # new: texture/space/density
    "lyrical_thread": score_lyrical_thread,     # new: subject continuity
    "emotional_arc": score_emotional_arc,       # new: intensity curve
    "groove_coherence": score_groove,           # new: BPM + groove_feel
    "era_mood": score_era_mood,                 # new: aesthetic coherence
    "variety": score_variety,                   # new: cross-track diversity
    "artist_separation": score_artist_sep,      # existing: artist spread
}

def score_pair(a: TrackMetadata, b: TrackMetadata, weights: dict[str, float]) -> float:
    """Score the transition quality from track a to track b."""
    total_score = 0.0
    total_weight = 0.0
    for dimension, weight in weights.items():
        if weight > 0 and dimension in DIMENSION_SCORERS:
            dimension_score = DIMENSION_SCORERS[dimension](a, b)
            total_score += weight * dimension_score
            total_weight += weight
    return total_score / total_weight if total_weight > 0 else 0.5
```

Each dimension scorer returns 0.0 (terrible transition) to 1.0 (perfect transition). When a scorer requires classification data that is missing from either track, it returns 0.5 (neutral, no opinion).

### 5.6 Narrative Section Assignment Algorithm

When `narrative_arc` weight > 0 and a narrative with section markers exists:

```python
def assign_tracks_to_sections(
    tracks: list[TrackMetadata],
    sections: list[NarrativeSection],
    goal: str,
) -> dict[int, list[TrackMetadata]]:
    """Assign each track to its best-fit narrative section.

    Algorithm:
    1. Parse narrative sections (already done by _parse_narrative_sections).
    2. For each track, score fitness against each section:
       - section_keywords overlap with track themes/vibes (jaccard similarity)
       - emotional_intensity match with section's implied intensity
       - narrator_stance match with section's implied stance
       - If section has position count constraint, respect capacity
    3. Assign greedily: highest-scoring pairs first, respecting section capacity.
    4. Unassigned tracks go to a 'flex' pool placed where transitions score best.
    """
```

`NarrativeSection` is derived from parsing the narrative text:
```python
@dataclass
class NarrativeSection:
    name: str                    # e.g., "WRATH"
    start_position: int          # 1-indexed start
    end_position: int            # 1-indexed end (inclusive)
    description: str             # e.g., "Fury. Naming the pain directly..."
    implied_intensity: float     # inferred from keywords (fury=0.9, exhale=0.2)
    implied_stance: str | None   # inferred (e.g., "defiant", "vulnerable")
    capacity: int                # end - start + 1 (max tracks for this section)
```

### 5.6 CLI Changes

```bash
tuneshift order <playlist> --weights narrative-queen     # use preset
tuneshift order <playlist> --weights '{"narrative_arc":0.9,"mood_continuity":0.7}'  # custom
tuneshift order <playlist> --dry-run                     # preview without applying
tuneshift weights                                        # list available presets
tuneshift weights set <playlist> narrative-queen         # store preset for playlist
tuneshift weights set <playlist> narrative_arc=0.9 mood_continuity=0.7  # granular
```

## 6. Integration: How the Three Systems Connect

```
         RECONCILIATION v2
         (find correct version)
                |
                v
        [Candidate Pool in DB]
                |
                v
          CURATION LAYER
     (trim to constraints, fill gaps)
     Uses: goal, narrative, mood_profile,
           constraints, classification data
                |
                v
        [Curated Track List]
                |
                v
          SEQUENCER v2
     (order by weighted dimensions)
     Uses: narrative, weights, all
           classification dimensions
                |
                v
         [Final Sequence]
                |
                v
            SYNC TO PLATFORMS
```

### 6.1 Data Flow

1. **Reconciliation** ensures each track in the DB maps to the correct recording on each platform (version-aware).
2. **Curation** takes the full candidate pool + playlist identity (goal, narrative, mood, constraints) and produces a curated subset.
3. **Sequencer** takes the curated list + weights + narrative and produces the final ordering.
4. **Sync** pushes the ordered list to platforms.

### 6.2 Dependency Order for Implementation

1. Playlist identity model (schema, CLI for goal/description/weights) -- foundational
2. Reconciliation v2 (album graph, version preferences) -- independent of 3/4
3. Curation layer (scoring, trim/fill, LLM integration) -- needs 1
4. Sequencer v2 (full-spectrum scoring, weight vector) -- needs 1
5. Integration (wire curate into workflow, connect to sync) -- needs 2, 3, 4

## 7. Non-Goals (explicitly excluded)

- Automatic lyrics fetching without user opt-in (copyright concerns)
- Real-time streaming analysis (this is a batch tool)
- Social/collaborative features (single-user tool)
- Platform-specific recommendation engine integration (we curate, not the platform)
- Grok/xAI integration (blocked permanently; see classifier.py)

## 8. Success Criteria

1. `tuneshift reconcile` finds the correct version of tracks that currently fail (e.g., Left at London, variant titles).
2. `tuneshift curate "Trans Wrath"` correctly identifies which tracks serve the narrative vs. which are filler.
3. `tuneshift order "Trans Wrath" --weights narrative-queen` produces an ordering that respects the 8-section arc without manual intervention.
4. A new playlist with 200 candidate tracks and a 90-minute constraint produces a coherent 90-minute curated playlist in under 2 minutes.
5. Version preferences cascade correctly: global -> playlist -> track override.
