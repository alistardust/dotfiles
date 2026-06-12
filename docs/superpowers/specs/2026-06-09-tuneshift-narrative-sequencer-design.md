# TuneShift Narrative Intelligence Sequencer

**Date:** 2026-06-09
**Scope:** `tools/tuneshift/tuneshift/sequencer/`, `tuneshift/commands/`, `tuneshift/cli.py`
**Status:** Approved

## Problem Statement

The sequencer is fundamentally a sonic similarity engine. It orders tracks by
how well they pair sonically (key, BPM, energy, vibe tags), which produces
smooth DJ-style mixes but not meaningful narrative arcs. The "narrative" arc
shape is an energy-only curve: it controls loudness, not story.

### What It Misses

1. **Lyrical content**: Can't know that two songs tell connected stories.
2. **Emotional intensity vs. energy**: A quiet ballad can be the emotional
   climax. Energy != narrative importance.
3. **Atmospheric texture**: "sparse/mid/dense" doesn't capture warmth vs.
   coldness, intimacy vs. vastness, polished vs. raw.
4. **Transition quality**: Similarity is scored, not complementarity. Great
   transitions are often earned contrasts, not smooth matches.
5. **Duration pacing**: Three 7-minute epics back-to-back exhausts the listener.
6. **Track importance**: Every track is weighted equally. No concept of "this is
   the song the playlist exists for."
7. **Opener/closer selection**: Purely energy math. Great openers are invitations;
   great closers provide resolution.

## Design

### 1. Expanded Classification

**Files:** `tuneshift/sequencer/classifier.py`, `tuneshift/sequencer/metadata.py`

The classification prompt is expanded to capture richer dimensions while
remaining backward-compatible with existing classified tracks. Tracks already
classified keep their existing metadata; re-running `enrich` fills in the new
fields.

#### New Classification Fields

| Field | Type | Purpose |
|-------|------|---------|
| `lyrical_subject` | `str` | What the song is about in 3-8 words |
| `emotional_intensity` | `float (0-1)` | How emotionally heavy/impactful, independent of volume |
| `narrator_stance` | `str` | Perspective: defiant, vulnerable, observational, celebratory, etc. |
| `sonic_texture` | `str` | warm, cold, raw, polished, lo-fi, crystalline |
| `space` | `str` | intimate, room, hall, vast, claustrophobic |
| `groove_feel` | `str` | driving, floating, mechanical, organic, static |
| `opens_with` | `str` | How the track begins sonically (e.g., "synth pad", "drum fill", "silence to vocal") |
| `closes_with` | `str` | How the track ends (e.g., "fade to silence", "hard cut", "sustained chord") |
| `energy_arc_within` | `str` | Internal energy shape: "builds to peak", "steady", "decays", "peak then drop" |

These fields are stored in the existing `tracks.metadata` JSON column. The
`TrackMetadata` dataclass in `metadata.py` gains corresponding attributes.

#### Configurable Classification Model

The classifier model is configurable via (in priority order):

1. `TUNESHIFT_CLASSIFIER_MODEL` environment variable
2. `classifier_model` entry in `schema_meta` table
3. Default: `claude-haiku-4-5-20241022`

```python
class TrackClassifier:
    def __init__(self, client=None, model=None):
        self._model = model or self._resolve_model()

    @staticmethod
    def _resolve_model() -> str:
        env_model = os.environ.get("TUNESHIFT_CLASSIFIER_MODEL")
        if env_model:
            return env_model
        return "claude-haiku-4-5-20241022"
```

The `enrich` command gains `--model` flag to override per-invocation.

#### Expanded Prompt

The classification fields are split into two tiers:

**Tier 1 (LLM-viable, high confidence):** `lyrical_subject`,
`emotional_intensity`, `narrator_stance`, `sonic_texture`, `space`,
`groove_feel`. These can be reliably inferred from the model's training
knowledge of popular music.

**Tier 2 (best-effort, may be inaccurate):** `opens_with`, `closes_with`,
`energy_arc_within`. These require specific recording memory. The classifier
marks these with a confidence field. When confidence is low, the sequencer falls
back to neutral scoring for transition bridge calculations.

Each classification response includes a `confidence` field (0-1) indicating how
well the model knows the specific recording. Tracks with `confidence < 0.5` get
their Tier 2 fields ignored by the sequencer.

```
Classify the following tracks. Return a JSON array with one object per track.

{track_list}

Response format (JSON array):
[
  {
    "title": "Track Title",
    "artist": "Artist Name",
    "themes": ["theme1", "theme2", "theme3"],
    "vibes": ["vibe1", "vibe2", "vibe3"],
    "instruments": ["instrument1", "instrument2"],
    "density": "sparse",
    "era_mood": ["era tag 1"],
    "lyrical_subject": "brief description of what the song is about",
    "emotional_intensity": 0.7,
    "narrator_stance": "defiant",
    "sonic_texture": "polished",
    "space": "vast",
    "groove_feel": "driving",
    "opens_with": "synth pad swell",
    "closes_with": "fade to silence",
    "energy_arc_within": "builds to peak then cuts"
  }
]

Rules:
- themes: 3-5 tags describing what the song is about (genre/style)
- vibes: 3-5 tags describing how it feels (mood/atmosphere)
- instruments: primary instruments heard in the recording
- density: one of "sparse", "mid", "dense"
- era_mood: 1-2 tags capturing production era and cultural moment
- lyrical_subject: 3-8 word description of lyrical content/meaning
- emotional_intensity: 0.0 (lightweight/fun) to 1.0 (devastating/transformative)
  This is NOT energy or loudness. A quiet ballad can be 0.95. A loud banger can be 0.3.
- narrator_stance: the emotional posture (defiant, vulnerable, celebratory,
  observational, pleading, triumphant, introspective, resigned, joyful, bitter)
- sonic_texture: overall production character (warm, cold, raw, polished, lo-fi,
  crystalline, gritty, lush)
- space: the "room" of the recording (intimate, room, hall, vast, claustrophobic,
  open-air)
- groove_feel: rhythmic character (driving, floating, mechanical, organic, static,
  syncopated, martial)
- opens_with: how the track's first 5-10 seconds sound (e.g., "silence to vocal",
  "drum fill", "synth pad", "guitar strum", "spoken word")
- closes_with: how the track's final 5-10 seconds sound (e.g., "fade to silence",
  "hard cut", "sustained chord", "applause", "segue")
- energy_arc_within: the internal energy shape of the track (e.g., "builds to peak",
  "steady", "decays", "peak then drop", "slow burn", "explosive opening then settle")
- Return ONLY the JSON array, no other text
```

### 2. Dual-Axis Narrative Arc

**File:** `tuneshift/sequencer/optimizer.py`

The current single-axis energy curve is replaced with a dual-axis system:

```python
def narrative_targets(position_frac: float) -> tuple[float, float]:
    """Return (energy_target, intensity_target) for a narrative position.

    Energy: loudness/tempo/density curve (physical)
    Intensity: emotional weight curve (psychological)
    """
    energy = _energy_curve(position_frac)
    intensity = _intensity_curve(position_frac)
    return energy, intensity


def _energy_curve(frac: float) -> float:
    """Physical energy target (unchanged from current narrative arc)."""
    if frac < 0.2:
        return 0.3 + 2.0 * frac
    if frac < 0.6:
        return 0.7
    if frac < 0.7:
        return 0.7 - 2.0 * (frac - 0.6)
    if frac < 0.9:
        return 0.5 + 2.5 * (frac - 0.7)
    return 1.0 - 4.0 * (frac - 0.9)


def _intensity_curve(frac: float) -> float:
    """Emotional intensity target independent of energy.

    This allows a quiet, devastating ballad to land at the climax (0.6-0.75).
    """
    if frac < 0.15:
        return 0.4   # scene-setting, invitation
    if frac < 0.35:
        return 0.55  # building, introducing tension
    if frac < 0.55:
        return 0.7   # deepening
    if frac < 0.75:
        return 0.95  # climax region
    if frac < 0.90:
        return 0.6   # aftermath, processing
    return 0.45       # resolution, closure
```

The `_arc_fit_multiplier` uses energy-only (as before). Emotional intensity is
handled by a SEPARATE modifier in `score_candidate()`:

```python
def _arc_fit_multiplier(track, position, total, arc):
    """Energy-only arc fit. Intensity is handled by intensity_arc_modifier."""
    if arc == "free" or total <= 1:
        return 1.0
    target = _target_energy(position / max(total - 1, 1), arc)
    if target is None or track.energy is None:
        return 1.0
    return 1.0 - 0.3 * abs(track.energy - target)
```

Intensity is a separate modifier added to `score_candidate()`:

```python
def intensity_arc_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Reward tracks whose emotional intensity fits the narrative position."""
    if context.total <= 1:
        return 1.0
    frac = context.position / max(context.total - 1, 1)
    intensity_target = _intensity_curve(frac)
    intensity = candidate.emotional_intensity if candidate.emotional_intensity is not None else 0.5
    fit = 1.0 - abs(intensity - intensity_target)
    # Scale: perfect fit = 1.15 bonus, worst fit = 0.85 penalty
    return (0.85 + 0.30 * fit) * strength + 1.0 * (1.0 - strength)
```

This avoids double-counting energy: the arc multiplier handles energy, the
intensity modifier handles emotional weight, and they combine multiplicatively
in `score_candidate()` alongside the other modifiers.

### 3. Playlist Intent Inference

**New file:** `tuneshift/sequencer/intent.py`

Before sequencing, analyze the full track list to determine the playlist's
natural narrative shape. This replaces hardcoded profiles as the primary control
(profiles remain as optional overrides).

**MVP implementation:** Intent inference uses simple heuristics (no LLM call):
- `dominant_themes`: most common tags across all tracks
- `emotional_range`: min/max of `emotional_intensity` values
- `tonal_center`: most common `narrator_stance`
- `sonic_palette`: most common `sonic_texture` values
- `climax_candidates`: top N tracks by `emotional_intensity` (where N = len/15)
- `suggested_arc`: if range is narrow, suggest "wave"; if wide, suggest "narrative"
- `chapter_boundaries`: positions where running theme similarity drops below 0.3
  (computed via sliding window Jaccard over themes+vibes)

This is deterministic and cheap (no API calls). A future enhancement could use
an LLM to analyze the full track list for deeper narrative understanding.

```python
@dataclass
class PlaylistIntent:
    """Inferred narrative intent for a playlist."""

    dominant_themes: list[str]       # most common themes
    emotional_range: tuple[float, float]  # (min, max) emotional intensity
    tonal_center: str                # predominant narrator stance
    sonic_palette: list[str]         # recurring textures
    climax_candidates: list[int]     # track_ids with highest emotional_intensity
    suggested_arc: str               # "narrative", "wave", "descending", etc.
    chapter_boundaries: list[int]    # suggested positions for thematic shifts


def infer_intent(tracks: list[TrackMetadata]) -> PlaylistIntent:
    """Analyze track metadata to determine playlist narrative intent."""
    ...
```

The intent inference:
1. Collects all themes, stances, and textures across tracks
2. Identifies the emotional range (a playlist of all 0.3 intensity is a chill
   session, not a narrative)
3. Finds natural groupings (tracks that share 2+ themes/vibes/textures form
   implicit "chapters")
4. Identifies climax candidates (highest `emotional_intensity` + thematic
   centrality)
5. Suggests an arc shape based on content diversity

The `optimize_sequence` function calls `infer_intent` first, then uses the
result to configure the arc, identify moments, and set chapter boundaries.

### 4. Transition Scoring Overhaul

**File:** `tuneshift/sequencer/scoring.py`

New scoring dimensions added to `score_pair`:

#### Sonic Bridge Scoring

```python
def transition_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score how well track A flows into track B sonically."""
    score = 0.5  # neutral default

    # Sonic bridge: A's ending matches B's opening
    if a.closes_with and b.opens_with:
        if _sonic_elements_compatible(a.closes_with, b.opens_with):
            score += 0.3
        elif _sonic_elements_contrasting(a.closes_with, b.opens_with):
            score += 0.15  # intentional contrast is also good

    # Texture continuity (or intentional shift)
    if a.sonic_texture and b.sonic_texture:
        if a.sonic_texture == b.sonic_texture:
            score += 0.1
        elif _textures_complementary(a.sonic_texture, b.sonic_texture):
            score += 0.05

    # Space transition
    if a.space and b.space:
        if _space_transition_smooth(a.space, b.space):
            score += 0.1

    return min(1.0, score)
```

#### Thematic Connection Scoring

```python
def narrative_connection_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score thematic/lyrical connection between adjacent tracks."""
    score = 0.5

    # Stance progression (defiant -> triumphant = great; celebratory -> bitter = jarring)
    if a.narrator_stance and b.narrator_stance:
        score += _stance_progression_score(a.narrator_stance, b.narrator_stance)

    # Lyrical subject connection
    if a.lyrical_subject and b.lyrical_subject:
        score += _subject_connection_score(a.lyrical_subject, b.lyrical_subject)

    return min(1.0, score)
```

#### Stance Progression Matrix

Certain narrator stance transitions are narratively satisfying:

| From | To | Score |
|------|----|-------|
| vulnerable | defiant | +0.2 (empowerment arc) |
| defiant | triumphant | +0.2 (victory) |
| introspective | celebratory | +0.15 (breakthrough) |
| bitter | resigned | +0.1 (acceptance) |
| joyful | vulnerable | +0.1 (depth shift) |
| triumphant | bitter | -0.1 (tonal whiplash) |
| celebratory | resigned | -0.1 (mood crash) |

These are stored as a configurable matrix, not hardcoded. The matrix is loaded
from `schema_meta` with a default built-in set.

### 5. Chapter Break Intelligence

**File:** `tuneshift/sequencer/modifiers.py`

Replace random bold jumps with intentional chapter breaks.

```python
def chapter_break_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    intent: PlaylistIntent,
    strength: float = 1.0,
) -> float:
    """At chapter boundaries, reward contrast. Between boundaries, reward flow."""
    if context.position in intent.chapter_boundaries:
        # At a chapter break: reward tracks that DIFFER from recent context
        recent_textures = {t.sonic_texture for t in context.recent_tracks if t.sonic_texture}
        recent_stances = {t.narrator_stance for t in context.recent_tracks if t.narrator_stance}

        texture_novel = candidate.sonic_texture not in recent_textures if candidate.sonic_texture else False
        stance_novel = candidate.narrator_stance not in recent_stances if candidate.narrator_stance else False

        novelty_bonus = 0.0
        if texture_novel:
            novelty_bonus += 0.1
        if stance_novel:
            novelty_bonus += 0.1

        return (1.0 + novelty_bonus) * strength + 1.0 * (1.0 - strength)

    return 1.0  # normal flow between chapters
```

The `bold_jump_chance` parameter is retained for non-narrative arcs (wave,
descending, ascending, free) where random variety is appropriate. For narrative
arcs, bold jumps are replaced by intentional chapter breaks. The chapter break
modifier only activates when:
1. Arc is "narrative", AND
2. The track has `narrator_stance` or `sonic_texture` data (new classification)

If a track lacks new classification data, the old bold jump mechanism fires as
fallback (preserving existing behavior for un-enriched playlists).

### 6. Moment System

**Files:** `tuneshift/sequencer/optimizer.py`, `tuneshift/commands/pin_cmd.py`,
`tuneshift/cli.py`

#### Auto-Detection

During intent inference, tracks with `emotional_intensity >= 0.85` and high
thematic overlap with the playlist's dominant themes become auto-detected
moments. The top 1-3 tracks (depending on playlist length) are flagged as
moment candidates.

#### Manual Override

New pin type: `moment`.

```
tuneshift pin "Trans Wrath" --moment "Protest"
```

Stored in `playlist_pins` with `pin_type = "moment"`. Unlike position pins,
moment pins don't specify an index. They specify that this track must be placed
in the climax region (0.55-0.75 of the arc).

#### Placement Logic

```python
def _resolve_moments(
    tracks: list[TrackMetadata],
    intent: PlaylistIntent,
    pins: list[PlaylistPin],
) -> list[int]:
    """Return track_ids that should be placed at climax positions."""
    # Manual moments override auto-detection
    manual = [p.track_id for p in pins if p.pin_type == "moment"]
    if manual:
        return manual

    # Auto-detect from intent
    return intent.climax_candidates[:max(1, len(tracks) // 15)]
```

Moment tracks are treated as position-region pins. They are removed from the
free pool BEFORE the greedy build, and their target positions (within the climax
region 0.55-0.75) are reserved as slots. The greedy builder builds around these
reserved slots, then moments are inserted at their positions. This avoids
displacing optimized transitions.

```python
def _place_moments(
    tracks: list[TrackMetadata],
    moments: list[int],
    total: int,
) -> dict[int, int]:
    """Assign moment tracks to positions in the climax region.

    Returns dict of target_position -> track_id (like position pins).
    """
    if not moments:
        return {}
    climax_start = int(total * 0.55)
    climax_end = int(total * 0.75)
    available_positions = list(range(climax_start, climax_end + 1))
    # Space moments evenly in the climax region
    step = max(1, len(available_positions) // (len(moments) + 1))
    result: dict[int, int] = {}
    for i, track_id in enumerate(moments):
        pos = climax_start + (i + 1) * step
        pos = min(pos, climax_end)
        result[pos] = track_id
    return result
```

These are then handled identically to position pins: removed from free pool,
inserted after greedy build at their reserved indices.

### 7. Duration-Aware Pacing

**File:** `tuneshift/sequencer/modifiers.py`

New modifier that varies ideal track length across the arc:

```python
def duration_pacing_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Reward duration variety and arc-appropriate lengths."""
    if not candidate.duration_ms:
        return 1.0

    frac = context.position / max(context.total - 1, 1)
    candidate_mins = candidate.duration_ms / 60000.0

    # Duration monotony penalty: penalize same-length runs
    recent_durations = [t.duration_ms for t in context.recent_tracks if t.duration_ms]
    if len(recent_durations) >= 3:
        avg_recent_mins = sum(recent_durations) / len(recent_durations) / 60000.0
        if abs(candidate_mins - avg_recent_mins) < 0.4:
            return 0.92 * strength + 1.0 * (1.0 - strength)

    # Arc-aware ideal duration
    if frac < 0.15:
        # Opener region: medium to long (scene-setting)
        ideal_range = (3.0, 5.5)
    elif frac < 0.55:
        # Rising action: progressively shorter
        ideal_range = (2.5, 4.5)
    elif frac < 0.75:
        # Climax: allow longer pieces (the payoff)
        ideal_range = (3.5, 7.0)
    elif frac < 0.90:
        # Falling action: medium
        ideal_range = (3.0, 5.0)
    else:
        # Resolution: medium, breathing room
        ideal_range = (3.0, 5.0)

    if ideal_range[0] <= candidate_mins <= ideal_range[1]:
        return 1.0 + 0.03 * strength  # slight bonus for ideal range
    return 1.0  # no penalty for out-of-range, just no bonus
```

### 8. Opener/Closer Selection Improvement

**File:** `tuneshift/sequencer/optimizer.py`

Replace pure energy math with narrative-aware selection:

```python
def select_opener(tracks: list[TrackMetadata], arc: str) -> TrackMetadata:
    """Select the best opening track for narrative intent."""
    if arc != "narrative":
        # Non-narrative arcs: use energy-based selection (unchanged)
        ...

    scored: list[tuple[float, TrackMetadata]] = []
    for track in tracks:
        energy = track.energy if track.energy is not None else 0.5
        energy_fit = 1.0 - abs(energy - 0.3)  # openers should be moderate

        # Narrative opener qualities
        intensity = track.emotional_intensity if track.emotional_intensity is not None else 0.5
        invitation_score = 1.0 - abs(intensity - 0.4)  # not too heavy, draws you in

        # Atmospheric openers preferred
        texture_bonus = 0.0
        if track.sonic_texture in ("warm", "lush", "lo-fi"):
            texture_bonus = 0.1
        if track.space in ("vast", "intimate"):
            texture_bonus += 0.1

        # Prefer tracks that "opens_with" something evocative
        opening_bonus = 0.0
        if track.opens_with and any(
            word in (track.opens_with or "").lower()
            for word in ("ambient", "pad", "silence", "intro", "spoken", "piano")
        ):
            opening_bonus = 0.1

        total = (
            0.3 * energy_fit
            + 0.3 * invitation_score
            + 0.2 * (texture_bonus + opening_bonus)
            + 0.2 * (1.0 - abs((track.valence or 0.5) - 0.5))
        )
        scored.append((total, track))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]
```

Similar logic for `select_closer`: prefer tracks with resolution/closure in
their narrator stance ("resigned", "triumphant", "peaceful"), lower emotional
intensity (denouement), and endings that feel conclusive ("sustained chord",
"fade to silence").

### 9. Updated Weight System

The scoring dimensions expand from 6 to 9:

```python
NARRATIVE_WEIGHTS: dict[str, float] = {
    "themes": 0.20,
    "energy": 0.12,
    "instrumentation": 0.10,
    "bpm": 0.08,
    "mode": 0.05,
    "key": 0.05,
    "transition": 0.15,      # NEW: sonic bridge scoring
    "narrative": 0.15,        # NEW: thematic connection scoring
    "emotional_arc": 0.10,    # NEW: emotional intensity continuity
}
```

The existing profiles (`psych-journey`, `sunset-chill`, etc.) remain as optional
overrides but are no longer the primary control. The default profile for
narrative arcs uses `NARRATIVE_WEIGHTS`. Non-narrative arcs use the existing
`DEFAULT_WEIGHTS` (which don't include the new dimensions).

### 10. TrackMetadata Expansion

**File:** `tuneshift/sequencer/metadata.py`

Add new fields to `TrackMetadata`:

```python
@dataclass
class TrackMetadata:
    # ... existing fields ...
    emotional_intensity: float | None = None
    lyrical_subject: str | None = None
    narrator_stance: str | None = None
    sonic_texture: str | None = None
    space: str | None = None
    groove_feel: str | None = None
    opens_with: str | None = None
    closes_with: str | None = None
    energy_arc_within: str | None = None
```

The `track_to_metadata` function reads these from `track.metadata` JSON:

```python
def track_to_metadata(track: Track) -> TrackMetadata:
    metadata = track.metadata or {}
    return TrackMetadata(
        # ... existing mappings ...
        emotional_intensity=_float_value(metadata.get("emotional_intensity")),
        lyrical_subject=metadata.get("lyrical_subject"),
        narrator_stance=metadata.get("narrator_stance"),
        sonic_texture=metadata.get("sonic_texture"),
        space=metadata.get("space"),
        groove_feel=metadata.get("groove_feel"),
        opens_with=metadata.get("opens_with"),
        closes_with=metadata.get("closes_with"),
        energy_arc_within=metadata.get("energy_arc_within"),
    )
```

## Backward Compatibility

- Tracks without the new classification fields use `None` defaults.
- Scoring functions fall back to neutral (0.5) when data is missing.
- The expanded classification prompt is a superset of the existing prompt.
- Existing profiles work unchanged; new dimensions are weight-normalized away
  when not present in the profile.
- The `moment` pin type uses the existing `playlist_pins` table (pin_type column).
- No schema migration needed (metadata is JSON in the existing `metadata` column).

## Testing Strategy

| Component | Test Type | Coverage |
|-----------|-----------|----------|
| Expanded classification prompt | Unit | Parse response with new fields |
| Dual-axis arc multiplier | Unit | Parameterized: quiet-intense at climax scores high |
| Transition scoring | Unit | Sonic bridge compatibility, stance progression |
| Chapter break modifier | Unit | Contrast bonus at boundaries, flow between |
| Duration pacing modifier | Unit | Monotony penalty, arc-appropriate lengths |
| Moment detection | Integration | Auto-detect from intent, manual override |
| Narrator stance matrix | Unit | All progressive/regressive pairs |
| Intent inference | Integration | Full playlist analysis produces valid intent |
| End-to-end narrative | Integration | Playlist with known tracks, verify placement |
| Backward compat | Regression | Tracks without new fields still sequence correctly |

## Out of Scope

- Fetching actual lyrics from external APIs (Genius, Musixmatch). The classifier
  works from the model's training knowledge of songs.
- Audio analysis (spectral features, beat detection). Would require audio file
  access or a music analysis API.
- User-configurable stance progression matrix (deferred: hardcode a good default,
  make it easy to override later).
- Spotify-specific sequencer adaptations (Spotify not yet implemented).
