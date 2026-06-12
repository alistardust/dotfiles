"""Playlist identity getter/setter tests for v7 columns."""

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


class TestCollection:
    def test_set_and_get_collection(self, db: Database) -> None:
        pid = db.create_playlist("Trans Wrath")
        db.set_collection(pid, "Pride")
        assert db.get_collection(pid) == "Pride"

    def test_list_collections(self, db: Database) -> None:
        p1 = db.create_playlist("Trans Wrath")
        p2 = db.create_playlist("Sapphic Softness")
        p3 = db.create_playlist("Desert Rock")
        db.set_collection(p1, "Pride")
        db.set_collection(p2, "Pride")
        db.set_collection(p3, "Laurel Canyon")
        collections = db.list_collections()
        assert "Pride" in collections
        assert "Laurel Canyon" in collections
        assert len(collections) == 2
