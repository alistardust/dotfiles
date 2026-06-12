# TuneShift Narrative Intelligence Sequencer - Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the sequencer from a sonic similarity engine into a narrative storytelling engine with richer classification, dual-axis arcs, transition intelligence, moment placement, and duration pacing.

**Architecture:** Expand LLM classification with tiered confidence fields, add intensity as a separate scoring modifier, implement playlist intent inference, add transition/narrative scoring dimensions, replace random bold jumps with chapter breaks for narrative arcs, and add moment pins.

**Tech Stack:** Python 3.10+, SQLite, Anthropic API (configurable model), pytest, ruff

**Spec:** `docs/superpowers/specs/2026-06-09-tuneshift-narrative-sequencer-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `tuneshift/sequencer/metadata.py` | Modify | Add 9 new fields to TrackMetadata, update `track_to_metadata` |
| `tuneshift/sequencer/classifier.py` | Modify | Expanded prompt, configurable model, confidence tiering |
| `tuneshift/sequencer/scoring.py` | Modify | Add `transition_score`, `narrative_connection_score`, `emotional_arc_score` |
| `tuneshift/sequencer/modifiers.py` | Modify | Add `intensity_arc_modifier`, `chapter_break_modifier`, `duration_pacing_modifier` |
| `tuneshift/sequencer/intent.py` | Create | `PlaylistIntent` dataclass, `infer_intent` function |
| `tuneshift/sequencer/optimizer.py` | Modify | Moment placement, narrative opener/closer, intent-driven arc |
| `tuneshift/sequencer/profiles.py` | Modify | Add `NARRATIVE_WEIGHTS`, keep existing profiles |
| `tuneshift/commands/pin_cmd.py` | Modify | Add `--moment` pin type |
| `tuneshift/commands/enrich_cmd.py` | Modify | Add `--model` flag |
| `tuneshift/cli.py` | Modify | Wire `--moment` and `--model` |
| `tests/test_metadata_expanded.py` | Create | New metadata field tests |
| `tests/test_scoring_narrative.py` | Create | Transition and narrative scoring tests |
| `tests/test_modifiers_narrative.py` | Create | Intensity, chapter, duration modifier tests |
| `tests/test_intent.py` | Create | Intent inference tests |
| `tests/test_moment_placement.py` | Create | Moment pin and placement tests |
| `tests/test_classifier_expanded.py` | Create | Expanded prompt parsing tests |

---

## Chunk 1: Metadata Expansion and Classification

### Task 1: Expand TrackMetadata with narrative fields

**Files:**
- Modify: `tuneshift/sequencer/metadata.py`
- Create: `tests/test_metadata_expanded.py`

- [ ] **Step 1: Write test for new metadata fields**

Create `tests/test_metadata_expanded.py`:

```python
"""Tests for expanded TrackMetadata narrative fields."""
import pytest
from tuneshift.models import Track
from tuneshift.sequencer.metadata import track_to_metadata, TrackMetadata


def test_track_to_metadata_reads_narrative_fields():
    """New narrative fields are populated from track.metadata JSON."""
    track = Track(
        id=1, title="Protest", artist="Kim Petras",
        metadata={
            "emotional_intensity": 0.9,
            "lyrical_subject": "refusing to be silenced",
            "narrator_stance": "defiant",
            "sonic_texture": "polished",
            "space": "vast",
            "groove_feel": "driving",
            "opens_with": "synth pad swell",
            "closes_with": "hard cut",
            "energy_arc_within": "builds to peak",
            "classification_confidence": 0.85,
        },
    )
    meta = track_to_metadata(track)
    assert meta.emotional_intensity == 0.9
    assert meta.lyrical_subject == "refusing to be silenced"
    assert meta.narrator_stance == "defiant"
    assert meta.sonic_texture == "polished"
    assert meta.space == "vast"
    assert meta.groove_feel == "driving"
    assert meta.opens_with == "synth pad swell"
    assert meta.closes_with == "hard cut"
    assert meta.energy_arc_within == "builds to peak"
    assert meta.classification_confidence == 0.85


def test_track_to_metadata_missing_narrative_fields():
    """Missing narrative fields default to None."""
    track = Track(id=2, title="Old Track", artist="Artist", metadata={})
    meta = track_to_metadata(track)
    assert meta.emotional_intensity is None
    assert meta.narrator_stance is None
    assert meta.opens_with is None
    assert meta.classification_confidence is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_metadata_expanded.py -v`
Expected: FAIL (fields don't exist on TrackMetadata yet).

- [ ] **Step 3: Add fields to TrackMetadata**

In `tuneshift/sequencer/metadata.py`, add to the `TrackMetadata` dataclass after `source`:

```python
    emotional_intensity: float | None = None
    lyrical_subject: str | None = None
    narrator_stance: str | None = None
    sonic_texture: str | None = None
    space: str | None = None
    groove_feel: str | None = None
    opens_with: str | None = None
    closes_with: str | None = None
    energy_arc_within: str | None = None
    classification_confidence: float | None = None
```

- [ ] **Step 4: Update track_to_metadata**

In `track_to_metadata()`, add after the existing metadata reads:

```python
    emotional_intensity=_float_value(metadata.get("emotional_intensity")),
    lyrical_subject=metadata.get("lyrical_subject"),
    narrator_stance=metadata.get("narrator_stance"),
    sonic_texture=metadata.get("sonic_texture"),
    space=metadata.get("space"),
    groove_feel=metadata.get("groove_feel"),
    opens_with=metadata.get("opens_with"),
    closes_with=metadata.get("closes_with"),
    energy_arc_within=metadata.get("energy_arc_within"),
    classification_confidence=_float_value(metadata.get("classification_confidence")),
```

- [ ] **Step 5: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_metadata_expanded.py -v`
Expected: All PASS.

- [ ] **Step 6: Run full suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass (additive change).

- [ ] **Step 7: Commit**

```bash
git add tuneshift/sequencer/metadata.py tests/test_metadata_expanded.py
git commit -m "feat(tuneshift): expand TrackMetadata with narrative intelligence fields"
```

---

### Task 2: Expand classifier prompt and make model configurable

**Files:**
- Modify: `tuneshift/sequencer/classifier.py`
- Modify: `tuneshift/commands/enrich_cmd.py`
- Modify: `tuneshift/cli.py`
- Create: `tests/test_classifier_expanded.py`

- [ ] **Step 1: Write tests for expanded classification parsing**

Create `tests/test_classifier_expanded.py`:

```python
"""Tests for expanded classifier prompt and response parsing."""
import json
import pytest
from tuneshift.sequencer.classifier import parse_classification_response, build_classification_prompt


def test_parse_expanded_response():
    """Parser handles new narrative fields in JSON response."""
    response = json.dumps([{
        "title": "Protest",
        "artist": "Kim Petras",
        "themes": ["empowerment", "identity"],
        "vibes": ["anthemic", "dark"],
        "instruments": ["synth", "drums"],
        "density": "dense",
        "era_mood": ["2020s pop"],
        "lyrical_subject": "trans defiance",
        "emotional_intensity": 0.9,
        "narrator_stance": "defiant",
        "sonic_texture": "polished",
        "space": "vast",
        "groove_feel": "driving",
        "opens_with": "synth pad",
        "closes_with": "hard cut",
        "energy_arc_within": "builds to peak",
        "confidence": 0.85,
    }])
    results = parse_classification_response(response)
    assert len(results) == 1
    assert results[0]["emotional_intensity"] == 0.9
    assert results[0]["narrator_stance"] == "defiant"
    assert results[0]["confidence"] == 0.85


def test_parse_legacy_response_still_works():
    """Old-format responses (without new fields) still parse correctly."""
    response = json.dumps([{
        "title": "Old Song",
        "artist": "Artist",
        "themes": ["rock"],
        "vibes": ["energetic"],
        "instruments": ["guitar"],
        "density": "mid",
        "era_mood": ["1970s rock"],
    }])
    results = parse_classification_response(response)
    assert len(results) == 1
    assert "emotional_intensity" not in results[0]


def test_build_prompt_includes_narrative_fields():
    """Expanded prompt mentions all new classification fields."""
    tracks = [{"title": "Test", "artist": "Artist"}]
    prompt = build_classification_prompt(tracks)
    assert "emotional_intensity" in prompt
    assert "narrator_stance" in prompt
    assert "sonic_texture" in prompt
    assert "opens_with" in prompt
    assert "confidence" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_classifier_expanded.py -v`
Expected: Some FAIL (prompt doesn't include new fields yet).

- [ ] **Step 3: Update classification prompt**

In `tuneshift/sequencer/classifier.py`, replace `_CLASSIFICATION_PROMPT` with the expanded version from the spec. Key additions:
- Add all new fields to the JSON schema example
- Add rules for each new field
- Add `confidence` field (0-1) for how well the model knows the recording
- Split rules into Tier 1 (always reliable) and Tier 2 (best-effort)

- [ ] **Step 4: Make model configurable**

In `TrackClassifier.__init__`:

```python
def __init__(self, client=None, model=None):
    self._client = client if client is not None else build_default_client()
    self._model = model or self._resolve_model()

@staticmethod
def _resolve_model() -> str:
    env_model = os.environ.get("TUNESHIFT_CLASSIFIER_MODEL")
    if env_model:
        return env_model
    return "claude-haiku-4-5-20241022"
```

- [ ] **Step 5: Add --model to enrich command**

In `tuneshift/commands/enrich_cmd.py`, pass `model=args.model` to `TrackClassifier()`.
In `tuneshift/cli.py`, add `--model` flag to the enrich subparser.

- [ ] **Step 6: Run all tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add tuneshift/sequencer/classifier.py tuneshift/commands/enrich_cmd.py tuneshift/cli.py tests/test_classifier_expanded.py
git commit -m "feat(tuneshift): expand classifier with narrative fields and configurable model"
```

---

## Chunk 2: New Scoring Dimensions

### Task 3: Add transition and narrative connection scoring

**Files:**
- Modify: `tuneshift/sequencer/scoring.py`
- Create: `tests/test_scoring_narrative.py`

- [ ] **Step 1: Write tests**

Create `tests/test_scoring_narrative.py`:

```python
"""Tests for transition and narrative connection scoring."""
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.scoring import transition_score, narrative_connection_score


@pytest.fixture
def track_a():
    return TrackMetadata(
        track_id=1, title="Song A", artist="Artist",
        closes_with="fade to silence", sonic_texture="warm", space="intimate",
        narrator_stance="vulnerable", lyrical_subject="heartbreak",
    )


@pytest.fixture
def track_b_bridge():
    """Track that bridges well from track_a (silence -> silence, warm -> warm)."""
    return TrackMetadata(
        track_id=2, title="Song B", artist="Artist 2",
        opens_with="silence to vocal", sonic_texture="warm", space="intimate",
        narrator_stance="defiant", lyrical_subject="self-acceptance",
    )


@pytest.fixture
def track_c_contrast():
    """Track that contrasts heavily with track_a."""
    return TrackMetadata(
        track_id=3, title="Song C", artist="Artist 3",
        opens_with="drum fill explosion", sonic_texture="gritty", space="vast",
        narrator_stance="triumphant", lyrical_subject="victory",
    )


def test_transition_score_sonic_bridge(track_a, track_b_bridge):
    """Matching close/open gives a high transition score."""
    score = transition_score(track_a, track_b_bridge)
    assert score > 0.7


def test_transition_score_no_data():
    """Missing transition data gives neutral score."""
    a = TrackMetadata(track_id=1, title="A", artist="X")
    b = TrackMetadata(track_id=2, title="B", artist="Y")
    score = transition_score(a, b)
    assert score == 0.5


def test_narrative_connection_empowerment_arc(track_a, track_b_bridge):
    """vulnerable -> defiant is a strong narrative progression."""
    score = narrative_connection_score(track_a, track_b_bridge)
    assert score > 0.6


def test_narrative_connection_whiplash(track_b_bridge, track_c_contrast):
    """Certain stance transitions are jarring."""
    # This tests that the scoring doesn't penalize all contrast
    # (defiant -> triumphant should actually be positive)
    score = narrative_connection_score(track_b_bridge, track_c_contrast)
    assert score >= 0.5  # defiant -> triumphant is progressive
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_scoring_narrative.py -v`
Expected: FAIL (functions don't exist).

- [ ] **Step 3: Implement transition_score**

In `tuneshift/sequencer/scoring.py`, add:

```python
_SONIC_BRIDGE_PAIRS = {
    # A closes_with -> B opens_with: compatible pairs
    ("fade to silence", "silence to vocal"),
    ("sustained chord", "pad"),
    ("sustained chord", "synth pad"),
    ("fade to silence", "ambient"),
    ("hard cut", "drum fill"),
    ("hard cut", "explosion"),
    ("piano", "piano"),
    ("guitar strum", "guitar"),
}

_COMPLEMENTARY_TEXTURES = {
    ("warm", "lush"), ("raw", "gritty"), ("polished", "crystalline"),
    ("lo-fi", "warm"), ("cold", "crystalline"),
}

_SMOOTH_SPACE_TRANSITIONS = {
    ("intimate", "intimate"), ("intimate", "room"), ("room", "hall"),
    ("hall", "vast"), ("vast", "vast"), ("room", "room"),
}


def transition_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score how well track A flows into track B sonically."""
    score = 0.5

    if a.closes_with and b.opens_with:
        a_close = a.closes_with.lower()
        b_open = b.opens_with.lower()
        # Check for sonic bridge
        for close_kw, open_kw in _SONIC_BRIDGE_PAIRS:
            if close_kw in a_close and open_kw in b_open:
                score += 0.3
                break
        else:
            # Intentional contrast also has value
            if ("silence" in a_close and "explosion" in b_open) or \
               ("silence" in a_close and "drum" in b_open):
                score += 0.15

    if a.sonic_texture and b.sonic_texture:
        if a.sonic_texture == b.sonic_texture:
            score += 0.1
        elif (a.sonic_texture, b.sonic_texture) in _COMPLEMENTARY_TEXTURES or \
             (b.sonic_texture, a.sonic_texture) in _COMPLEMENTARY_TEXTURES:
            score += 0.05

    if a.space and b.space:
        if (a.space, b.space) in _SMOOTH_SPACE_TRANSITIONS or \
           (b.space, a.space) in _SMOOTH_SPACE_TRANSITIONS:
            score += 0.1

    return min(1.0, score)
```

- [ ] **Step 4: Implement narrative_connection_score**

```python
_STANCE_PROGRESSION = {
    # (from, to): bonus/penalty
    ("vulnerable", "defiant"): 0.2,
    ("defiant", "triumphant"): 0.2,
    ("introspective", "celebratory"): 0.15,
    ("introspective", "defiant"): 0.15,
    ("bitter", "resigned"): 0.1,
    ("joyful", "vulnerable"): 0.1,
    ("vulnerable", "introspective"): 0.1,
    ("resigned", "joyful"): 0.15,
    ("triumphant", "bitter"): -0.1,
    ("celebratory", "resigned"): -0.1,
    ("joyful", "bitter"): -0.1,
}


def narrative_connection_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score thematic/lyrical connection between adjacent tracks."""
    score = 0.5

    if a.narrator_stance and b.narrator_stance:
        pair = (a.narrator_stance, b.narrator_stance)
        progression = _STANCE_PROGRESSION.get(pair, 0.0)
        score += progression

    if a.lyrical_subject and b.lyrical_subject:
        # Simple keyword overlap for subject connection
        a_words = set(a.lyrical_subject.lower().split())
        b_words = set(b.lyrical_subject.lower().split())
        overlap = len(a_words & b_words)
        if overlap > 0:
            score += min(0.15, overlap * 0.05)

    return max(0.0, min(1.0, score))
```

- [ ] **Step 5: Add emotional_arc_score function**

```python
def emotional_arc_score(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score emotional intensity continuity (avoid jarring jumps)."""
    if a.emotional_intensity is None or b.emotional_intensity is None:
        return 0.5
    delta = abs(a.emotional_intensity - b.emotional_intensity)
    # Small changes (< 0.2) are ideal, large jumps penalized
    if delta < 0.2:
        return 0.9
    if delta < 0.4:
        return 0.6
    return 0.3
```

- [ ] **Step 6: Integrate into score_pair**

Update `score_pair` to include new dimensions when data is available:

```python
def _has_dimension_data(track: TrackMetadata, dimension: str) -> bool:
    # ... existing checks ...
    if dimension == "transition":
        return track.opens_with is not None or track.closes_with is not None
    if dimension == "narrative":
        return track.narrator_stance is not None
    if dimension == "emotional_arc":
        return track.emotional_intensity is not None
    return False
```

And in the scoring dispatch:
```python
        elif dimension == "transition":
            score += weight * transition_score(a, b)
        elif dimension == "narrative":
            score += weight * narrative_connection_score(a, b)
        elif dimension == "emotional_arc":
            score += weight * emotional_arc_score(a, b)
```

- [ ] **Step 7: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_scoring_narrative.py -v`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add tuneshift/sequencer/scoring.py tests/test_scoring_narrative.py
git commit -m "feat(tuneshift): add transition, narrative, and emotional arc scoring dimensions"
```

---

## Chunk 3: Modifiers and Intent Inference

### Task 4: Add intensity arc modifier, chapter breaks, and duration pacing

**Files:**
- Modify: `tuneshift/sequencer/modifiers.py`
- Create: `tests/test_modifiers_narrative.py`

- [ ] **Step 1: Write tests**

Create `tests/test_modifiers_narrative.py`:

```python
"""Tests for narrative sequencer modifiers."""
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.modifiers import (
    SequenceContext, intensity_arc_modifier, chapter_break_modifier,
    duration_pacing_modifier,
)
from tuneshift.sequencer.intent import PlaylistIntent


def _make_track(emotional_intensity=0.5, duration_ms=240000, **kwargs):
    return TrackMetadata(
        track_id=1, title="Test", artist="A",
        emotional_intensity=emotional_intensity,
        duration_ms=duration_ms, **kwargs,
    )


def test_intensity_modifier_climax_rewards_intense():
    """High-intensity track at climax position gets bonus."""
    ctx = SequenceContext(position=13, total=20)  # 0.68 = climax region
    track = _make_track(emotional_intensity=0.95)
    result = intensity_arc_modifier(track, ctx)
    assert result > 1.0  # bonus


def test_intensity_modifier_climax_penalizes_lightweight():
    """Low-intensity track at climax position gets penalty."""
    ctx = SequenceContext(position=13, total=20)
    track = _make_track(emotional_intensity=0.2)
    result = intensity_arc_modifier(track, ctx)
    assert result < 1.0  # penalty


def test_intensity_modifier_opening_rewards_moderate():
    """Moderate intensity at opening gets bonus."""
    ctx = SequenceContext(position=1, total=20)  # 0.05 = opening
    track = _make_track(emotional_intensity=0.4)
    result = intensity_arc_modifier(track, ctx)
    assert result >= 1.0


def test_duration_pacing_penalizes_monotony():
    """Same-length tracks in succession get penalized."""
    ctx = SequenceContext(position=5, total=20)
    # Fill recent with 4-minute tracks
    for _ in range(3):
        ctx.advance(_make_track(duration_ms=240000))
    track = _make_track(duration_ms=242000)  # almost same length
    result = duration_pacing_modifier(track, ctx)
    assert result < 1.0


def test_duration_pacing_no_penalty_for_variety():
    """Different-length track after a run is not penalized."""
    ctx = SequenceContext(position=5, total=20)
    for _ in range(3):
        ctx.advance(_make_track(duration_ms=240000))
    track = _make_track(duration_ms=360000)  # 6 minutes vs 4
    result = duration_pacing_modifier(track, ctx)
    assert result >= 1.0


def test_chapter_break_rewards_contrast():
    """At a chapter boundary, novel texture/stance gets bonus."""
    intent = PlaylistIntent(
        dominant_themes=[], emotional_range=(0.3, 0.9),
        tonal_center="defiant", sonic_palette=["warm"],
        climax_candidates=[], suggested_arc="narrative",
        chapter_boundaries=[5],
    )
    ctx = SequenceContext(position=5, total=20)
    # Fill recent with "warm" textured tracks
    for _ in range(3):
        ctx.advance(_make_track(sonic_texture="warm", narrator_stance="vulnerable"))
    # Candidate has different texture
    track = _make_track(sonic_texture="gritty", narrator_stance="defiant")
    result = chapter_break_modifier(track, ctx, intent)
    assert result > 1.0
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_modifiers_narrative.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement intensity_arc_modifier**

In `tuneshift/sequencer/modifiers.py`, add:

```python
def _intensity_curve(frac: float) -> float:
    """Emotional intensity target independent of energy."""
    if frac < 0.15:
        return 0.4
    if frac < 0.35:
        return 0.55
    if frac < 0.55:
        return 0.7
    if frac < 0.75:
        return 0.95
    if frac < 0.90:
        return 0.6
    return 0.45


def intensity_arc_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Reward tracks whose emotional intensity fits the narrative position."""
    if context.total <= 1:
        return 1.0
    intensity = candidate.emotional_intensity
    if intensity is None:
        return 1.0
    frac = context.position / max(context.total - 1, 1)
    target = _intensity_curve(frac)
    fit = 1.0 - abs(intensity - target)
    return (0.85 + 0.30 * fit) * strength + 1.0 * (1.0 - strength)
```

- [ ] **Step 4: Implement chapter_break_modifier**

```python
def chapter_break_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    intent: "PlaylistIntent | None" = None,
    strength: float = 1.0,
) -> float:
    """At chapter boundaries, reward contrast. Between boundaries, neutral."""
    if intent is None or context.position not in intent.chapter_boundaries:
        return 1.0

    recent_textures = {t.sonic_texture for t in context.recent_tracks if t.sonic_texture}
    recent_stances = {t.narrator_stance for t in context.recent_tracks if t.narrator_stance}

    novelty_bonus = 0.0
    if candidate.sonic_texture and candidate.sonic_texture not in recent_textures:
        novelty_bonus += 0.1
    if candidate.narrator_stance and candidate.narrator_stance not in recent_stances:
        novelty_bonus += 0.1

    return (1.0 + novelty_bonus) * strength + 1.0 * (1.0 - strength)
```

- [ ] **Step 5: Implement duration_pacing_modifier**

```python
def duration_pacing_modifier(
    candidate: TrackMetadata,
    context: SequenceContext,
    strength: float = 1.0,
) -> float:
    """Penalize same-length runs and reward arc-appropriate durations."""
    if not candidate.duration_ms:
        return 1.0

    recent_durations = [t.duration_ms for t in context.recent_tracks if t.duration_ms]
    if len(recent_durations) >= 3:
        avg_recent = sum(recent_durations) / len(recent_durations)
        candidate_ms = candidate.duration_ms
        # Penalize if within 25 seconds of average
        if abs(candidate_ms - avg_recent) < 25000:
            return 0.92 * strength + 1.0 * (1.0 - strength)

    return 1.0
```

- [ ] **Step 6: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_modifiers_narrative.py -v`
Expected: All PASS.

- [ ] **Step 7: Run full suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add tuneshift/sequencer/modifiers.py tests/test_modifiers_narrative.py
git commit -m "feat(tuneshift): add intensity arc, chapter break, and duration pacing modifiers"
```

---

### Task 5: Create intent inference module

**Files:**
- Create: `tuneshift/sequencer/intent.py`
- Create: `tests/test_intent.py`

- [ ] **Step 1: Write tests**

Create `tests/test_intent.py`:

```python
"""Tests for playlist intent inference."""
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.intent import infer_intent


def _make_tracks(specs):
    """Create TrackMetadata list from (title, intensity, stance, themes, texture) tuples."""
    tracks = []
    for i, (title, intensity, stance, themes, texture) in enumerate(specs):
        tracks.append(TrackMetadata(
            track_id=i, title=title, artist=f"Artist {i}",
            emotional_intensity=intensity, narrator_stance=stance,
            themes=themes, vibes=[], sonic_texture=texture,
        ))
    return tracks


def test_infer_intent_identifies_climax_candidates():
    """Tracks with highest emotional_intensity become climax candidates."""
    tracks = _make_tracks([
        ("A", 0.3, "joyful", ["pop"], "warm"),
        ("B", 0.5, "introspective", ["folk"], "warm"),
        ("C", 0.95, "defiant", ["rock"], "gritty"),
        ("D", 0.4, "celebratory", ["pop"], "polished"),
        ("E", 0.9, "vulnerable", ["ballad"], "warm"),
    ])
    intent = infer_intent(tracks)
    # C and E should be climax candidates (highest intensity)
    assert 2 in intent.climax_candidates
    assert 4 in intent.climax_candidates


def test_infer_intent_finds_dominant_themes():
    """Most common themes across tracks are identified."""
    tracks = _make_tracks([
        ("A", 0.5, "joyful", ["pop", "dance"], "polished"),
        ("B", 0.5, "joyful", ["pop", "synth"], "polished"),
        ("C", 0.5, "defiant", ["rock", "pop"], "gritty"),
    ])
    intent = infer_intent(tracks)
    assert "pop" in intent.dominant_themes


def test_infer_intent_detects_chapter_boundaries():
    """Chapter boundaries where themes shift are identified."""
    tracks = _make_tracks([
        ("A", 0.5, "vulnerable", ["folk", "acoustic"], "warm"),
        ("B", 0.5, "vulnerable", ["folk", "acoustic"], "warm"),
        ("C", 0.5, "vulnerable", ["folk", "acoustic"], "warm"),
        ("D", 0.8, "defiant", ["rock", "electric"], "gritty"),
        ("E", 0.8, "defiant", ["rock", "electric"], "gritty"),
    ])
    intent = infer_intent(tracks)
    # Boundary should be around position 3 (shift from folk to rock)
    assert any(2 <= b <= 3 for b in intent.chapter_boundaries)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_intent.py -v`
Expected: FAIL (module doesn't exist).

- [ ] **Step 3: Implement intent.py**

Create `tuneshift/sequencer/intent.py`:

```python
"""Playlist intent inference from track metadata."""
from collections import Counter
from dataclasses import dataclass, field

from tuneshift.sequencer.metadata import TrackMetadata


@dataclass
class PlaylistIntent:
    """Inferred narrative intent for a playlist."""

    dominant_themes: list[str] = field(default_factory=list)
    emotional_range: tuple[float, float] = (0.0, 1.0)
    tonal_center: str = ""
    sonic_palette: list[str] = field(default_factory=list)
    climax_candidates: list[int] = field(default_factory=list)
    suggested_arc: str = "narrative"
    chapter_boundaries: list[int] = field(default_factory=list)


def infer_intent(tracks: list[TrackMetadata]) -> PlaylistIntent:
    """Analyze track metadata to determine playlist narrative intent.

    Uses simple heuristics (no LLM call): theme frequency, intensity range,
    stance distribution, sliding-window similarity for chapter detection.
    """
    if not tracks:
        return PlaylistIntent()

    # Dominant themes
    theme_counter: Counter[str] = Counter()
    for t in tracks:
        for tag in t.themes + t.vibes:
            theme_counter[tag] += 1
    dominant_themes = [tag for tag, _ in theme_counter.most_common(5)]

    # Emotional range
    intensities = [t.emotional_intensity for t in tracks if t.emotional_intensity is not None]
    if intensities:
        emotional_range = (min(intensities), max(intensities))
    else:
        emotional_range = (0.0, 1.0)

    # Tonal center (most common stance)
    stance_counter: Counter[str] = Counter()
    for t in tracks:
        if t.narrator_stance:
            stance_counter[t.narrator_stance] += 1
    tonal_center = stance_counter.most_common(1)[0][0] if stance_counter else ""

    # Sonic palette
    texture_counter: Counter[str] = Counter()
    for t in tracks:
        if t.sonic_texture:
            texture_counter[t.sonic_texture] += 1
    sonic_palette = [tex for tex, _ in texture_counter.most_common(3)]

    # Climax candidates: top tracks by emotional intensity
    n_climax = max(1, len(tracks) // 15)
    sorted_by_intensity = sorted(
        [(t.track_id, t.emotional_intensity or 0.0) for t in tracks],
        key=lambda x: x[1],
        reverse=True,
    )
    climax_candidates = [tid for tid, _ in sorted_by_intensity[:n_climax]]

    # Chapter boundaries: where sliding window similarity drops
    chapter_boundaries = _detect_chapters(tracks)

    # Suggested arc
    intensity_spread = emotional_range[1] - emotional_range[0]
    suggested_arc = "narrative" if intensity_spread > 0.4 else "wave"

    return PlaylistIntent(
        dominant_themes=dominant_themes,
        emotional_range=emotional_range,
        tonal_center=tonal_center,
        sonic_palette=sonic_palette,
        climax_candidates=climax_candidates,
        suggested_arc=suggested_arc,
        chapter_boundaries=chapter_boundaries,
    )


def _detect_chapters(tracks: list[TrackMetadata], window: int = 3) -> list[int]:
    """Detect chapter boundaries by sliding window Jaccard similarity drop."""
    if len(tracks) < window * 2:
        return []

    boundaries: list[int] = []
    for i in range(window, len(tracks) - window):
        left_tags: set[str] = set()
        for t in tracks[i - window:i]:
            left_tags.update(t.themes + t.vibes)
        right_tags: set[str] = set()
        for t in tracks[i:i + window]:
            right_tags.update(t.themes + t.vibes)

        if not left_tags and not right_tags:
            continue
        union = len(left_tags | right_tags)
        if union == 0:
            continue
        similarity = len(left_tags & right_tags) / union
        if similarity < 0.3:
            # Avoid consecutive boundaries
            if not boundaries or i - boundaries[-1] >= window:
                boundaries.append(i)

    return boundaries
```

- [ ] **Step 4: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_intent.py -v`
Expected: All PASS.

- [ ] **Step 5: Run full suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add tuneshift/sequencer/intent.py tests/test_intent.py
git commit -m "feat(tuneshift): add playlist intent inference for narrative sequencing"
```

---

## Chunk 4: Optimizer Integration and Moment System

### Task 6: Add narrative weights profile

**Files:**
- Modify: `tuneshift/sequencer/profiles.py`

- [ ] **Step 1: Add NARRATIVE_WEIGHTS and profile**

```python
NARRATIVE_WEIGHTS: dict[str, float] = {
    "themes": 0.20,
    "energy": 0.12,
    "instrumentation": 0.10,
    "bpm": 0.08,
    "mode": 0.05,
    "key": 0.05,
    "transition": 0.15,
    "narrative": 0.15,
    "emotional_arc": 0.10,
}
```

Add a "narrative" profile to `_BUILTIN_PROFILES`:

```python
"narrative": WeightProfile(
    name="narrative",
    description="Full narrative intelligence with emotional arc",
    weights=dict(NARRATIVE_WEIGHTS),
    arc="narrative",
    bold_jump_chance=0.0,  # replaced by chapter breaks
    artist_min_separation=4,
    narrative_mode="chapter",
    context_window=5,
),
```

- [ ] **Step 2: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass (additive).

- [ ] **Step 3: Commit**

```bash
git add tuneshift/sequencer/profiles.py
git commit -m "feat(tuneshift): add narrative weight profile with new scoring dimensions"
```

---

### Task 7: Integrate modifiers and intent into optimizer

**Files:**
- Modify: `tuneshift/sequencer/optimizer.py`
- Modify: `tuneshift/sequencer/modifiers.py` (update `score_candidate`)

- [ ] **Step 1: Update score_candidate to include new modifiers**

In `modifiers.py`, EXTEND `score_candidate()` to include the new modifiers. Add `intent` as a new optional parameter (default None) so ALL existing callers continue to work without changes. Existing callers in `optimizer.py` (line ~337) pass positional args only, so `intent` must remain keyword-only or last positional with default None:

```python
def score_candidate(
    candidate: TrackMetadata,
    current: TrackMetadata,
    context: SequenceContext,
    base_score: float,
    penalty_strengths: dict[str, float] | None = None,
    intent: "PlaylistIntent | None" = None,
) -> float:
    """Apply all context modifiers to a base pairwise score."""
    strengths = penalty_strengths or {}

    effective_base = base_score
    if candidate.artist == current.artist:
        effective_base = min(base_score, 0.55)

    modifiers = [
        artist_recency_penalty(candidate, context, strengths.get("artist_recency", 1.0)),
        artist_variety_bonus(candidate, context, strengths.get("artist_variety", 1.0)),
        subgenre_staleness_penalty(candidate, context, strengths.get("subgenre_staleness", 1.0)),
        era_diversity_bonus(candidate, context, strengths.get("era_diversity", 1.0)),
        energy_monotony_penalty(candidate, context, strengths.get("energy_monotony", 1.0)),
        narrative_arc_modifier(candidate, context, strengths.get("narrative_arc", 1.0)),
        intensity_arc_modifier(candidate, context, strengths.get("intensity_arc", 1.0)),
        chapter_break_modifier(candidate, context, intent, strengths.get("chapter_break", 1.0)),
        duration_pacing_modifier(candidate, context, strengths.get("duration_pacing", 1.0)),
    ]

    product = 1.0
    for modifier in modifiers:
        product *= modifier

    result = effective_base * product
    return max(result, SCORE_FLOOR)
```

- [ ] **Step 2: Update optimizer to pass intent through**

In `optimizer.py`, modify `_greedy_build` to accept and pass `intent`:

Add `intent: "PlaylistIntent | None" = None` parameter to `_greedy_build` signature (current signature at line ~285). This is a BREAKING signature change; update the call site in `optimize_sequence` (line ~400) to pass the new `intent` arg. Pass it to `score_candidate`:

```python
adjusted = score_candidate(
    candidate, current, context,
    base * arc_mult, penalty_overrides, intent,
)
```

In `optimize_sequence`, infer intent before building:

```python
from tuneshift.sequencer.intent import infer_intent

# In optimize_sequence, before _greedy_build:
intent = infer_intent(tracks) if arc == "narrative" else None
```

Pass `intent` to `_greedy_build`.

- [ ] **Step 3: Update narrative opener/closer selection**

Replace `select_opener` and `select_closer` with narrative-aware versions per the spec. The new logic factors in:
- `emotional_intensity` (openers should be moderate ~0.4, closers should be resolution ~0.4-0.5)
- `sonic_texture` (warm/lush/intimate preferred for openers)
- `narrator_stance` (openers: observational/inviting; closers: resigned/triumphant/peaceful)
- `opens_with` (evocative openings preferred for openers)

Only activate for `arc == "narrative"`. Non-narrative arcs use existing logic.

- [ ] **Step 4: Replace random bold jumps for narrative arc**

In `_greedy_build`, modify the bold jump logic:

```python
# Bold jumps: use chapter breaks for narrative, random for other arcs
use_bold_jumps = arc != "narrative" or intent is None
if (
    use_bold_jumps
    and not protect_region
    and bold_jump_cooldown == 0
    and random.random() < bold_jump_chance
    and len(candidates) > 3
):
    # ... existing bold jump logic ...
```

For narrative arcs with intent, the `chapter_break_modifier` handles variety at
chapter boundaries instead of random jumps.

> **Backward compat note:** When `arc="narrative"` but tracks lack new classification fields (un-enriched), `intent` will be None (infer_intent returns None when data is insufficient). This causes `use_bold_jumps = True`, preserving existing random-jump behavior. Add a test case verifying this fallback.

- [ ] **Step 5: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: All pass.

- [ ] **Step 6: Lint**

Run: `cd tools/tuneshift && .venv/bin/ruff check .`
Expected: No violations.

- [ ] **Step 7: Commit**

```bash
git add tuneshift/sequencer/optimizer.py tuneshift/sequencer/modifiers.py
git commit -m "feat(tuneshift): integrate narrative intelligence into optimizer pipeline"
```

---

### Task 8: Add moment pin type and placement

**Files:**
- Modify: `tuneshift/commands/pin_cmd.py`
- Modify: `tuneshift/cli.py`
- Modify: `tuneshift/sequencer/optimizer.py`
- Create: `tests/test_moment_placement.py`

- [ ] **Step 1: Write tests**

Create `tests/test_moment_placement.py`:

```python
"""Tests for moment pin placement in the climax region."""
import pytest
from tuneshift.db import Database
from tuneshift.models import Track, PlaylistPin
from tuneshift.sequencer.optimizer import _place_moments


def test_place_moments_targets_climax_region():
    """Moments are placed in the 55-75% region."""
    # 20-track playlist: climax region is positions 11-15
    positions = _place_moments(
        tracks=[],  # not needed for placement logic
        moments=[42],  # one moment track_id
        total=20,
    )
    assert len(positions) == 1
    target_pos = list(positions.keys())[0]
    assert 11 <= target_pos <= 15


def test_place_moments_multiple_spaced():
    """Multiple moments are evenly spaced in climax region."""
    positions = _place_moments(
        tracks=[], moments=[42, 99], total=20,
    )
    assert len(positions) == 2
    pos_list = sorted(positions.keys())
    assert pos_list[0] < pos_list[1]
    assert all(11 <= p <= 15 for p in pos_list)


def test_place_moments_empty():
    """No moments returns empty dict."""
    assert _place_moments([], [], 20) == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_moment_placement.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement _place_moments in optimizer.py**

```python
def _place_moments(
    tracks: list[TrackMetadata],
    moments: list[int],
    total: int,
) -> dict[int, int]:
    """Assign moment tracks to positions in the climax region (55-75%).

    Returns dict of target_position -> track_id (treated like position pins).
    """
    if not moments:
        return {}
    climax_start = int(total * 0.55)
    climax_end = int(total * 0.75)
    available_positions = list(range(climax_start, min(climax_end + 1, total - 1)))
    if not available_positions:
        return {}
    step = max(1, len(available_positions) // (len(moments) + 1))
    result: dict[int, int] = {}
    for i, track_id in enumerate(moments):
        pos = climax_start + (i + 1) * step
        pos = min(pos, climax_end, total - 2)  # don't overlap with closer
        result[pos] = track_id
    return result
```

- [ ] **Step 4: Integrate moments into optimize_sequence**

In `optimize_sequence`, after resolving pins and before greedy build:

```python
# Resolve moments (auto-detected or pinned)
# Insert this AFTER _resolve_pins (around line 394-400) and BEFORE free pool preparation
moment_track_ids = [p.track_id for p in (pins or []) if p.pin_type == "moment"]
if not moment_track_ids and intent:
    moment_track_ids = intent.climax_candidates

moment_positions = _place_moments(tracks, moment_track_ids, track_count)
# Merge with position_pins (moments are just region-aware position pins)
position_pins.update(moment_positions)
```

- [ ] **Step 5: Add --moment to pin command**

In `tuneshift/commands/pin_cmd.py`, add handling for `--moment`:

```python
if args.moment:
    db.set_pin(playlist.id, track.id, pin_type="moment")
    print(f'Pinned "{track.title}" as moment (will be placed at climax)')
```

In `tuneshift/cli.py`, add to the pin subparser:
```python
p_pin.add_argument("--moment", metavar="TITLE", help="Pin track as a narrative moment (placed at climax)")
```

- [ ] **Step 6: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_moment_placement.py tests/test_pin_cmd.py -v`
Expected: All PASS.

- [ ] **Step 7: Run full suite + lint**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q && .venv/bin/ruff check .`
Expected: All pass, no violations.

- [ ] **Step 8: Commit**

```bash
git add tuneshift/sequencer/optimizer.py tuneshift/commands/pin_cmd.py tuneshift/cli.py tests/test_moment_placement.py
git commit -m "feat(tuneshift): add moment pin type with automatic climax placement"
```

---

## Final Verification

- [ ] **Run full test suite**: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -v`
- [ ] **Run linter**: `cd tools/tuneshift && .venv/bin/ruff check .`
- [ ] **Verify CLI**: `.venv/bin/python -m tuneshift pin --help` (shows --moment)
- [ ] **Verify enrich**: `.venv/bin/python -m tuneshift enrich --help` (shows --model)
- [ ] **Backward compat**: Run sequencer on a playlist without new metadata, verify it still sequences correctly using existing energy/themes data
