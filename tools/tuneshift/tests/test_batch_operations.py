"""Tests for batch operations: plan/apply model."""

import json

import pytest

from tuneshift.commands.batch_cmd import (
    BatchPlan,
    PlanOperation,
    extract_featured_artists,
    plan_dedupe,
    plan_rm_artist,
    render_plan,
)
from tuneshift.db import Database


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def _add_tracks(db, playlist_id, tracks):
    """Helper: add tracks to a playlist."""
    for i, (title, artist, album) in enumerate(tracks):
        track_id = db.insert_track(
            type("T", (), {
                "title": title, "artist": artist, "album": album,
                "duration_seconds": None, "isrc": None, "energy": None,
                "valence": None, "tempo": None, "key": None,
                "themes": [], "metadata": {},
            })()
        )
        db.conn.execute(
            "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
            (playlist_id, track_id, i),
        )
    db.conn.commit()


class TestFeaturedArtistExtraction:
    def test_feat_dot(self):
        assert extract_featured_artists("Pynk (feat. Grimes)") == ["Grimes"]

    def test_ft_dot(self):
        assert extract_featured_artists("Song (ft. Artist)") == ["Artist"]

    def test_featuring(self):
        assert extract_featured_artists("Song [featuring Big Boi]") == ["Big Boi"]

    def test_multiple_featured(self):
        result = extract_featured_artists("Hot Girl Summer (feat. Nicki Minaj & Ty Dolla $ign)")
        assert "Nicki Minaj" in result
        assert "Ty Dolla $ign" in result

    def test_no_featured(self):
        assert extract_featured_artists("Born This Way") == []

    def test_with_keyword(self):
        assert extract_featured_artists("Tightrope (with Big Boi)") == ["Big Boi"]


class TestPlanDedupe:
    def test_under_cap_no_changes(self, db):
        playlist_id = db.create_playlist("Test")
        _add_tracks(db, playlist_id, [
            ("Track 1", "Artist A", "Album"),
            ("Track 2", "Artist B", "Album"),
        ])
        ops = plan_dedupe(db, playlist_id, cap=1)
        assert ops == []

    def test_over_cap_removes_extras(self, db):
        playlist_id = db.create_playlist("Test")
        _add_tracks(db, playlist_id, [
            ("Track 1", "Artist A", "Album"),
            ("Track 2", "Artist A", "Album 2"),
            ("Track 3", "Artist A", "Album 3"),
        ])
        ops = plan_dedupe(db, playlist_id, cap=1)
        removes = [op for op in ops if op.action == "rm"]
        keeps = [op for op in ops if op.action == "keep"]
        assert len(removes) == 2
        assert len(keeps) == 1
        assert keeps[0].track_title == "Track 1"


class TestPlanRmArtist:
    def test_removes_primary_artist(self, db):
        playlist_id = db.create_playlist("Test")
        _add_tracks(db, playlist_id, [
            ("Track 1", "Keep Artist", "Album"),
            ("Track 2", "Remove Me", "Album"),
            ("Track 3", "Keep Artist", "Album"),
        ])
        ops = plan_rm_artist(db, playlist_id, "Remove Me")
        assert len(ops) == 1
        assert ops[0].track_title == "Track 2"

    def test_removes_featured_artist(self, db):
        playlist_id = db.create_playlist("Test")
        _add_tracks(db, playlist_id, [
            ("Song (feat. Bad Artist)", "Good Artist", "Album"),
            ("Clean Song", "Good Artist", "Album"),
        ])
        ops = plan_rm_artist(db, playlist_id, "Bad Artist")
        assert len(ops) == 1
        assert ops[0].track_title == "Song (feat. Bad Artist)"


class TestBatchPlan:
    def test_save_and_load(self, tmp_path):
        import tuneshift.commands.batch_cmd as batch_mod
        original_dir = batch_mod._PLAN_DIR
        batch_mod._PLAN_DIR = tmp_path / "plans"

        try:
            plan = BatchPlan(playlist_name="Test", playlist_id=1)
            plan.operations.append(PlanOperation(
                action="rm", track_title="Bad Song", track_artist="Bad Artist",
                track_id=42, reason="test removal",
            ))
            plan.save()

            loaded = BatchPlan.load()
            assert loaded is not None
            assert loaded.playlist_name == "Test"
            assert len(loaded.removals) == 1
            assert loaded.removals[0].track_title == "Bad Song"
        finally:
            batch_mod._PLAN_DIR = original_dir

    def test_discard(self, tmp_path):
        import tuneshift.commands.batch_cmd as batch_mod
        original_dir = batch_mod._PLAN_DIR
        batch_mod._PLAN_DIR = tmp_path / "plans"

        try:
            plan = BatchPlan(playlist_name="Test", playlist_id=1)
            plan.save()
            assert BatchPlan.discard() is True
            assert BatchPlan.load() is None
        finally:
            batch_mod._PLAN_DIR = original_dir


class TestRenderPlan:
    def test_render_includes_all_sections(self):
        plan = BatchPlan(playlist_name="Test", playlist_id=1)
        plan.operations = [
            PlanOperation(action="rm", track_title="A", track_artist="X", reason="bad"),
            PlanOperation(action="keep", track_title="B", track_artist="Y", reason="good"),
        ]
        output = render_plan(plan)
        assert "REMOVE (1):" in output
        assert "KEEP (1):" in output
        assert '"A" by X' in output
        assert "1 removal(s), 1 keep(s)" in output
