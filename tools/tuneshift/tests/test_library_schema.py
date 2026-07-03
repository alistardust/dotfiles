"""Tests for the library schema: artists, albums, and FK linkage."""

import json
import sqlite3

import pytest

from tuneshift.db import Database, _SCHEMA_VERSION
from tuneshift.models import Artist, Album


@pytest.fixture
def db(tmp_path):
    """Fresh database with schema applied."""
    db_path = tmp_path / "test.db"
    database = Database(db_path)
    yield database
    database.close()


class TestArtistsTable:
    def test_artists_table_exists(self, db):
        tables = {
            row[0]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "artists" in tables

    def test_artists_columns(self, db):
        cols = {
            row[1]
            for row in db.conn.execute("PRAGMA table_info(artists)").fetchall()
        }
        expected = {
            "id", "name", "norm_name", "sort_name", "bio", "identity",
            "tags", "identity_confidence", "genres", "origin",
            "active_start", "active_end", "mb_artist_id",
            "tidal_artist_id", "spotify_artist_uri",
            "lastfm_url", "wikipedia_url", "enrichment_sources",
            "verified", "enriched_at", "verified_at", "created_at", "updated_at",
        }
        assert expected.issubset(cols)

    def test_insert_and_get_artist(self, db):
        db.conn.execute(
            "INSERT INTO artists (name, norm_name) VALUES (?, ?)",
            ("Against Me!", "against me!"),
        )
        db.conn.commit()
        artist = db.get_artist_by_name("Against Me!")
        assert artist is not None
        assert artist.name == "Against Me!"
        assert artist.tags == []
        assert artist.verified is False

    def test_update_artist(self, db):
        db.conn.execute(
            "INSERT INTO artists (name, norm_name) VALUES (?, ?)",
            ("SOPHIE", "sophie"),
        )
        db.conn.commit()
        artist = db.get_artist_by_name("SOPHIE")
        db.update_artist(
            artist.id,
            bio="Scottish musician and producer.",
            tags=["trans", "woman", "electronic", "experimental"],
            identity={"gender_identity": "trans woman"},
            identity_confidence="confirmed",
            verified=1,
        )
        updated = db.get_artist(artist.id)
        assert updated.bio == "Scottish musician and producer."
        assert "trans" in updated.tags
        assert updated.identity["gender_identity"] == "trans woman"
        assert updated.identity_confidence == "confirmed"
        assert updated.verified is True

    def test_norm_name_unique(self, db):
        db.conn.execute(
            "INSERT INTO artists (name, norm_name) VALUES (?, ?)",
            ("Lady Gaga", "lady gaga"),
        )
        db.conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            db.conn.execute(
                "INSERT INTO artists (name, norm_name) VALUES (?, ?)",
                ("Lady GaGa", "lady gaga"),
            )


class TestAlbumsTable:
    def test_albums_table_exists(self, db):
        tables = {
            row[0]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "albums" in tables

    def test_albums_columns(self, db):
        cols = {
            row[1]
            for row in db.conn.execute("PRAGMA table_info(albums)").fetchall()
        }
        expected = {
            "id", "title", "norm_title", "artist_id", "release_date",
            "release_type", "edition", "genres", "mb_release_group_id",
            "tidal_album_id", "spotify_album_uri",
            "enriched_at", "created_at",
        }
        assert expected.issubset(cols)

    def test_insert_and_get_album(self, db):
        db.conn.execute(
            "INSERT INTO artists (name, norm_name) VALUES (?, ?)",
            ("Against Me!", "against me!"),
        )
        artist_id = db.conn.execute("SELECT id FROM artists WHERE norm_name = 'against me!'").fetchone()[0]
        db.conn.execute(
            "INSERT INTO albums (title, norm_title, artist_id) VALUES (?, ?, ?)",
            ("Transgender Dysphoria Blues", "transgender dysphoria blues", artist_id),
        )
        db.conn.commit()
        albums = db.get_albums_by_artist(artist_id)
        assert len(albums) == 1
        assert albums[0].title == "Transgender Dysphoria Blues"
        assert albums[0].artist_id == artist_id

    def test_album_fk_cascade(self, db):
        db.conn.execute(
            "INSERT INTO artists (name, norm_name) VALUES (?, ?)",
            ("Test Artist", "test artist"),
        )
        artist_id = db.conn.execute("SELECT id FROM artists WHERE norm_name = 'test artist'").fetchone()[0]
        db.conn.execute(
            "INSERT INTO albums (title, norm_title, artist_id) VALUES (?, ?, ?)",
            ("Test Album", "test album", artist_id),
        )
        db.conn.commit()
        db.conn.execute("PRAGMA foreign_keys = ON")
        db.conn.execute("DELETE FROM artists WHERE id = ?", (artist_id,))
        db.conn.commit()
        albums = db.conn.execute("SELECT COUNT(*) FROM albums WHERE artist_id = ?", (artist_id,)).fetchone()[0]
        assert albums == 0


class TestTracksFKLinkage:
    def test_tracks_have_artist_id_column(self, db):
        cols = {
            row[1]
            for row in db.conn.execute("PRAGMA table_info(tracks)").fetchall()
        }
        assert "artist_id" in cols
        assert "album_id" in cols

    def test_artists_for_playlist(self, db):
        # Set up artist -> track -> playlist linkage
        db.conn.execute("INSERT INTO artists (name, norm_name) VALUES ('A1', 'a1')")
        db.conn.execute("INSERT INTO artists (name, norm_name) VALUES ('A2', 'a2')")
        db.conn.execute("""
            INSERT INTO tracks (title, artist, album, norm_title, norm_artist, artist_id)
            VALUES ('T1', 'A1', NULL, 't1', 'a1', 1)
        """)
        db.conn.execute("""
            INSERT INTO tracks (title, artist, album, norm_title, norm_artist, artist_id)
            VALUES ('T2', 'A2', NULL, 't2', 'a2', 2)
        """)
        db.conn.execute("INSERT INTO playlists (name) VALUES ('Test PL')")
        db.conn.execute("INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (1, 1, 0)")
        db.conn.execute("INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (1, 2, 1)")
        db.conn.commit()

        artists = db.get_artists_for_playlist(1)
        names = {a.name for a in artists}
        assert names == {"A1", "A2"}


class TestMigrationFromV7:
    def test_v7_migrates_to_v8(self, tmp_path):
        """Simulate a v7 database and verify migration creates tables + populates."""
        db_path = tmp_path / "v7.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO schema_meta VALUES ('version', '7');
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL, artist TEXT NOT NULL, album TEXT,
                norm_title TEXT NOT NULL, norm_artist TEXT NOT NULL, norm_album TEXT,
                duration_seconds INTEGER, isrc TEXT, energy REAL, valence REAL,
                tempo REAL, key TEXT, themes TEXT, metadata JSON,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                mb_recording_id TEXT, mb_release_group_id TEXT,
                confidence_tier TEXT, confidence_score REAL, resolved_at TEXT
            );
            CREATE TABLE playlists (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                description TEXT, narrative TEXT, collection TEXT, goal TEXT,
                playlist_type TEXT, weights TEXT, mood_profile TEXT,
                curation_constraints TEXT, preferences TEXT,
                auto_reorder INTEGER DEFAULT 0, reorder_arc TEXT DEFAULT 'wave',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE playlist_tracks (
                playlist_id INTEGER, track_id INTEGER, position INTEGER,
                version_override TEXT, PRIMARY KEY (playlist_id, position)
            );
            CREATE TABLE playlist_pins (
                id INTEGER PRIMARY KEY, playlist_id INTEGER, track_id INTEGER,
                pin_type TEXT, group_id TEXT, group_order INTEGER,
                UNIQUE(playlist_id, track_id)
            );
            CREATE TABLE evidence (id INTEGER PRIMARY KEY, track_id INTEGER,
                source TEXT, evidence_type TEXT, confidence REAL, raw_data TEXT,
                is_current INTEGER DEFAULT 1, superseded_by INTEGER, created_at TEXT);
            CREATE TABLE platform_tracks (
                id INTEGER PRIMARY KEY, track_id INTEGER, platform TEXT,
                platform_track_id TEXT, platform_title TEXT, platform_artist TEXT,
                platform_album TEXT, match_score INTEGER, is_divergent INTEGER DEFAULT 0,
                divergence_note TEXT, status TEXT DEFAULT 'matched',
                user_approved INTEGER DEFAULT 0, unavailable INTEGER DEFAULT 0,
                created_at TEXT, UNIQUE(track_id, platform)
            );
            CREATE TABLE platform_playlists (
                id INTEGER PRIMARY KEY, playlist_id INTEGER, platform TEXT,
                platform_playlist_id TEXT, last_synced_at TEXT,
                UNIQUE(playlist_id, platform)
            );
            CREATE TABLE sync_log (
                id INTEGER PRIMARY KEY, playlist_id INTEGER, platform TEXT,
                action TEXT, tracks_added INTEGER DEFAULT 0,
                tracks_removed INTEGER DEFAULT 0, tracks_reordered INTEGER DEFAULT 0,
                tracks_unavailable INTEGER DEFAULT 0, divergences_flagged INTEGER DEFAULT 0,
                timestamp TEXT
            );
            INSERT INTO tracks (title, artist, album, norm_title, norm_artist, norm_album)
            VALUES ('Heroes', 'David Bowie', 'Heroes', 'heroes', 'david bowie', 'heroes');
            INSERT INTO tracks (title, artist, album, norm_title, norm_artist, norm_album)
            VALUES ('Ziggy Stardust', 'David Bowie', 'Ziggy Stardust', 'ziggy stardust', 'david bowie', 'ziggy stardust');
            INSERT INTO tracks (title, artist, album, norm_title, norm_artist, norm_album)
            VALUES ('Creep', 'Radiohead', 'Pablo Honey', 'creep', 'radiohead', 'pablo honey');
        """)
        conn.close()

        db = Database(db_path)

        # Version updated
        version = db.conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()[0]
        assert int(version) == _SCHEMA_VERSION

        # Artists created
        artist_count = db.conn.execute("SELECT COUNT(*) FROM artists").fetchone()[0]
        assert artist_count == 2  # David Bowie + Radiohead

        # Albums created
        album_count = db.conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
        assert album_count == 3  # Heroes, Ziggy Stardust, Pablo Honey

        # All tracks linked
        unlinked = db.conn.execute(
            "SELECT COUNT(*) FROM tracks WHERE artist_id IS NULL"
        ).fetchone()[0]
        assert unlinked == 0

        # Access methods work
        bowie = db.get_artist_by_name("David Bowie")
        assert bowie is not None
        assert bowie.name == "David Bowie"
        albums = db.get_albums_by_artist(bowie.id)
        assert len(albums) == 2

        db.close()
