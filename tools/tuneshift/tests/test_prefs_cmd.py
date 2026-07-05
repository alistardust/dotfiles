from types import SimpleNamespace

import pytest

from tuneshift.commands.prefs_cmd import handle_prefs
from tuneshift.db import Database
from tuneshift.models import Track


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "prefs.db")
    yield database
    database.close()


def _args(action, key=None, value=None, target=None, *, playlist=None, track=None):
    return SimpleNamespace(
        action=action, key=key, value=value, target=target,
        playlist=playlist, track=track,
    )


class TestGlobalScope:
    def test_show_defaults_when_unset(self, db, capsys):
        assert handle_prefs(_args("show"), db) == 0
        out = capsys.readouterr().out
        # Typed cascade is authoritative; empty state renders "(none set)".
        assert "(none set)" in out
        assert "Effective version preferences (global" in out

    def test_set_and_show_prefer_list(self, db, capsys):
        assert handle_prefs(_args("set", "version.prefer", "radio, single, studio"), db) == 0
        assert db.get_global_preferences() == {"prefer": ["radio", "single", "studio"]}
        assert handle_prefs(_args("show"), db) == 0
        out = capsys.readouterr().out
        assert "prefer = radio, single, studio" in out

    def test_set_float_and_int(self, db):
        handle_prefs(_args("set", "version.duration_tolerance_percent", "12.5"), db)
        handle_prefs(_args("set", "version.min_lead", "8"), db)
        stored = db.get_global_preferences()
        assert stored["duration_tolerance_percent"] == 12.5
        assert stored["min_lead"] == 8

    def test_clear(self, db):
        handle_prefs(_args("set", "version.avoid", "live"), db)
        assert db.get_global_preferences() is not None
        assert handle_prefs(_args("clear"), db) == 0
        assert db.get_global_preferences() is None

    def test_rejects_bad_key(self, db, capsys):
        assert handle_prefs(_args("set", "prefer", "live"), db) == 1
        assert "version.<field>" in capsys.readouterr().out

    def test_rejects_unknown_field(self, db, capsys):
        assert handle_prefs(_args("set", "version.bogus", "x"), db) == 1
        assert "Unknown field" in capsys.readouterr().out

    def test_rejects_bad_number(self, db, capsys):
        assert handle_prefs(_args("set", "version.min_lead", "notanint"), db) == 1
        assert "Invalid value" in capsys.readouterr().out


class TestPlaylistScope:
    def test_set_writes_playlist_layer(self, db):
        pid = db.create_playlist("Party")
        assert handle_prefs(_args("set", "version.avoid", "live,acoustic", playlist="Party"), db) == 0
        assert db.get_preferences(pid) == {"avoid": ["live", "acoustic"]}
        # Global untouched.
        assert db.get_global_preferences() is None

    def test_unknown_playlist_errors(self, db, capsys):
        assert handle_prefs(_args("show", playlist="Nope"), db) == 1
        assert "not found" in capsys.readouterr().out

    def test_effective_stacks_global_then_playlist(self, db, capsys):
        db.create_playlist("Live Sets")
        handle_prefs(_args("set", "version.prefer", "studio", playlist=None), db)  # global
        handle_prefs(_args("set", "version.prefer", "live", playlist="Live Sets"), db)
        capsys.readouterr()
        handle_prefs(_args("show", playlist="Live Sets"), db)
        out = capsys.readouterr().out
        # Playlist layer overrides global in the effective view.
        assert "prefer                      = live" in out


class TestTrackScope:
    def test_set_writes_track_global_layer(self, db):
        # `--track` alone (no `--playlist`) targets the playlist-agnostic
        # per-track scope, stored under a NULL playlist_id.
        tid = db.add_track(Track(title="Song", artist="Artist", album="Album"))
        assert handle_prefs(_args("set", "spatial", "prefer", "atmos", track=tid), db) == 0
        assert db.get_track_global_prefs(tid) == [
            {"criterion": "spatial", "strength": "prefer", "target": "atmos"}
        ]
        # Not stored as a playlist-specific row.
        assert db.get_global_preferences() is None

    def test_legacy_per_track_is_retired(self, db, capsys):
        tid = db.add_track(Track(title="Song", artist="Artist", album="Album"))
        assert handle_prefs(_args("set", "version.prefer", "expanded", track=tid), db) == 1
        assert "retired" in capsys.readouterr().out

    def test_unknown_track_errors(self, db, capsys):
        assert handle_prefs(_args("show", track=99999), db) == 1
        assert "not found" in capsys.readouterr().out


class TestTypedGrammar:
    """The general (criterion, strength, target) model at all three scopes."""

    def test_global_typed_set_writes_criteria(self, db, capsys):
        assert handle_prefs(_args("set", "spatial", "prefer", "atmos"), db) == 0
        stored = db.get_global_preferences()
        assert stored["criteria"] == [
            {"criterion": "spatial", "strength": "prefer", "target": "atmos"}
        ]
        assert "Set spatial prefer atmos (global)." in capsys.readouterr().out

    def test_playlist_typed_set_writes_playlist_criteria(self, db):
        pid = db.create_playlist("Spatial")
        assert handle_prefs(
            _args("set", "spatial", "require", "atmos", playlist="Spatial"), db
        ) == 0
        assert db.get_preferences(pid)["criteria"] == [
            {"criterion": "spatial", "strength": "require", "target": "atmos"}
        ]
        # Global untouched.
        assert db.get_global_preferences() is None

    def test_playlist_track_typed_set_writes_triple_table(self, db):
        from tuneshift.models import Track
        pid = db.create_playlist("Spatial")
        tid = db.add_track(Track(title="S", artist="A", album="Al"))
        assert handle_prefs(
            _args("set", "spatial", "prefer", "atmos", playlist="Spatial", track=tid),
            db,
        ) == 0
        assert db.get_playlist_track_prefs(pid, tid) == [
            {"criterion": "spatial", "strength": "prefer", "target": "atmos"}
        ]

    def test_track_without_playlist_is_track_global(self, db):
        from tuneshift.models import Track
        tid = db.add_track(Track(title="S", artist="A", album="Al"))
        assert handle_prefs(
            _args("set", "spatial", "prefer", "atmos", track=tid), db
        ) == 0
        # Stored as a playlist-agnostic per-track row (NULL playlist_id).
        assert db.get_track_global_prefs(tid) == [
            {"criterion": "spatial", "strength": "prefer", "target": "atmos"}
        ]

    def test_set_rejects_unknown_criterion(self, db, capsys):
        assert handle_prefs(_args("set", "bogus", "prefer", "atmos"), db) == 1
        assert "Unknown criterion" in capsys.readouterr().out

    def test_set_warns_on_unknown_structured_target(self, db, capsys):
        assert handle_prefs(_args("set", "spatial", "prefer", "quadraphonic"), db) == 0
        out = capsys.readouterr().out
        assert "may never match" in out

    def test_set_replaces_same_polarity_at_same_scope(self, db):
        # Re-setting the same (criterion, target) with the SAME polarity
        # replaces the strength in place (prefer -> require).
        handle_prefs(_args("set", "spatial", "prefer", "atmos"), db)
        handle_prefs(_args("set", "spatial", "require", "atmos"), db)
        criteria = db.get_global_preferences()["criteria"]
        assert criteria == [
            {"criterion": "spatial", "strength": "require", "target": "atmos"}
        ]

    def test_set_rejects_opposite_polarity_conflict(self, db, capsys):
        # Opposite polarity on the same (criterion, target) at the same scope is
        # a contradiction and is rejected loudly (FL3 conflict rule).
        handle_prefs(_args("set", "spatial", "prefer", "atmos"), db)
        capsys.readouterr()
        assert handle_prefs(_args("set", "spatial", "avoid", "atmos"), db) == 1
        assert "Conflict" in capsys.readouterr().out
        # Original pref is preserved.
        assert db.get_global_preferences()["criteria"] == [
            {"criterion": "spatial", "strength": "prefer", "target": "atmos"}
        ]

    def test_multi_target_coexist_at_same_scope(self, db):
        # Two different targets on one axis coexist (the historical overwrite bug).
        handle_prefs(_args("set", "content", "avoid", "karaoke"), db)
        handle_prefs(_args("set", "content", "avoid", "instrumental"), db)
        targets = {c["target"] for c in db.get_global_preferences()["criteria"]}
        assert targets == {"karaoke", "instrumental"}

    def test_unset_removes_global_criterion(self, db, capsys):
        handle_prefs(_args("set", "spatial", "prefer", "atmos"), db)
        assert handle_prefs(_args("unset", "spatial"), db) == 0
        assert "Unset spatial (global)." in capsys.readouterr().out
        # criteria key dropped; global blob cleared when nothing remains.
        assert db.get_global_preferences() is None

    def test_unset_missing_criterion_reports_none(self, db, capsys):
        assert handle_prefs(_args("unset", "spatial"), db) == 0
        assert "No \"spatial\" preference set" in capsys.readouterr().out

    def test_unset_removes_playlist_track_row(self, db):
        from tuneshift.models import Track
        pid = db.create_playlist("Spatial")
        tid = db.add_track(Track(title="S", artist="A", album="Al"))
        handle_prefs(
            _args("set", "spatial", "prefer", "atmos", playlist="Spatial", track=tid), db
        )
        assert handle_prefs(
            _args("unset", "spatial", playlist="Spatial", track=tid), db
        ) == 0
        assert db.get_playlist_track_prefs(pid, tid) == []

    def test_list_shows_precedence_and_marks_effective_winner(self, db, capsys):
        db.create_playlist("Spatial")
        tid = db.add_track(__import__("tuneshift.models", fromlist=["Track"]).Track(
            title="S", artist="A", album="Al"))
        handle_prefs(_args("set", "spatial", "avoid", "atmos"), db)  # global
        handle_prefs(
            _args("set", "spatial", "require", "atmos", playlist="Spatial", track=tid), db
        )
        capsys.readouterr()
        assert handle_prefs(
            _args("list", playlist="Spatial", track=tid), db
        ) == 0
        out = capsys.readouterr().out
        assert "[global]" in out and "[playlist-track]" in out
        # The global avoid is overridden by the more-specific require.
        assert "(overridden)" in out
        assert "* spatial require atmos" in out


class TestLegacyGrammarStillWorks:
    def test_legacy_prefer_list_unchanged(self, db):
        assert handle_prefs(_args("set", "version.prefer", "studio,live"), db) == 0
        assert db.get_global_preferences() == {"prefer": ["studio", "live"]}

    def test_show_lists_typed_criteria_too(self, db, capsys):
        handle_prefs(_args("set", "spatial", "prefer", "atmos"), db)
        assert handle_prefs(_args("show"), db) == 0
        out = capsys.readouterr().out
        # `show` renders the authoritative typed cascade.
        assert "[global]" in out
        assert "spatial prefer atmos" in out
