# TuneShift: Reconciliation v2, Curation Layer, and Sequencer v2 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform TuneShift from a sync tool into an intelligent playlist curator with album-aware reconciliation, full-spectrum weighted sequencing, and constraint-driven curation.

**Architecture:** Pipeline model: reconcile (find correct version) -> curate (trim/fill to constraints) -> sequence (order by weighted dimensions) -> sync. Foundation layer adds playlist identity (goal, weights, constraints) to the schema. Each layer reads from the DB and produces output the next layer consumes.

**Tech Stack:** Python 3.10+, SQLite, existing LLM multi-backend (Anthropic/OpenAI/Ollama), optional Genius/Musixmatch lyrics API, existing platform clients (Tidal, YouTube Music).

**Spec:** `docs/superpowers/specs/2026-06-11-tuneshift-reconciliation-curation-sequencer-design.md`

---

## Chunk 1: Foundation (Playlist Identity Model)

Schema migration v7, CLI commands for goal/weights/constraints, and the data structures that all three features depend on.

### Task 1: Schema Migration v7

**Files:**
- Modify: `tuneshift/db.py` (schema string, migration logic, new methods)
- Test: `tests/identity/test_db_migration.py`

- [ ] **Step 1: Write failing test for schema v7**

```python
# In tests/identity/test_db_migration.py, update test_schema_version_is_current:
def test_schema_version_is_current(self, db):
    row = db.conn.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()
    assert int(row[0]) == 7

# Add new test:
def test_v7_playlist_columns_exist(self, db):
    """Schema v7 adds goal, playlist_type, weights, mood_profile, curation_constraints, preferences."""
    cursor = db.conn.execute("PRAGMA table_info(playlists)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "goal" in columns
    assert "playlist_type" in columns
    assert "weights" in columns
    assert "mood_profile" in columns
    assert "curation_constraints" in columns
    assert "preferences" in columns

def test_v7_playlist_tracks_version_override(self, db):
    """Schema v7 adds version_override to playlist_tracks."""
    cursor = db.conn.execute("PRAGMA table_info(playlist_tracks)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "version_override" in columns
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/identity/test_db_migration.py -x -q`
Expected: FAIL (version is 6, columns don't exist)

- [ ] **Step 3: Implement schema v7 migration**

In `tuneshift/db.py`:
1. Update `_SCHEMA` string: add `goal TEXT`, `playlist_type TEXT`, `weights TEXT`, `mood_profile TEXT`, `curation_constraints TEXT`, `preferences TEXT` to `CREATE TABLE playlists`.
2. Add `version_override TEXT` to `CREATE TABLE playlist_tracks`.
3. Add migration case for version 6->7:

```python
if version < 7:
    self.conn.execute("ALTER TABLE playlists ADD COLUMN goal TEXT")
    self.conn.execute("ALTER TABLE playlists ADD COLUMN playlist_type TEXT")
    self.conn.execute("ALTER TABLE playlists ADD COLUMN weights TEXT")
    self.conn.execute("ALTER TABLE playlists ADD COLUMN mood_profile TEXT")
    self.conn.execute("ALTER TABLE playlists ADD COLUMN curation_constraints TEXT")
    self.conn.execute("ALTER TABLE playlists ADD COLUMN preferences TEXT")
    self.conn.execute("ALTER TABLE playlist_tracks ADD COLUMN version_override TEXT")
    self.conn.execute("UPDATE schema_meta SET value = '7' WHERE key = 'version'")
    self.conn.commit()
```

4. Update `CURRENT_VERSION = 7` (or equivalent constant).

- [ ] **Step 4: Run tests to verify pass**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/identity/test_db_migration.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tuneshift/db.py tests/identity/test_db_migration.py
git commit -m "feat(db): schema v7 - playlist identity model columns"
```

---

### Task 2: Playlist Identity DB Methods

**Files:**
- Modify: `tuneshift/db.py` (new getter/setter methods)
- Test: `tests/test_playlist_identity.py` (new file)

- [ ] **Step 1: Write tests for goal/weights/constraints/preferences methods**

```python
# tests/test_playlist_identity.py
import json
from pathlib import Path
import pytest
from tuneshift.db import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


class TestPlaylistGoal:
    def test_set_and_get_goal(self, db: Database) -> None:
        pid = db.create_playlist("Test")
        db.set_goal(pid, "Celebrate trans joy and fury")
        assert db.get_goal(pid) == "Celebrate trans joy and fury"

    def test_get_goal_returns_none_when_unset(self, db: Database) -> None:
        pid = db.create_playlist("Empty")
        assert db.get_goal(pid) is None


class TestPlaylistWeights:
    def test_set_and_get_weights(self, db: Database) -> None:
        pid = db.create_playlist("Test")
        weights = {"narrative_arc": 0.9, "energy_flow": 0.3, "mood_continuity": 0.7}
        db.set_weights(pid, weights)
        assert db.get_weights(pid) == weights

    def test_get_weights_returns_none_when_unset(self, db: Database) -> None:
        pid = db.create_playlist("Empty")
        assert db.get_weights(pid) is None


class TestPlaylistConstraints:
    def test_set_and_get_constraints(self, db: Database) -> None:
        pid = db.create_playlist("Test")
        constraints = {
            "duration": {"target_minutes": 90, "tolerance_minutes": 10, "hard_limit_minutes": 120},
            "track_count": {"target": 25, "tolerance": 5, "hard_limit": None},
        }
        db.set_constraints(pid, constraints)
        assert db.get_constraints(pid) == constraints


class TestPlaylistPreferences:
    def test_set_and_get_preferences(self, db: Database) -> None:
        pid = db.create_playlist("Test")
        prefs = {"version_preferences": {"prefer": ["studio", "explicit"], "avoid": ["live"]}}
        db.set_preferences(pid, prefs)
        assert db.get_preferences(pid) == prefs


class TestPlaylistType:
    def test_set_and_get_type(self, db: Database) -> None:
        pid = db.create_playlist("Test")
        db.set_playlist_type(pid, "narrative")
        assert db.get_playlist_type(pid) == "narrative"


class TestMoodProfile:
    def test_set_and_get_mood_profile(self, db: Database) -> None:
        pid = db.create_playlist("Test")
        mood = {"primary": "defiant", "secondary": "euphoric", "arc": "build-to-catharsis"}
        db.set_mood_profile(pid, mood)
        assert db.get_mood_profile(pid) == mood

    def test_get_mood_profile_returns_none_when_unset(self, db: Database) -> None:
        pid = db.create_playlist("Empty")
        assert db.get_mood_profile(pid) is None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_playlist_identity.py -x -q`
Expected: FAIL (methods don't exist)

- [ ] **Step 3: Implement DB methods**

Add to `tuneshift/db.py`:

```python
def set_goal(self, playlist_id: int, goal: str | None) -> None:
    self.conn.execute("UPDATE playlists SET goal = ? WHERE id = ?", (goal, playlist_id))
    self.conn.commit()

def get_goal(self, playlist_id: int) -> str | None:
    row = self.conn.execute("SELECT goal FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
    return row[0] if row else None

def set_weights(self, playlist_id: int, weights: dict | None) -> None:
    import json as _json
    val = _json.dumps(weights) if weights else None
    self.conn.execute("UPDATE playlists SET weights = ? WHERE id = ?", (val, playlist_id))
    self.conn.commit()

def get_weights(self, playlist_id: int) -> dict | None:
    import json as _json
    row = self.conn.execute("SELECT weights FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
    return _json.loads(row[0]) if row and row[0] else None

def set_constraints(self, playlist_id: int, constraints: dict | None) -> None:
    import json as _json
    val = _json.dumps(constraints) if constraints else None
    self.conn.execute("UPDATE playlists SET curation_constraints = ? WHERE id = ?", (val, playlist_id))
    self.conn.commit()

def get_constraints(self, playlist_id: int) -> dict | None:
    import json as _json
    row = self.conn.execute("SELECT curation_constraints FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
    return _json.loads(row[0]) if row and row[0] else None

def set_preferences(self, playlist_id: int, prefs: dict | None) -> None:
    import json as _json
    val = _json.dumps(prefs) if prefs else None
    self.conn.execute("UPDATE playlists SET preferences = ? WHERE id = ?", (val, playlist_id))
    self.conn.commit()

def get_preferences(self, playlist_id: int) -> dict | None:
    import json as _json
    row = self.conn.execute("SELECT preferences FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
    return _json.loads(row[0]) if row and row[0] else None

def set_playlist_type(self, playlist_id: int, playlist_type: str | None) -> None:
    self.conn.execute("UPDATE playlists SET playlist_type = ? WHERE id = ?", (playlist_type, playlist_id))
    self.conn.commit()

def get_playlist_type(self, playlist_id: int) -> str | None:
    row = self.conn.execute("SELECT playlist_type FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
    return row[0] if row else None

def set_mood_profile(self, playlist_id: int, mood_profile: dict | None) -> None:
    import json as _json
    val = _json.dumps(mood_profile) if mood_profile else None
    self.conn.execute("UPDATE playlists SET mood_profile = ? WHERE id = ?", (val, playlist_id))
    self.conn.commit()

def get_mood_profile(self, playlist_id: int) -> dict | None:
    import json as _json
    row = self.conn.execute("SELECT mood_profile FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
    return _json.loads(row[0]) if row and row[0] else None
```

- [ ] **Step 4: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_playlist_identity.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tuneshift/db.py tests/test_playlist_identity.py
git commit -m "feat(db): playlist identity methods (goal, weights, constraints, preferences)"
```

---

### Task 3: CLI Commands for Playlist Identity

**Files:**
- Create: `tuneshift/commands/goal_cmd.py`
- Create: `tuneshift/commands/weights_cmd.py`
- Modify: `tuneshift/cli.py` (add subcommands)
- Test: `tests/test_goal_cmd.py` (new)
- Test: `tests/test_weights_cmd.py` (new)

- [ ] **Step 1: Write tests for goal command**

```python
# tests/test_goal_cmd.py
from pathlib import Path
from types import SimpleNamespace
import pytest
from tuneshift.db import Database
from tuneshift.commands.goal_cmd import handle_goal


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "test.db")
    d.create_playlist("Trans Wrath")
    return d


class TestHandleGoal:
    def test_set_goal(self, db: Database) -> None:
        args = SimpleNamespace(playlist="Trans Wrath", text="Celebrate trans fury", clear=False)
        result = handle_goal(args, db)
        assert result == 0
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        assert db.get_goal(pid) == "Celebrate trans fury"

    def test_show_goal(self, db: Database, capsys) -> None:
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        db.set_goal(pid, "Existing goal")
        args = SimpleNamespace(playlist="Trans Wrath", text=None, clear=False)
        handle_goal(args, db)
        out = capsys.readouterr().out
        assert "Existing goal" in out

    def test_clear_goal(self, db: Database) -> None:
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        db.set_goal(pid, "Something")
        args = SimpleNamespace(playlist="Trans Wrath", text=None, clear=True)
        handle_goal(args, db)
        assert db.get_goal(pid) is None
```

- [ ] **Step 2: Write tests for weights command**

```python
# tests/test_weights_cmd.py
from pathlib import Path
from types import SimpleNamespace
import pytest
from tuneshift.db import Database
from tuneshift.commands.weights_cmd import handle_weights


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "test.db")
    d.create_playlist("Trans Wrath")
    return d


class TestHandleWeights:
    def test_set_preset(self, db: Database) -> None:
        args = SimpleNamespace(
            playlist="Trans Wrath", preset="narrative-queen",
            values=None, action="set",
        )
        result = handle_weights(args, db)
        assert result == 0
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        w = db.get_weights(pid)
        assert w["narrative_arc"] == 0.9

    def test_set_granular(self, db: Database) -> None:
        args = SimpleNamespace(
            playlist="Trans Wrath", preset=None,
            values=["narrative_arc=0.8", "mood_continuity=0.6"],
            action="set",
        )
        handle_weights(args, db)
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        w = db.get_weights(pid)
        assert w["narrative_arc"] == 0.8
        assert w["mood_continuity"] == 0.6

    def test_list_presets(self, db: Database, capsys) -> None:
        args = SimpleNamespace(playlist=None, preset=None, values=None, action="list")
        handle_weights(args, db)
        out = capsys.readouterr().out
        assert "narrative-queen" in out
        assert "energy-wave" in out
```

- [ ] **Step 3: Run tests to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_goal_cmd.py tests/test_weights_cmd.py -x -q`
Expected: FAIL (modules don't exist)

- [ ] **Step 4: Implement goal_cmd.py**

```python
# tuneshift/commands/goal_cmd.py
"""Goal command: set/show/clear playlist goal."""
from tuneshift.db import Database


def handle_goal(args, db: Database) -> int:
    """Set, show, or clear a playlist's goal."""
    playlists = db.list_playlists()
    matches = [p for p in playlists if p.name == args.playlist]
    if not matches:
        print(f'Playlist "{args.playlist}" not found.')
        return 1

    pid = matches[0].id

    if args.clear:
        db.set_goal(pid, None)
        print(f'Cleared goal for "{args.playlist}".')
        return 0

    if args.text:
        db.set_goal(pid, args.text)
        print(f'Set goal for "{args.playlist}".')
        return 0

    # Show current goal
    goal = db.get_goal(pid)
    if goal:
        print(f'Goal for "{args.playlist}":\n\n{goal}')
    else:
        print(f'No goal set for "{args.playlist}". Set one with: tuneshift goal "{args.playlist}" "<text>"')
    return 0
```

- [ ] **Step 5: Implement weights_cmd.py with presets**

```python
# tuneshift/commands/weights_cmd.py
"""Weights command: manage sequencing weight vectors."""
from tuneshift.db import Database

PRESETS: dict[str, dict[str, float]] = {
    "narrative-queen": {
        "narrative_arc": 0.9, "emotional_arc": 0.8, "lyrical_thread": 0.8,
        "mood_continuity": 0.7, "energy_flow": 0.3, "sonic_texture": 0.5,
        "variety": 0.4, "artist_separation": 0.6, "groove_coherence": 0.4, "era_mood": 0.3,
    },
    "energy-wave": {
        "energy_flow": 0.9, "mood_continuity": 0.6, "sonic_texture": 0.5,
        "variety": 0.5, "artist_separation": 0.5, "groove_coherence": 0.6,
        "narrative_arc": 0.0, "lyrical_thread": 0.1, "emotional_arc": 0.3, "era_mood": 0.2,
    },
    "mood-bath": {
        "mood_continuity": 0.9, "sonic_texture": 0.8, "groove_coherence": 0.7,
        "energy_flow": 0.3, "variety": 0.3, "emotional_arc": 0.5,
        "narrative_arc": 0.0, "lyrical_thread": 0.2, "artist_separation": 0.4, "era_mood": 0.6,
    },
    "discovery": {
        "variety": 0.9, "energy_flow": 0.6, "sonic_texture": 0.5,
        "mood_continuity": 0.4, "artist_separation": 0.8, "groove_coherence": 0.3,
        "narrative_arc": 0.0, "lyrical_thread": 0.1, "emotional_arc": 0.2, "era_mood": 0.3,
    },
    "workout": {
        "energy_flow": 0.9, "groove_coherence": 0.8, "variety": 0.3,
        "mood_continuity": 0.4, "sonic_texture": 0.3, "artist_separation": 0.5,
        "narrative_arc": 0.0, "lyrical_thread": 0.0, "emotional_arc": 0.2, "era_mood": 0.1,
    },
}

VALID_DIMENSIONS = {
    "narrative_arc", "energy_flow", "mood_continuity", "sonic_texture",
    "lyrical_thread", "emotional_arc", "groove_coherence", "era_mood",
    "variety", "artist_separation",
}


def handle_weights(args, db: Database) -> int:
    """Manage sequencing weight vectors."""
    if args.action == "list":
        print("Available weight presets:\n")
        for name, weights in PRESETS.items():
            top3 = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]
            summary = ", ".join(f"{k}={v}" for k, v in top3)
            print(f"  {name}: {summary} ...")
        return 0

    if not args.playlist:
        print("Playlist name required for set/show.")
        return 1

    playlists = db.list_playlists()
    matches = [p for p in playlists if p.name == args.playlist]
    if not matches:
        print(f'Playlist "{args.playlist}" not found.')
        return 1

    pid = matches[0].id

    if args.action == "show":
        weights = db.get_weights(pid)
        if weights:
            print(f'Weights for "{args.playlist}":')
            for dim, val in sorted(weights.items(), key=lambda x: x[1], reverse=True):
                bar = "#" * int(val * 10)
                print(f"  {dim:20s} {val:.1f} {bar}")
        else:
            print(f'No weights set for "{args.playlist}". Using default (energy-wave).')
        return 0

    # action == "set"
    if args.preset:
        if args.preset not in PRESETS:
            print(f'Unknown preset "{args.preset}". Use `tuneshift weights list`.')
            return 1
        db.set_weights(pid, PRESETS[args.preset])
        print(f'Set weights for "{args.playlist}" to preset "{args.preset}".')
        return 0

    if args.values:
        weights = db.get_weights(pid) or {}
        for pair in args.values:
            if "=" not in pair:
                print(f'Invalid format: "{pair}". Use dimension=value.')
                return 1
            dim, val_str = pair.split("=", 1)
            if dim not in VALID_DIMENSIONS:
                print(f'Unknown dimension: "{dim}". Valid: {sorted(VALID_DIMENSIONS)}')
                return 1
            weights[dim] = float(val_str)
        db.set_weights(pid, weights)
        print(f'Updated weights for "{args.playlist}".')
        return 0

    print("Specify --preset or dimension=value pairs.")
    return 1
```

- [ ] **Step 6: Wire into CLI**

In `tuneshift/cli.py`, add subcommands for `goal` and `weights`:

```python
# goal
p_goal = sub.add_parser("goal", help="Set or show playlist goal/theme")
p_goal.add_argument("playlist", help="Playlist name")
p_goal.add_argument("text", nargs="?", help="Goal text to set")
p_goal.add_argument("--clear", action="store_true", help="Clear the goal")

# weights
p_weights = sub.add_parser("weights", help="Manage sequencing weight presets")
p_weights.add_argument("action", nargs="?", default="list", choices=["list", "set", "show"])
p_weights.add_argument("playlist", nargs="?", help="Playlist name")
p_weights.add_argument("--preset", help="Named preset to apply")
p_weights.add_argument("values", nargs="*", help="dimension=value pairs")
```

And in the dispatch section:
```python
elif args.command == "goal":
    from tuneshift.commands.goal_cmd import handle_goal
    return handle_goal(args, db)
elif args.command == "weights":
    from tuneshift.commands.weights_cmd import handle_weights
    return handle_weights(args, db)
```

- [ ] **Step 7: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_goal_cmd.py tests/test_weights_cmd.py tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add tuneshift/commands/goal_cmd.py tuneshift/commands/weights_cmd.py tuneshift/cli.py tests/test_goal_cmd.py tests/test_weights_cmd.py
git commit -m "feat(cli): goal and weights commands for playlist identity"
```

---

### Task 4: WeightVector Data Model and Preset Resolution

**Files:**
- Create: `tuneshift/sequencer/weights.py`
- Test: `tests/test_weights_model.py` (new)

- [ ] **Step 1: Write tests**

```python
# tests/test_weights_model.py
import pytest
from tuneshift.sequencer.weights import resolve_weights, DEFAULT_WEIGHTS, PRESETS


class TestResolveWeights:
    def test_returns_default_when_none(self) -> None:
        w = resolve_weights(None, None)
        assert w == DEFAULT_WEIGHTS

    def test_preset_override(self) -> None:
        w = resolve_weights(None, "narrative-queen")
        assert w["narrative_arc"] == 0.9

    def test_custom_dict_used_directly(self) -> None:
        custom = {"energy_flow": 1.0, "variety": 0.5}
        w = resolve_weights(custom, None)
        assert w["energy_flow"] == 1.0
        assert w["variety"] == 0.5
        # Unspecified dimensions default to 0.0
        assert w.get("narrative_arc", 0.0) == 0.0

    def test_custom_overrides_preset(self) -> None:
        custom = {"narrative_arc": 0.5}
        w = resolve_weights(custom, "narrative-queen")
        # Custom wins over preset
        assert w["narrative_arc"] == 0.5

    def test_invalid_preset_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown preset"):
            resolve_weights(None, "nonexistent")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_weights_model.py -x -q`
Expected: FAIL

- [ ] **Step 3: Implement weights.py**

```python
# tuneshift/sequencer/weights.py
"""Weight vector resolution and preset management for sequencer."""

PRESETS: dict[str, dict[str, float]] = {
    "narrative-queen": {
        "narrative_arc": 0.9, "emotional_arc": 0.8, "lyrical_thread": 0.8,
        "mood_continuity": 0.7, "energy_flow": 0.3, "sonic_texture": 0.5,
        "variety": 0.4, "artist_separation": 0.6, "groove_coherence": 0.4, "era_mood": 0.3,
    },
    "energy-wave": {
        "energy_flow": 0.9, "mood_continuity": 0.6, "sonic_texture": 0.5,
        "variety": 0.5, "artist_separation": 0.5, "groove_coherence": 0.6,
        "narrative_arc": 0.0, "lyrical_thread": 0.1, "emotional_arc": 0.3, "era_mood": 0.2,
    },
    "mood-bath": {
        "mood_continuity": 0.9, "sonic_texture": 0.8, "groove_coherence": 0.7,
        "energy_flow": 0.3, "variety": 0.3, "emotional_arc": 0.5,
        "narrative_arc": 0.0, "lyrical_thread": 0.2, "artist_separation": 0.4, "era_mood": 0.6,
    },
    "discovery": {
        "variety": 0.9, "energy_flow": 0.6, "sonic_texture": 0.5,
        "mood_continuity": 0.4, "artist_separation": 0.8, "groove_coherence": 0.3,
        "narrative_arc": 0.0, "lyrical_thread": 0.1, "emotional_arc": 0.2, "era_mood": 0.3,
    },
    "workout": {
        "energy_flow": 0.9, "groove_coherence": 0.8, "variety": 0.3,
        "mood_continuity": 0.4, "sonic_texture": 0.3, "artist_separation": 0.5,
        "narrative_arc": 0.0, "lyrical_thread": 0.0, "emotional_arc": 0.2, "era_mood": 0.1,
    },
}

ALL_DIMENSIONS = [
    "narrative_arc", "energy_flow", "mood_continuity", "sonic_texture",
    "lyrical_thread", "emotional_arc", "groove_coherence", "era_mood",
    "variety", "artist_separation",
]

DEFAULT_WEIGHTS: dict[str, float] = PRESETS["energy-wave"]


def resolve_weights(
    stored_weights: dict[str, float] | None,
    preset_name: str | None,
) -> dict[str, float]:
    """Resolve final weight vector from stored weights and/or preset.

    Priority: stored_weights override preset values.
    If neither provided, returns DEFAULT_WEIGHTS.
    """
    if preset_name and preset_name not in PRESETS:
        raise ValueError(f"Unknown preset: '{preset_name}'. Available: {list(PRESETS.keys())}")

    base = dict(PRESETS.get(preset_name, DEFAULT_WEIGHTS)) if preset_name else {}

    if stored_weights:
        if not base:
            # Custom weights with no preset: start from zeros
            base = {dim: 0.0 for dim in ALL_DIMENSIONS}
        base.update(stored_weights)

    return base if base else dict(DEFAULT_WEIGHTS)
```

- [ ] **Step 4: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_weights_model.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tuneshift/sequencer/weights.py tests/test_weights_model.py
git commit -m "feat(sequencer): weight vector resolution with named presets"
```

---

## Chunk 2: Sequencer v2 (Full-Spectrum Scoring)

Extends `scoring.py` with new dimension scorers and refactors `score_pair` to use the DIMENSION_SCORERS registry.

### Task 5: New Dimension Scorers

**Files:**
- Modify: `tuneshift/sequencer/scoring.py` (add scorers, registry, refactor score_pair)
- Test: `tests/test_scoring_dimensions.py` (new)

- [ ] **Step 1: Write tests for new dimension scorers**

```python
# tests/test_scoring_dimensions.py
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.scoring import (
    score_mood_continuity,
    score_sonic_texture,
    score_lyrical_thread,
    score_groove_coherence,
    score_variety,
    DIMENSION_SCORERS,
)


def _track(**kwargs) -> TrackMetadata:
    defaults = {"track_id": 1, "title": "T", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(**defaults)


class TestMoodContinuity:
    def test_same_mood_scores_high(self) -> None:
        a = _track(emotional_intensity=0.8, vibes=["angry", "defiant"])
        b = _track(emotional_intensity=0.7, vibes=["angry", "fierce"])
        score = score_mood_continuity(a, b)
        assert score > 0.6

    def test_opposite_mood_scores_low(self) -> None:
        a = _track(emotional_intensity=0.9, vibes=["angry", "explosive"])
        b = _track(emotional_intensity=0.1, vibes=["peaceful", "gentle"])
        score = score_mood_continuity(a, b)
        assert score < 0.4

    def test_missing_data_returns_neutral(self) -> None:
        a = _track()
        b = _track()
        score = score_mood_continuity(a, b)
        assert score == 0.5


class TestSonicTexture:
    def test_similar_texture_scores_high(self) -> None:
        a = _track(sonic_texture="thick", space="intimate", density="dense")
        b = _track(sonic_texture="thick", space="intimate", density="dense")
        score = score_sonic_texture(a, b)
        assert score > 0.8

    def test_different_texture_scores_low(self) -> None:
        a = _track(sonic_texture="thin", space="vast", density="sparse")
        b = _track(sonic_texture="thick", space="intimate", density="dense")
        score = score_sonic_texture(a, b)
        assert score < 0.4


class TestLyricalThread:
    def test_same_subject_scores_high(self) -> None:
        a = _track(lyrical_subject="identity", narrator_stance="defiant")
        b = _track(lyrical_subject="identity", narrator_stance="defiant")
        score = score_lyrical_thread(a, b)
        assert score > 0.7

    def test_different_subject_scores_moderate(self) -> None:
        a = _track(lyrical_subject="love", narrator_stance="vulnerable")
        b = _track(lyrical_subject="rage", narrator_stance="defiant")
        score = score_lyrical_thread(a, b)
        assert score < 0.5


class TestDimensionRegistry:
    def test_all_dimensions_registered(self) -> None:
        expected = {
            "narrative_arc", "energy_flow", "mood_continuity", "sonic_texture",
            "lyrical_thread", "emotional_arc", "groove_coherence", "era_mood",
            "variety", "artist_separation",
        }
        assert set(DIMENSION_SCORERS.keys()) == expected

    def test_all_scorers_callable(self) -> None:
        for name, scorer in DIMENSION_SCORERS.items():
            assert callable(scorer), f"{name} scorer is not callable"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_scoring_dimensions.py -x -q`
Expected: FAIL (new functions don't exist)

- [ ] **Step 3: Implement new dimension scorers**

Add to `tuneshift/sequencer/scoring.py`:

```python
def score_mood_continuity(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score mood/emotional continuity between adjacent tracks."""
    if a.emotional_intensity is None and b.emotional_intensity is None:
        if not a.vibes and not b.vibes:
            return 0.5
    intensity_sim = 1.0 - abs(
        (a.emotional_intensity or 0.5) - (b.emotional_intensity or 0.5)
    )
    vibes_sim = jaccard(a.vibes, b.vibes)
    era_sim = jaccard(a.era_mood, b.era_mood)
    return 0.4 * intensity_sim + 0.4 * vibes_sim + 0.2 * era_sim


def score_sonic_texture(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score sonic texture/space/density transition quality."""
    if not a.sonic_texture and not b.sonic_texture:
        return 0.5
    texture_match = 1.0 if a.sonic_texture == b.sonic_texture else 0.3
    space_match = 1.0 if a.space == b.space else 0.4
    density_map = {"sparse": 0, "mid": 1, "dense": 2}
    da = density_map.get(a.density or "mid", 1)
    db_val = density_map.get(b.density or "mid", 1)
    density_sim = 1.0 - abs(da - db_val) / 2.0
    return 0.4 * texture_match + 0.3 * space_match + 0.3 * density_sim


def score_lyrical_thread(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score lyrical subject and narrator stance continuity."""
    if not a.lyrical_subject and not b.lyrical_subject:
        return 0.5
    subject_match = 1.0 if a.lyrical_subject == b.lyrical_subject else 0.3
    stance_match = 1.0 if a.narrator_stance == b.narrator_stance else 0.4
    return 0.6 * subject_match + 0.4 * stance_match


def score_groove_coherence(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score rhythmic/groove coherence."""
    groove_match = 1.0 if a.groove_feel == b.groove_feel else 0.4
    bpm_sim = bpm_score(a.bpm, b.bpm) if a.bpm and b.bpm else 0.5
    density_map = {"sparse": 0, "mid": 1, "dense": 2}
    da = density_map.get(a.density or "mid", 1)
    db_val = density_map.get(b.density or "mid", 1)
    density_sim = 1.0 - abs(da - db_val) / 2.0
    return 0.4 * groove_match + 0.35 * bpm_sim + 0.25 * density_sim


def score_era_mood_transition(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score era/aesthetic coherence."""
    return jaccard(a.era_mood, b.era_mood) if a.era_mood or b.era_mood else 0.5


def score_variety_transition(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score variety/contrast (inverse of similarity)."""
    # High variety score = tracks are DIFFERENT (good for discovery playlists)
    theme_sim = jaccard(a.themes, b.themes)
    vibe_sim = jaccard(a.vibes, b.vibes)
    instrument_sim = jaccard(a.instruments, b.instruments)
    similarity = 0.4 * theme_sim + 0.3 * vibe_sim + 0.3 * instrument_sim
    return 1.0 - similarity  # invert: different = high score


def score_artist_separation_transition(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score artist separation (1.0 if different artist, 0.0 if same)."""
    if a.artist.lower().strip() == b.artist.lower().strip():
        return 0.0
    return 1.0


def score_narrative_arc_transition(a: TrackMetadata, b: TrackMetadata) -> float:
    """Score narrative arc respect (placeholder - needs context from optimizer)."""
    # This scorer is a no-op at the pair level; narrative arc is enforced
    # by chapter boundary hard-breaks in the optimizer, not pairwise scoring.
    # Return neutral so it doesn't interfere when used in score_pair.
    return 0.5
```

- [ ] **Step 4: Create DIMENSION_SCORERS registry and refactor score_pair**

Replace the existing `score_pair` dispatch with the registry pattern:

```python
from typing import Callable

DIMENSION_SCORERS: dict[str, Callable[[TrackMetadata, TrackMetadata], float]] = {
    "narrative_arc": score_narrative_arc_transition,
    "energy_flow": energy_score,
    "mood_continuity": score_mood_continuity,
    "sonic_texture": score_sonic_texture,
    "lyrical_thread": score_lyrical_thread,
    "emotional_arc": emotional_arc_score,
    "groove_coherence": score_groove_coherence,
    "era_mood": score_era_mood_transition,
    "variety": score_variety_transition,
    "artist_separation": score_artist_separation_transition,
}

# Keep backward compatibility with existing dimension names
_LEGACY_DIMENSION_MAP = {
    "themes": "mood_continuity",
    "energy": "energy_flow",
    "instrumentation": "sonic_texture",
    "bpm": "groove_coherence",
    "narrative": "narrative_arc",
    "emotional_arc": "emotional_arc",
}


def score_pair(
    a: TrackMetadata,
    b: TrackMetadata,
    weights: dict[str, float],
) -> float:
    """Compute a weighted transition score between two tracks."""
    total_score = 0.0
    total_weight = 0.0

    for dimension, weight in weights.items():
        if weight <= 0:
            continue
        # Resolve legacy dimension names
        resolved = _LEGACY_DIMENSION_MAP.get(dimension, dimension)
        scorer = DIMENSION_SCORERS.get(resolved)
        if not scorer:
            continue
        score = scorer(a, b)
        total_score += weight * score
        total_weight += weight

    return total_score / total_weight if total_weight > 0 else 0.5
```

- [ ] **Step 5: Run all tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: ALL PASS (new tests + existing tests via backward compat)

- [ ] **Step 6: Commit**

```bash
git add tuneshift/sequencer/scoring.py tests/test_scoring_dimensions.py
git commit -m "feat(sequencer): full-spectrum dimension scorers with registry"
```

---

### Task 6: Integrate Weight Vector into Optimizer

**Files:**
- Modify: `tuneshift/sequencer/optimizer.py` (accept weights, use resolve_weights)
- Modify: `tuneshift/commands/order_cmd.py` (pass --weights flag)
- Test: `tests/test_optimizer_weights.py` (new)

- [ ] **Step 1: Write test for weights integration**

```python
# tests/test_optimizer_weights.py
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.optimizer import optimize_sequence
from tuneshift.sequencer.weights import PRESETS


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A", "energy": 0.5}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestOptimizerWeights:
    def test_accepts_new_weight_dimensions(self) -> None:
        tracks = [_track(i, energy=i * 0.1) for i in range(5)]
        result = optimize_sequence(
            tracks, weights=PRESETS["energy-wave"], arc="wave"
        )
        assert len(result) == 5
        assert {t.track_id for t in result} == {0, 1, 2, 3, 4}

    def test_narrative_queen_preset(self) -> None:
        tracks = [_track(i, emotional_intensity=i * 0.2) for i in range(5)]
        result = optimize_sequence(
            tracks, weights=PRESETS["narrative-queen"], arc="narrative"
        )
        assert len(result) == 5
```

- [ ] **Step 2: Run test to verify it works with current optimizer**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_optimizer_weights.py -x -q`
Expected: PASS (optimizer already accepts weights dict; new dimensions just get ignored by old code, but with the refactored score_pair they'll be used)

- [ ] **Step 3: Wire --weights into order command**

In `tuneshift/cli.py`, add to the `order` subparser:
```python
p_order.add_argument("--weights", help="Weight preset name or JSON")
```

In `tuneshift/commands/order_cmd.py`, resolve weights before calling sequence_playlist:
```python
from tuneshift.sequencer.weights import resolve_weights, PRESETS
import json

# In handle_order():
weights_arg = getattr(args, "weights", None)
if weights_arg:
    if weights_arg.startswith("{"):
        explicit_weights = json.loads(weights_arg)
    elif weights_arg in PRESETS:
        explicit_weights = PRESETS[weights_arg]
    else:
        print(f'Unknown preset: "{weights_arg}"')
        return 1
else:
    explicit_weights = None

# Pass to sequence_playlist or resolve from DB
```

- [ ] **Step 4: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tuneshift/sequencer/optimizer.py tuneshift/commands/order_cmd.py tuneshift/cli.py tests/test_optimizer_weights.py
git commit -m "feat(sequencer): wire weight vector into optimizer and order command"
```

---

## Chunk 3: Reconciliation v2 (Album Graph and Version Preferences)

### Task 7: Version Preference Model

**Files:**
- Create: `tuneshift/reconcile_prefs.py`
- Test: `tests/test_reconcile_prefs.py` (new)

- [ ] **Step 1: Write tests for preference resolution**

```python
# tests/test_reconcile_prefs.py
import pytest
from tuneshift.reconcile_prefs import (
    VersionPreferences,
    resolve_preferences,
    score_version,
)


class TestVersionPreferences:
    def test_default_preferences(self) -> None:
        prefs = VersionPreferences()
        assert "studio" in prefs.prefer
        assert "live" in prefs.avoid

    def test_score_preferred_version(self) -> None:
        prefs = VersionPreferences(prefer=["studio", "explicit"], avoid=["live"])
        score = score_version("Studio Album", 210, prefs, expected_duration=200)
        assert score > 0

    def test_score_avoided_version(self) -> None:
        prefs = VersionPreferences(prefer=["studio"], avoid=["live", "remix"])
        score = score_version("Live at Wembley", 300, prefs, expected_duration=200)
        assert score < 0

    def test_duration_tolerance(self) -> None:
        prefs = VersionPreferences(duration_tolerance_percent=15)
        # 50% longer than expected -> rejected
        score = score_version("Remaster", 300, prefs, expected_duration=200)
        assert score < -100


class TestResolvePreferences:
    def test_playlist_overrides_global(self) -> None:
        global_prefs = {"prefer": ["studio"], "avoid": ["live"]}
        playlist_prefs = {"prefer": ["live"], "avoid": []}
        resolved = resolve_preferences(global_prefs, playlist_prefs, None)
        assert "live" in resolved.prefer
        assert "live" not in resolved.avoid
```

- [ ] **Step 2: Implement reconcile_prefs.py**

```python
# tuneshift/reconcile_prefs.py
"""Version preference model for reconciliation."""
from dataclasses import dataclass, field


@dataclass
class VersionPreferences:
    prefer: list[str] = field(default_factory=lambda: ["studio", "original", "explicit"])
    avoid: list[str] = field(default_factory=lambda: ["live", "remix", "acoustic", "radio-edit", "clean"])
    duration_tolerance_percent: float = 15.0
    tiebreak_order: list[str] = field(default_factory=lambda: ["newest-remaster", "original-release"])


def resolve_preferences(
    global_prefs: dict | None,
    playlist_prefs: dict | None,
    track_prefs: dict | None,
) -> VersionPreferences:
    """Cascade preferences: track > playlist > global > defaults."""
    base = VersionPreferences()

    for layer in [global_prefs, playlist_prefs, track_prefs]:
        if not layer:
            continue
        if "prefer" in layer:
            base.prefer = layer["prefer"]
        if "avoid" in layer:
            base.avoid = layer["avoid"]
        if "duration_tolerance_percent" in layer:
            base.duration_tolerance_percent = layer["duration_tolerance_percent"]
        if "tiebreak_order" in layer:
            base.tiebreak_order = layer["tiebreak_order"]

    return base


def score_version(
    album_name: str,
    duration_seconds: float,
    prefs: VersionPreferences,
    expected_duration: float | None = None,
) -> float:
    """Score a track version based on preferences. Higher = better."""
    score = 0.0
    name_lower = album_name.lower()

    for keyword in prefs.prefer:
        if keyword.lower() in name_lower:
            score += 10.0

    for keyword in prefs.avoid:
        if keyword.lower() in name_lower:
            score -= 20.0

    if expected_duration and prefs.duration_tolerance_percent:
        tolerance = expected_duration * prefs.duration_tolerance_percent / 100.0
        deviation = abs(duration_seconds - expected_duration)
        if deviation > tolerance:
            score -= 200.0  # hard reject

    return score
```

- [ ] **Step 3: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_reconcile_prefs.py -x -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tuneshift/reconcile_prefs.py tests/test_reconcile_prefs.py
git commit -m "feat(reconcile): version preference model with cascading resolution"
```

---

### Task 8: Album Graph Search Enhancement

**Files:**
- Modify: `tuneshift/reconcile.py` (add album-first strategy, version scoring)
- Test: `tests/test_reconcile_album.py` (new)

- [ ] **Step 1: Write tests for album-graph reconciliation**

```python
# tests/test_reconcile_album.py
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest
from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.reconcile import reconcile_track


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test.db")


class TestAlbumGraphReconciliation:
    def test_finds_track_via_album_tracklist(self, db: Database) -> None:
        """When direct search fails, album tracklist search succeeds."""
        track = Track(title="Revolution!", artist="Left at London", album="Transgender Street Legend, Vol. 2")
        track_id = db.add_track(track)
        pid = db.create_playlist("Test")
        db.add_track_to_playlist(pid, track_id, 0)

        mock_client = MagicMock()
        # Direct search returns nothing
        mock_client.search_track.return_value = []
        # Album search finds the album
        mock_client.search_album.return_value = [
            MagicMock(platform_id="alb1", title="Transgender Street Legend, Vol. 2", artist="Left at London")
        ]
        # Album tracklist contains our track
        mock_client.get_album_tracks.return_value = [
            MagicMock(platform_id="trk99", title="Revolution!", artist="Left at London",
                     duration_seconds=195, album="Transgender Street Legend, Vol. 2"),
        ]

        result = reconcile_track(db, track_id, mock_client)
        assert result.platform_id == "trk99"
        assert result.match_type == "album_tracklist"
```

- [ ] **Step 2: Implement album tracklist strategy in reconcile.py**

Add a new strategy `_strategy_album_tracklist` that:
1. Gets the track's album name from DB
2. Searches for the album on platform
3. Fetches full tracklist
4. Fuzzy-matches track title against all tracks in the album
5. Applies version preferences to score candidates

Integration point: insert in the cascade between existing `_strategy_album_lookup` and `_strategy_title_artist`.

- [ ] **Step 3: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_reconcile_album.py tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tuneshift/reconcile.py tests/test_reconcile_album.py
git commit -m "feat(reconcile): album tracklist strategy with version preference scoring"
```

---

### Task 9: Global Preferences File and CLI

**Files:**
- Create: `tuneshift/commands/prefs_cmd.py`
- Modify: `tuneshift/cli.py`
- Test: `tests/test_prefs_cmd.py` (new)

- [ ] **Step 1: Write tests**

```python
# tests/test_prefs_cmd.py
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from tuneshift.db import Database
from tuneshift.commands.prefs_cmd import handle_prefs, load_global_preferences


class TestLoadGlobalPreferences:
    def test_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        prefs = load_global_preferences(tmp_path / "nonexistent.toml")
        assert prefs["version_preferences"]["prefer"] == ["studio", "original", "explicit"]

    def test_loads_from_toml(self, tmp_path: Path) -> None:
        config = tmp_path / "prefs.toml"
        config.write_text('[version_preferences]\nprefer = ["live", "explicit"]\n')
        prefs = load_global_preferences(config)
        assert prefs["version_preferences"]["prefer"] == ["live", "explicit"]
```

- [ ] **Step 2: Implement prefs_cmd.py**

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add tuneshift/commands/prefs_cmd.py tuneshift/cli.py tests/test_prefs_cmd.py
git commit -m "feat(cli): global preferences command for version preference management"
```

---

## Chunk 4: Curation Layer

### Task 10: Curation Scoring Engine

**Files:**
- Create: `tuneshift/curation/__init__.py`
- Create: `tuneshift/curation/scoring.py`
- Create: `tuneshift/curation/context.py`
- Test: `tests/test_curation_scoring.py` (new)

- [ ] **Step 1: Write tests for curation scoring**

```python
# tests/test_curation_scoring.py
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.scoring import (
    score_track_contribution,
    score_narrative_fit,
    score_mood_contribution,
    CURATION_SCORERS,
)


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestCurationScoring:
    def test_all_scorers_registered(self) -> None:
        expected = {"narrative_fit", "mood_contribution", "sonic_role", "energy_role", "uniqueness", "redundancy"}
        assert set(CURATION_SCORERS.keys()) == expected

    def test_narrative_fit_high_for_matching_track(self) -> None:
        ctx = PlaylistContext(
            goal="Trans fury and empowerment",
            narrative_sections=[{"name": "WRATH", "description": "Fury and defiance"}],
            mood_profile=None,
            all_tracks=[],
        )
        track = _track(1, lyrical_subject="identity", narrator_stance="defiant",
                      themes=["trans", "rage"], emotional_intensity=0.9)
        score = score_narrative_fit(track, ctx, [])
        assert score > 0.6

    def test_narrative_fit_low_for_unrelated_track(self) -> None:
        ctx = PlaylistContext(
            goal="Trans fury and empowerment",
            narrative_sections=[{"name": "WRATH", "description": "Fury and defiance"}],
            mood_profile=None,
            all_tracks=[],
        )
        track = _track(2, lyrical_subject="partying", narrator_stance="carefree",
                      themes=["summer", "beach"], emotional_intensity=0.3)
        score = score_narrative_fit(track, ctx, [])
        assert score < 0.4

    def test_missing_classification_returns_neutral(self) -> None:
        ctx = PlaylistContext(goal="Any", narrative_sections=[], mood_profile=None, all_tracks=[])
        track = _track(3)  # no classification data
        scores = score_track_contribution(track, ctx, [])
        # Must return all 6 scoring dimensions even without classification data
        expected_keys = {"narrative_fit", "mood_contribution", "sonic_role", "energy_role", "uniqueness", "redundancy"}
        assert set(scores.keys()) == expected_keys
        # Must not crash; neutral range acceptable for unclassified tracks
        assert all(isinstance(v, float) and 0.0 <= v <= 1.0 for v in scores.values())
```

- [ ] **Step 2: Run tests to verify failure**

- [ ] **Step 3: Implement curation scoring**

Create `tuneshift/curation/context.py`:
```python
"""Playlist context for curation decisions."""
from dataclasses import dataclass


@dataclass
class PlaylistContext:
    goal: str
    narrative_sections: list[dict]  # parsed section dicts
    mood_profile: dict | None
    all_tracks: list  # full track list for cross-comparison
```

Create `tuneshift/curation/scoring.py`:
```python
"""Curation scoring engine: rate each track's contribution to the playlist."""
from typing import Callable
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.curation.context import PlaylistContext


def score_narrative_fit(track: TrackMetadata, ctx: PlaylistContext, all_tracks: list) -> float:
    """Score how well this track serves the narrative goal."""
    if not ctx.goal and not ctx.narrative_sections:
        return 0.5
    if not track.lyrical_subject and not track.themes:
        return 0.5
    # Keyword overlap between goal text and track classification
    goal_words = set(ctx.goal.lower().split()) if ctx.goal else set()
    track_words = set()
    if track.themes:
        track_words.update(t.lower() for t in track.themes)
    if track.vibes:
        track_words.update(v.lower() for v in track.vibes)
    if track.lyrical_subject:
        track_words.add(track.lyrical_subject.lower())
    if track.narrator_stance:
        track_words.add(track.narrator_stance.lower())
    if not goal_words or not track_words:
        return 0.5
    overlap = len(goal_words & track_words)
    return min(1.0, overlap / max(3, len(goal_words) * 0.3))


def score_mood_contribution(track: TrackMetadata, ctx: PlaylistContext, all_tracks: list) -> float:
    """Score mood/atmosphere contribution."""
    if not track.emotional_intensity and not track.vibes:
        return 0.5
    # Basic: higher intensity = higher contribution for intense playlists
    return track.emotional_intensity if track.emotional_intensity is not None else 0.5


def score_sonic_role(track: TrackMetadata, ctx: PlaylistContext, all_tracks: list) -> float:
    """Score sonic texture contribution."""
    if not track.sonic_texture and not track.instruments:
        return 0.5
    # Tracks with unique sonic properties score higher
    return 0.6  # placeholder: will be enhanced with cross-track comparison


def score_energy_role(track: TrackMetadata, ctx: PlaylistContext, all_tracks: list) -> float:
    """Score energy curve contribution."""
    return track.energy if track.energy is not None else 0.5


def score_uniqueness(track: TrackMetadata, ctx: PlaylistContext, all_tracks: list) -> float:
    """Score how unique this track is vs others in the pool."""
    if not all_tracks or not track.themes:
        return 0.5
    # Compare against all other tracks
    similarities = []
    for other in all_tracks:
        if other.track_id == track.track_id:
            continue
        overlap = len(set(track.themes) & set(other.themes))
        total = len(set(track.themes) | set(other.themes))
        similarities.append(overlap / total if total else 0)
    if not similarities:
        return 0.5
    avg_sim = sum(similarities) / len(similarities)
    return 1.0 - avg_sim  # less similar = more unique


def score_redundancy(track: TrackMetadata, ctx: PlaylistContext, all_tracks: list) -> float:
    """Score redundancy (1.0 = not redundant, 0.0 = fully redundant)."""
    # Inverse of highest similarity to any single other track
    if not all_tracks:
        return 1.0
    max_sim = 0.0
    for other in all_tracks:
        if other.track_id == track.track_id:
            continue
        sim = 0.0
        if track.lyrical_subject and track.lyrical_subject == other.lyrical_subject:
            sim += 0.3
        if track.narrator_stance and track.narrator_stance == other.narrator_stance:
            sim += 0.2
        if track.themes and other.themes:
            overlap = len(set(track.themes) & set(other.themes))
            sim += 0.3 * (overlap / max(len(track.themes), 1))
        if track.energy is not None and other.energy is not None:
            sim += 0.2 * (1.0 - abs(track.energy - other.energy))
        max_sim = max(max_sim, sim)
    return 1.0 - max_sim


CURATION_SCORERS: dict[str, Callable[[TrackMetadata, PlaylistContext, list], float]] = {
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
    """Score a track's contribution across all curation dimensions."""
    return {name: scorer(track, context, all_tracks) for name, scorer in CURATION_SCORERS.items()}
```

- [ ] **Step 4: Run tests**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_curation_scoring.py -x -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tuneshift/curation/ tests/test_curation_scoring.py
git commit -m "feat(curation): scoring engine with 6-dimension contribution assessment"
```

---

### Task 11: Curation Trim/Analyze Logic

**Files:**
- Create: `tuneshift/curation/curator.py`
- Test: `tests/test_curator.py` (new)

- [ ] **Step 1: Write tests for trim and analyze**

```python
# tests/test_curator.py
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.curator import curate_trim, curate_analyze, CurationResult


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A", "duration_ms": 200000}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestCurateTrim:
    def test_trims_to_target_track_count(self) -> None:
        tracks = [_track(i, energy=0.5, themes=["rock"]) for i in range(20)]
        ctx = PlaylistContext(goal="Rock playlist", narrative_sections=[], mood_profile=None, all_tracks=tracks)
        constraints = {"track_count": {"target": 10, "tolerance": 2, "hard_limit": 12}}
        result = curate_trim(tracks, ctx, constraints)
        assert len(result.keep) <= 12
        assert len(result.keep) >= 8

    def test_respects_hard_limit(self) -> None:
        tracks = [_track(i, duration_ms=300000) for i in range(30)]  # 5 min each
        ctx = PlaylistContext(goal="Short playlist", narrative_sections=[], mood_profile=None, all_tracks=tracks)
        constraints = {"duration": {"target_minutes": 60, "tolerance_minutes": 5, "hard_limit_minutes": 65}}
        result = curate_trim(tracks, ctx, constraints)
        total_ms = sum(t.duration_ms or 0 for t in result.keep)
        assert total_ms <= 65 * 60 * 1000


class TestCurateAnalyze:
    def test_returns_coverage_report(self) -> None:
        tracks = [_track(i, themes=["trans", "fury"], emotional_intensity=0.8) for i in range(10)]
        ctx = PlaylistContext(goal="Trans fury", narrative_sections=[], mood_profile=None, all_tracks=tracks)
        report = curate_analyze(tracks, ctx)
        assert "scores" in report
        assert len(report["scores"]) == 10
```

- [ ] **Step 2: Implement curator.py**

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add tuneshift/curation/curator.py tests/test_curator.py
git commit -m "feat(curation): trim and analyze modes with constraint handling"
```

---

### Task 12: Curation CLI Command

**Files:**
- Create: `tuneshift/commands/curate_cmd.py`
- Modify: `tuneshift/cli.py`
- Test: `tests/test_curate_cmd.py` (new)

- [ ] **Step 1: Write tests**

- [ ] **Step 2: Implement curate_cmd.py**

CLI command `tuneshift curate <playlist>` with flags: `--trim`, `--fill`, `--analyze`, `--dry-run`, `--strategy`.

- [ ] **Step 3: Wire into CLI**

- [ ] **Step 4: Run tests**

- [ ] **Step 5: Commit**

```bash
git add tuneshift/commands/curate_cmd.py tuneshift/cli.py tests/test_curate_cmd.py
git commit -m "feat(cli): curate command with trim/fill/analyze modes"
```

---

### Task 13: Curation Gap Analysis and Fill Suggestions

**Files:**
- Create: `tuneshift/curation/gap_analyzer.py`
- Test: `tests/test_gap_analyzer.py` (new)

- [ ] **Step 1: Write tests for gap detection**

```python
# tests/test_gap_analyzer.py
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.curation.gap_analyzer import analyze_gaps, GapReport


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestGapAnalysis:
    def test_detects_thin_section(self) -> None:
        tracks = [_track(i, emotional_intensity=0.8) for i in range(3)]
        sections = [
            {"name": "OPENING", "start": 1, "end": 2, "description": "Setup"},
            {"name": "WRATH", "start": 3, "end": 10, "description": "Fury"},  # only has 1 track
        ]
        gaps = analyze_gaps(tracks, sections, goal="Fury playlist")
        assert any(g.section_name == "WRATH" for g in gaps)

    def test_detects_missing_transition(self) -> None:
        # High energy tracks with no cooldown before quiet section
        tracks = [
            _track(1, emotional_intensity=0.9, vibes=["explosive"]),
            _track(2, emotional_intensity=0.1, vibes=["peaceful"]),
        ]
        sections = [
            {"name": "WRATH", "start": 1, "end": 1, "description": "Fury"},
            {"name": "EXHALE", "start": 2, "end": 2, "description": "Recovery"},
        ]
        gaps = analyze_gaps(tracks, sections, goal="Arc playlist")
        assert any("transition" in g.gap_type for g in gaps)
```

- [ ] **Step 2: Implement gap_analyzer.py**

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add tuneshift/curation/gap_analyzer.py tests/test_gap_analyzer.py
git commit -m "feat(curation): gap analysis with section coverage and transition detection"
```

---

## Chunk 5: Integration and Polish

### Task 14: Wire Weights into Sequencer Workflow

**Files:**
- Modify: `tuneshift/commands/order_cmd.py` (load weights from DB)
- Modify: `tuneshift/sequencer/optimizer.py` (accept resolved weights)
- Test: `tests/test_weight_resolution.py` (new)

- [ ] **Step 1: Write tests for weight resolution**

```python
# tests/test_weight_resolution.py
import pytest
from tuneshift.sequencer.scoring import resolve_weights, PRESETS


class TestResolveWeights:
    def test_cli_weights_override_everything(self) -> None:
        cli = {"narrative_arc": 0.1}
        db = {"narrative_arc": 0.9, "energy_flow": 0.5}
        result = resolve_weights(cli_weights=cli, db_weights=db, preset_name=None)
        assert result["narrative_arc"] == 0.1  # CLI wins
        assert result["energy_flow"] == 0.5  # falls through to DB

    def test_db_weights_override_preset(self) -> None:
        db = {"narrative_arc": 0.8}
        result = resolve_weights(cli_weights=None, db_weights=db, preset_name="energy-wave")
        assert result["narrative_arc"] == 0.8  # DB wins over preset

    def test_preset_provides_base(self) -> None:
        result = resolve_weights(cli_weights=None, db_weights=None, preset_name="narrative-queen")
        assert result == PRESETS["narrative-queen"]

    def test_no_weights_returns_equal_blend(self) -> None:
        result = resolve_weights(cli_weights=None, db_weights=None, preset_name=None)
        # All dimensions present at equal weight
        assert len(result) == 10
        assert all(v == 0.5 for v in result.values())
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_weight_resolution.py -x -q`
Expected: FAIL (resolve_weights doesn't exist)

- [ ] **Step 3: Implement resolve_weights in scoring.py**

Add to `tuneshift/sequencer/scoring.py`:

```python
# Default equal-weight blend when nothing specified
DEFAULT_WEIGHTS: dict[str, float] = {dim: 0.5 for dim in DIMENSION_SCORERS}


def resolve_weights(
    cli_weights: dict[str, float] | None,
    db_weights: dict[str, float] | None,
    preset_name: str | None,
) -> dict[str, float]:
    """Resolve weight vector from cascade: CLI > DB > preset > default.

    Priority: CLI-provided values override DB, which overrides preset.
    Unspecified dimensions fall through to the next level.
    """
    # Start with base
    if preset_name and preset_name in PRESETS:
        base = dict(PRESETS[preset_name])
    else:
        base = dict(DEFAULT_WEIGHTS)

    # DB overrides base
    if db_weights:
        base.update(db_weights)

    # CLI overrides everything
    if cli_weights:
        base.update(cli_weights)

    return base
```

- [ ] **Step 4: Update order_cmd.py to use resolve_weights**

In `tuneshift/commands/order_cmd.py`, update the `order` command:
- Load `db_weights = db.get_weights(playlist_id)` before calling sequence
- Load `preset_name = db.get_playlist_type(playlist_id)` for preset lookup
- Call `resolve_weights(cli_weights=cli_weights, db_weights=db_weights, preset_name=preset_name)`
- Pass resolved weights to `sequence_playlist()`

- [ ] **Step 5: Update sequence_playlist signature**

In `tuneshift/sequencer/optimizer.py`, change `sequence_playlist` to accept `weights: dict[str, float] | None = None` parameter. When provided, pass to `score_pair` (which already dispatches to dimension scorers via registry from Task 5).

- [ ] **Step 6: Run full test suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git commit -m "feat: wire weight resolution into sequence_playlist workflow"
```

---

### Task 15: NarrativeSection Parser Enhancement

**Files:**
- Modify: `tuneshift/sequencer/intent.py` (produce NarrativeSection objects)
- Create: `tuneshift/sequencer/narrative_parser.py` (extract to dedicated module)
- Test: `tests/test_narrative_parser.py` (new)

- [ ] **Step 1: Write tests for NarrativeSection parsing**

```python
# tests/test_narrative_parser.py
import pytest
from tuneshift.sequencer.narrative_parser import parse_narrative, NarrativeSection


class TestParseNarrative:
    def test_parses_trans_wrath_narrative(self) -> None:
        narrative = """OPENING (1-2): The setup. A Southern preacher's sermon.
WRATH (11-18): Fury. Naming the pain directly.
ANTHEM (26): True Trans Soul Rebel. Fist in the air."""
        sections = parse_narrative(narrative)
        assert len(sections) == 3
        assert sections[0].name == "OPENING"
        assert sections[0].start_position == 1
        assert sections[0].end_position == 2
        assert sections[1].name == "WRATH"
        assert sections[1].implied_intensity > 0.7
        assert sections[2].name == "ANTHEM"
        assert sections[2].capacity == 1

    def test_handles_single_position_section(self) -> None:
        narrative = "EXHALE (19): Seven minutes of drone."
        sections = parse_narrative(narrative)
        assert sections[0].start_position == 19
        assert sections[0].end_position == 19
        assert sections[0].capacity == 1
```

- [ ] **Step 2: Implement narrative_parser.py**

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add tuneshift/sequencer/narrative_parser.py tests/test_narrative_parser.py tuneshift/sequencer/intent.py
git commit -m "feat(sequencer): dedicated narrative parser producing NarrativeSection objects"
```

---

### Task 16: Section Assignment in Optimizer

**Files:**
- Modify: `tuneshift/sequencer/optimizer.py` (add section assignment logic)
- Test: `tests/test_section_assignment.py` (new)

- [ ] **Step 1: Write tests for section assignment**

```python
# tests/test_section_assignment.py
import pytest
from tuneshift.sequencer.metadata import TrackMetadata
from tuneshift.sequencer.optimizer import assign_tracks_to_sections
from tuneshift.sequencer.narrative_parser import NarrativeSection


def _track(track_id: int, **kwargs) -> TrackMetadata:
    defaults = {"title": f"T{track_id}", "artist": "A"}
    defaults.update(kwargs)
    return TrackMetadata(track_id=track_id, **defaults)


class TestAssignTracksToSections:
    def test_assigns_intense_tracks_to_wrath(self) -> None:
        sections = [
            NarrativeSection(name="OPENING", start_position=1, end_position=2,
                           description="Gentle setup", implied_intensity=0.2,
                           implied_stance=None, capacity=2),
            NarrativeSection(name="WRATH", start_position=3, end_position=5,
                           description="Fury and defiance", implied_intensity=0.9,
                           implied_stance="defiant", capacity=3),
        ]
        tracks = [
            _track(1, emotional_intensity=0.1, narrator_stance="gentle"),
            _track(2, emotional_intensity=0.2, narrator_stance="peaceful"),
            _track(3, emotional_intensity=0.9, narrator_stance="defiant"),
            _track(4, emotional_intensity=0.8, narrator_stance="angry"),
            _track(5, emotional_intensity=0.7, narrator_stance="defiant"),
        ]
        assignments = assign_tracks_to_sections(tracks, sections, "Trans fury")
        # High-intensity tracks should be in WRATH
        wrath_ids = {t.track_id for t in assignments.get("WRATH", [])}
        assert 3 in wrath_ids
        assert 4 in wrath_ids
```

- [ ] **Step 2: Implement section assignment**

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add tuneshift/sequencer/optimizer.py tests/test_section_assignment.py
git commit -m "feat(sequencer): narrative section assignment algorithm"
```

---

### Task 17: End-to-End Integration Test

**Files:**
- Test: `tests/test_integration_pipeline.py` (new)

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration_pipeline.py
"""End-to-end test: full pipeline from playlist creation through curation and sequencing."""
from pathlib import Path
import pytest
from tuneshift.db import Database
from tuneshift.models import Track
from tuneshift.sequencer.optimizer import sequence_playlist
from tuneshift.curation.curator import curate_analyze


@pytest.fixture
def populated_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    pid = db.create_playlist("Integration Test")
    db.set_goal(pid, "Test playlist for integration")
    db.set_narrative(pid, "OPENING (1-3): Setup.\nWRATH (4-8): Peak fury.\nANTHEM (9-10): Close.")
    db.set_weights(pid, {"narrative_arc": 0.9, "mood_continuity": 0.7, "energy_flow": 0.3})

    for i in range(10):
        t = Track(title=f"Track {i}", artist=f"Artist {i % 3}")
        tid = db.add_track(t)
        db.add_track_to_playlist(pid, tid, i)
        db.update_track_metadata(tid, {
            "emotional_intensity": i * 0.1,
            "narrator_stance": "defiant" if i > 5 else "gentle",
            "themes": ["fury"] if i > 5 else ["peace"],
            "vibes": ["angry"] if i > 5 else ["calm"],
            "energy": i * 0.1,
        })
    return db


class TestFullPipeline:
    def test_sequence_uses_stored_weights(self, populated_db: Database) -> None:
        db = populated_db
        playlists = db.list_playlists()
        pid = playlists[0].id
        result = sequence_playlist(db, pid, arc="narrative")
        assert len(result) == 10

    def test_analyze_produces_coverage_report(self, populated_db: Database) -> None:
        from tuneshift.sequencer.metadata import get_track_metadata_map
        from tuneshift.curation.context import PlaylistContext

        db = populated_db
        playlists = db.list_playlists()
        pid = playlists[0].id
        track_ids = db.get_playlist_track_ids(pid)
        metadata_map = get_track_metadata_map(db, track_ids)
        tracks = [metadata_map[tid] for tid in track_ids if tid in metadata_map]

        ctx = PlaylistContext(
            goal=db.get_goal(pid),
            narrative_sections=[],
            mood_profile=None,
            all_tracks=tracks,
        )
        report = curate_analyze(tracks, ctx)
        assert "scores" in report
        assert len(report["scores"]) == 10
```

- [ ] **Step 2: Run integration test**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/test_integration_pipeline.py -x -q`
Expected: PASS

- [ ] **Step 3: Run full suite**

Run: `cd tools/tuneshift && .venv/bin/python -m pytest tests/ -x -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_pipeline.py
git commit -m "test: end-to-end integration test for full pipeline"
```

---

### Task 18: Update Repo Skill Documentation

**Files:**
- Modify: `.github/skills/tuneshift.md`

- [ ] **Step 1: Update skill doc with new commands and architecture**

Add curation layer, weight vector, and reconciliation v2 to the skill document.

- [ ] **Step 2: Commit**

```bash
git add .github/skills/tuneshift.md
git commit -m "docs: update repo skill with curation, weights, and reconciliation v2"
```

---

## Summary

| Chunk | Tasks | Focus |
|-------|-------|-------|
| 1: Foundation | 1-4 | Schema v7, DB methods, CLI (goal, weights), weight model |
| 2: Sequencer v2 | 5-6 | Dimension scorers, registry, optimizer integration |
| 3: Reconciliation v2 | 7-9 | Version preferences, album graph search, prefs CLI |
| 4: Curation | 10-13 | Scoring engine, trim/analyze, CLI, gap analysis |
| 5: Integration | 14-18 | Wire everything together, parser, section assignment, E2E test, docs |

**Total: 18 tasks, ~50 commits, estimated 90 minutes of implementation time.**

Each task is independently testable and produces a working commit. The dependency order ensures each chunk builds on the previous one's foundation.
