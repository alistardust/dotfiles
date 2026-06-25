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


class TestMultiArtistCreditSplitting:
    def test_comma_split(self):
        from tuneshift.commands.batch_cmd import split_artist_credits
        assert split_artist_credits("Drake, 21 Savage") == ["Drake", "21 Savage"]

    def test_ampersand_split(self):
        from tuneshift.commands.batch_cmd import split_artist_credits
        assert split_artist_credits("Simon & Garfunkel") == ["Simon", "Garfunkel"]

    def test_and_split(self):
        from tuneshift.commands.batch_cmd import split_artist_credits
        assert split_artist_credits("Hall and Oates") == ["Hall", "Oates"]

    def test_single_artist_no_split(self):
        from tuneshift.commands.batch_cmd import split_artist_credits
        assert split_artist_credits("Against Me!") == ["Against Me!"]


class TestBanEnforcementAtAdd:
    def test_banned_primary_artist_blocked(self, db):
        db.ban_artist("Nicki Minaj", "transphobe")
        from tuneshift.commands.batch_cmd import check_track_against_bans
        result = check_track_against_bans(db, "Super Bass", "Nicki Minaj")
        assert result == "Nicki Minaj"

    def test_banned_featured_artist_blocked(self, db):
        db.ban_artist("Nicki Minaj", "transphobe")
        from tuneshift.commands.batch_cmd import check_track_against_bans
        result = check_track_against_bans(db, "Hot Girl Summer (feat. Nicki Minaj & Ty Dolla $ign)", "Megan Thee Stallion")
        assert result == "Nicki Minaj"

    def test_banned_multi_credit_blocked(self, db):
        db.ban_artist("Drake", "test")
        from tuneshift.commands.batch_cmd import check_track_against_bans
        result = check_track_against_bans(db, "Rich Flex", "Drake, 21 Savage")
        assert result == "Drake"

    def test_unbanned_artist_passes(self, db):
        from tuneshift.commands.batch_cmd import check_track_against_bans
        result = check_track_against_bans(db, "Good Song", "Good Artist")
        assert result is None

    def test_diacritic_normalization(self, db):
        db.ban_artist("Beyonce", "test")
        # Should match with accent
        assert db.is_artist_banned("Beyonce")


class TestAtomicApplyAndUndo:
    def test_apply_records_only_executed_ops(self, db):
        from tuneshift.commands.batch_cmd import apply_plan, BatchPlan, PlanOperation
        playlist_id = db.create_playlist("Test")
        _add_tracks(db, playlist_id, [
            ("Track 1", "Artist A", "Album"),
            ("Track 2", "Artist B", "Album"),
        ])
        tracks = db.get_playlist_tracks(playlist_id)

        plan = BatchPlan(playlist_name="Test", playlist_id=playlist_id)
        plan.operations = [
            PlanOperation(action="rm", track_title="Track 1", track_artist="Artist A",
                          track_id=tracks[0].id, position=0, previous_position=0),
            PlanOperation(action="rm", track_title="Nonexistent", track_artist="Nobody",
                          track_id=99999, position=5, previous_position=5),
        ]
        removed, added = apply_plan(db, plan)
        assert removed == 1  # only one actually existed

        # History should record 1 op, not 2
        history = db.get_batch_history(playlist_id)
        assert len(history) == 1
        recorded_ops = json.loads(history[0]["plan_json"])["operations"]
        assert len(recorded_ops) == 1
        assert recorded_ops[0]["track"] == "Track 1"

    def test_undo_restores_removed_track(self, db):
        from tuneshift.commands.batch_cmd import apply_plan, undo_batch, BatchPlan, PlanOperation
        playlist_id = db.create_playlist("Test")
        _add_tracks(db, playlist_id, [
            ("Track 1", "Artist A", "Album"),
            ("Track 2", "Artist B", "Album"),
            ("Track 3", "Artist C", "Album"),
        ])
        tracks = db.get_playlist_tracks(playlist_id)

        plan = BatchPlan(playlist_name="Test", playlist_id=playlist_id)
        plan.operations = [
            PlanOperation(action="rm", track_title="Track 2", track_artist="Artist B",
                          track_id=tracks[1].id, position=1, previous_position=1),
        ]
        apply_plan(db, plan)

        # Verify removal
        remaining = db.get_playlist_tracks(playlist_id)
        assert len(remaining) == 2
        assert all(t.title != "Track 2" for t in remaining)

        # Undo
        result = undo_batch(db)
        assert result is True

        # Verify restoration
        restored = db.get_playlist_tracks(playlist_id)
        assert len(restored) == 3
        assert any(t.title == "Track 2" for t in restored)


class TestPlanFileParsing:
    def test_parse_removes_and_adds(self):
        from tuneshift.commands.batch_cmd import parse_plan_file
        content = "- Bad Song - Bad Artist\n+ Good Song - Good Artist\n# comment\n"
        ops = parse_plan_file(content)
        assert len(ops) == 2
        assert ops[0].action == "rm"
        assert ops[0].track_title == "Bad Song"
        assert ops[1].action == "add"
        assert ops[1].track_artist == "Good Artist"

    def test_parse_section_move(self):
        from tuneshift.commands.batch_cmd import parse_plan_file
        content = "= My Song - Artist -> sec:WRATH\n"
        ops = parse_plan_file(content)
        assert len(ops) == 1
        assert ops[0].action == "assign_section"
        assert ops[0].section_name == "WRATH"

    def test_parse_position_move(self):
        from tuneshift.commands.batch_cmd import parse_plan_file
        content = "= My Song - Artist -> pos:7\n"
        ops = parse_plan_file(content)
        assert len(ops) == 1
        assert ops[0].position == 7

    def test_parse_section_with_position(self):
        from tuneshift.commands.batch_cmd import parse_plan_file
        content = "= My Song - Artist -> sec:WRATH:3\n"
        ops = parse_plan_file(content)
        assert len(ops) == 1
        assert ops[0].section_name == "WRATH"
        assert ops[0].position == 3
