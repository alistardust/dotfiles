"""Tests for schema v2 migration and IdentityStore methods."""

import sqlite3

from tuneshift.db import Database


class TestSchemaV2Migration:
    def test_new_db_has_identity_columns(self, db):
        cols = {row[1] for row in db.conn.execute("PRAGMA table_info(tracks)").fetchall()}
        assert "mb_recording_id" in cols
        assert "mb_release_group_id" in cols
        assert "confidence_tier" in cols
        assert "confidence_score" in cols
        assert "resolved_at" in cols

    def test_evidence_table_exists(self, db):
        tables = {row[0] for row in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "evidence" in tables

    def test_schema_version_is_current(self, db):
        row = db.conn.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()
        assert int(row[0]) == 5

    def test_migration_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"
        db1 = Database(db_path)
        db1.close()
        db2 = Database(db_path)
        cols = {row[1] for row in db2.conn.execute("PRAGMA table_info(tracks)").fetchall()}
        assert "mb_recording_id" in cols
        db2.close()

    def test_v1_db_migrates_on_open(self, tmp_path):
        db_path = tmp_path / "v1.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO schema_meta VALUES ('version', '1');
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                album TEXT,
                isrc TEXT,
                duration_seconds INTEGER,
                norm_title TEXT,
                norm_artist TEXT,
                norm_album TEXT
            );
            INSERT INTO tracks (title, artist, album) VALUES ('Heroes', 'David Bowie', 'Heroes');
        """)
        conn.close()
        db = Database(db_path)
        cols = {row[1] for row in db.conn.execute("PRAGMA table_info(tracks)").fetchall()}
        assert "mb_recording_id" in cols
        row = db.conn.execute("SELECT title FROM tracks WHERE id = 1").fetchone()
        assert row[0] == "Heroes"
        db.close()

    def test_v2_db_migrates_to_v3(self, tmp_path):
        db_path = tmp_path / "v2.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO schema_meta VALUES ('version', '2');
            CREATE TABLE playlists (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL, artist TEXT NOT NULL, album TEXT,
                norm_title TEXT, norm_artist TEXT, norm_album TEXT,
                duration_seconds INTEGER, isrc TEXT, energy REAL, valence REAL,
                tempo REAL, key TEXT, themes TEXT, metadata JSON,
                created_at TEXT, updated_at TEXT,
                mb_recording_id TEXT, mb_release_group_id TEXT,
                confidence_tier TEXT, confidence_score REAL, resolved_at TEXT
            );
            CREATE TABLE evidence (id INTEGER PRIMARY KEY, track_id INTEGER,
                source TEXT, evidence_type TEXT, confidence REAL, raw_data TEXT,
                is_current INTEGER DEFAULT 1, superseded_by INTEGER, created_at TEXT);
            INSERT INTO playlists (name) VALUES ('Test Playlist');
        """)
        conn.close()
        db = Database(db_path)
        playlist_cols = {row[1] for row in db.conn.execute("PRAGMA table_info(playlists)").fetchall()}
        assert "auto_reorder" in playlist_cols
        assert "reorder_arc" in playlist_cols
        version = db.conn.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()[0]
        assert int(version) == 5
        db.close()


class TestIdentityStoreMethods:
    def test_get_resolution_state_unresolved(self, db_with_track):
        db, track_id = db_with_track
        tier, score, resolved_at = db.get_resolution_state(track_id)
        assert tier is None
        assert score is None
        assert resolved_at is None

    def test_store_resolution(self, db_with_track):
        db, track_id = db_with_track
        db.store_resolution(
            track_id=track_id,
            mb_recording_id="abc-123-def",
            mb_release_group_id="rg-456",
            confidence_tier="CONFIRMED",
            confidence_score=0.85,
            evidence=[
                {"source": "musicbrainz", "evidence_type": "isrc_lookup", "confidence": 0.85},
            ],
        )
        tier, score, resolved_at = db.get_resolution_state(track_id)
        assert tier == "CONFIRMED"
        assert score == 0.85
        assert resolved_at is not None

    def test_store_resolution_updates_isrc(self, db_with_track):
        db, track_id = db_with_track
        db.store_resolution(
            track_id=track_id,
            mb_recording_id="abc-123",
            mb_release_group_id=None,
            confidence_tier="VERIFIED",
            confidence_score=0.96,
            evidence=[{"source": "musicbrainz", "evidence_type": "isrc_lookup", "confidence": 0.96}],
            isrc="NEWISRC123456",
        )
        track = db.get_track(track_id)
        assert track.isrc == "NEWISRC123456"

    def test_store_failed_evidence(self, db_with_track):
        db, track_id = db_with_track
        db.store_failed_evidence(
            track_id=track_id,
            evidence=[
                {"source": "musicbrainz", "evidence_type": "text_search", "confidence": 0.3},
            ],
        )
        tier, score, _ = db.get_resolution_state(track_id)
        assert tier is None
        rows = db.conn.execute("SELECT * FROM evidence WHERE track_id = ?", (track_id,)).fetchall()
        assert len(rows) == 1

    def test_find_unresolved(self, db_with_track):
        db, track_id = db_with_track
        unresolved = db.find_unresolved()
        assert any(t.id == track_id for t in unresolved)

    def test_find_unresolved_excludes_resolved(self, db_with_track):
        db, track_id = db_with_track
        db.store_resolution(
            track_id=track_id,
            mb_recording_id="abc",
            mb_release_group_id=None,
            confidence_tier="CONFIRMED",
            confidence_score=0.85,
            evidence=[{"source": "musicbrainz", "evidence_type": "isrc_lookup", "confidence": 0.85}],
        )
        unresolved = db.find_unresolved()
        assert not any(t.id == track_id for t in unresolved)

    def test_find_unresolved_below_tier(self, db_with_track):
        db, track_id = db_with_track
        db.store_resolution(
            track_id=track_id,
            mb_recording_id="abc",
            mb_release_group_id=None,
            confidence_tier="PROBABLE",
            confidence_score=0.65,
            evidence=[{"source": "musicbrainz", "evidence_type": "text_search", "confidence": 0.65}],
        )
        below_confirmed = db.find_unresolved(below_tier="CONFIRMED")
        assert any(t.id == track_id for t in below_confirmed)


class TestEvidenceSupersession:
    def test_upgrade_supersedes_old_evidence(self, db_with_track):
        db, track_id = db_with_track
        # First resolution
        db.store_resolution(
            track_id=track_id,
            mb_recording_id="old-mb-id",
            mb_release_group_id=None,
            confidence_tier="PROBABLE",
            confidence_score=0.65,
            evidence=[{"source": "musicbrainz", "evidence_type": "text_search", "confidence": 0.65}],
        )
        old_evidence = db.conn.execute(
            "SELECT id, is_current FROM evidence WHERE track_id = ?", (track_id,)
        ).fetchall()
        assert len(old_evidence) == 1
        assert old_evidence[0][1] == 1  # is_current = 1

        # Second resolution (upgrade)
        db.store_resolution(
            track_id=track_id,
            mb_recording_id="new-mb-id",
            mb_release_group_id="rg-new",
            confidence_tier="CONFIRMED",
            confidence_score=0.88,
            evidence=[
                {"source": "musicbrainz", "evidence_type": "isrc_lookup", "confidence": 0.88},
            ],
        )
        # Old evidence superseded
        old_row = db.conn.execute(
            "SELECT is_current, superseded_by FROM evidence WHERE id = ?", (old_evidence[0][0],)
        ).fetchone()
        assert old_row[0] == 0  # is_current = 0
        assert old_row[1] is not None  # superseded_by points to new anchor

        # New evidence is current
        new_rows = db.conn.execute(
            "SELECT id, is_current FROM evidence WHERE track_id = ? AND is_current = 1", (track_id,)
        ).fetchall()
        assert len(new_rows) == 1
        assert new_rows[0][1] == 1

    def test_failed_evidence_does_not_supersede(self, db_with_track):
        db, track_id = db_with_track
        # First: successful resolution
        db.store_resolution(
            track_id=track_id,
            mb_recording_id="mb-id",
            mb_release_group_id=None,
            confidence_tier="CONFIRMED",
            confidence_score=0.85,
            evidence=[{"source": "musicbrainz", "evidence_type": "isrc_lookup", "confidence": 0.85}],
        )
        # Second: failed attempt
        db.store_failed_evidence(
            track_id=track_id,
            evidence=[{"source": "discogs", "evidence_type": "release_confirmation", "confidence": 0.05}],
        )
        # Original evidence remains current
        current = db.conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE track_id = ? AND is_current = 1", (track_id,)
        ).fetchone()[0]
        assert current == 2  # both are current (failed does not supersede)


class TestAutoReorder:
    def test_default_auto_reorder_off(self, db):
        db.create_playlist("Test Playlist")
        playlist = db.find_playlist_by_name("Test Playlist")
        assert playlist.auto_reorder is False
        assert playlist.reorder_arc == "wave"

    def test_set_auto_reorder_on(self, db):
        playlist_id = db.create_playlist("Test Playlist")
        db.set_auto_reorder(playlist_id, enabled=True, arc="rise")
        playlist = db.find_playlist_by_name("Test Playlist")
        assert playlist.auto_reorder is True
        assert playlist.reorder_arc == "rise"

    def test_set_auto_reorder_off(self, db):
        playlist_id = db.create_playlist("Test Playlist")
        db.set_auto_reorder(playlist_id, enabled=True, arc="wave")
        db.set_auto_reorder(playlist_id, enabled=False)
        playlist = db.find_playlist_by_name("Test Playlist")
        assert playlist.auto_reorder is False

    def test_list_playlists_includes_reorder_fields(self, db):
        db.create_playlist("Playlist A")
        db.create_playlist("Playlist B")
        db.set_auto_reorder(1, enabled=True, arc="descend")
        playlists = db.list_playlists()
        a = next(p for p in playlists if p.name == "Playlist A")
        b = next(p for p in playlists if p.name == "Playlist B")
        assert a.auto_reorder is True
        assert a.reorder_arc == "descend"
        assert b.auto_reorder is False
        assert b.reorder_arc == "wave"
