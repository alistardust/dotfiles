"""Tests for identity resolution database layer."""

import sqlite3
from pathlib import Path

import pytest

from tidal_importer.identity.db import IdentityDB
from tidal_importer.identity.models import Album, Artist, Evidence, Recording


@pytest.fixture
def db(tmp_path):
    return IdentityDB(tmp_path / "test.db")


class TestSchema:
    def test_creates_all_tables(self, db):
        tables = db.list_tables()
        expected = {
            "artists", "recordings", "isrcs", "albums", "releases",
            "platform_tracks", "recording_albums", "resolution_evidence",
            "resolution_candidates", "playlists", "playlist_tracks",
            "recording_preferences", "audio_features",
        }
        assert expected.issubset(set(tables))

    def test_wal_mode_enabled(self, db):
        result = db.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"

    def test_foreign_keys_enabled(self, db):
        result = db.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1

    def test_schema_version(self, db):
        result = db.execute("PRAGMA user_version").fetchone()
        assert result[0] == 1


class TestArtistCRUD:
    def test_upsert_new(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA", mb_artist_id="mb-abba"))
        row = db.get_artist("a1")
        assert row.name == "ABBA"
        assert row.mb_artist_id == "mb-abba"

    def test_upsert_update(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA"))
        db.upsert_artist(Artist(id="a1", name="ABBA", mb_artist_id="mb-updated"))
        row = db.get_artist("a1")
        assert row.mb_artist_id == "mb-updated"

    def test_get_by_mb_id(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA", mb_artist_id="mb-abba"))
        row = db.get_artist_by_mb_id("mb-abba")
        assert row.id == "a1"

    def test_get_not_found(self, db):
        assert db.get_artist("nonexistent") is None


class TestRecordingCRUD:
    def test_upsert_and_get(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA"))
        db.upsert_recording(Recording(id="r1", title="Dancing Queen", artist_id="a1", duration_ms=231000))
        row = db.get_recording("r1")
        assert row.title == "Dancing Queen"
        assert row.duration_ms == 231000

    def test_get_by_mb_id(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA"))
        db.upsert_recording(Recording(id="r1", title="DQ", artist_id="a1", mb_recording_id="mb-r1"))
        row = db.get_recording_by_mb_id("mb-r1")
        assert row.id == "r1"


class TestAlbumCRUD:
    def test_upsert_and_get(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA"))
        album = Album(id="alb1", title="Arrival", artist_id="a1",
                      primary_type="Album", secondary_types=[], release_year=1976)
        db.upsert_album(album)
        row = db.get_album("alb1")
        assert row.title == "Arrival"
        assert row.is_compilation is False

    def test_secondary_types_as_json(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA"))
        album = Album(id="alb2", title="Gold", artist_id="a1",
                      primary_type="Album", secondary_types=["Compilation"])
        db.upsert_album(album)
        row = db.get_album("alb2")
        assert row.secondary_types == ["Compilation"]
        assert row.is_compilation is True


class TestEvidenceCRUD:
    def test_add_and_get(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA"))
        db.upsert_recording(Recording(id="r1", title="DQ", artist_id="a1"))
        db.add_evidence(Evidence(id="ev1", recording_id="r1", source="musicbrainz",
                                 evidence_type="isrc_match", confidence=0.97))
        rows = db.get_evidence_for_recording("r1")
        assert len(rows) == 1
        assert rows[0].confidence == 0.97

    def test_supersede(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA"))
        db.upsert_recording(Recording(id="r1", title="DQ", artist_id="a1"))
        db.add_evidence(Evidence(id="ev1", recording_id="r1", source="musicbrainz",
                                 evidence_type="isrc_match", confidence=0.92))
        db.supersede_evidence("ev1", "ev2")
        db.add_evidence(Evidence(id="ev2", recording_id="r1", source="musicbrainz",
                                 evidence_type="isrc_match", confidence=0.97))
        current = db.get_current_evidence_for_recording("r1")
        assert len(current) == 1
        assert current[0].id == "ev2"


class TestUniqueConstraints:
    def test_duplicate_mb_artist_rejected(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA", mb_artist_id="mb-1"))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO artists (id, name, mb_artist_id) VALUES (?, ?, ?)",
                ("a2", "Other", "mb-1"),
            )

    def test_duplicate_platform_track_rejected(self, db):
        db.upsert_artist(Artist(id="a1", name="ABBA"))
        db.upsert_recording(Recording(id="r1", title="DQ", artist_id="a1"))
        db.execute(
            "INSERT INTO platform_tracks (id, recording_id, platform, platform_track_id) "
            "VALUES (?, ?, ?, ?)", ("pt1", "r1", "tidal", "12345"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO platform_tracks (id, recording_id, platform, platform_track_id) "
                "VALUES (?, ?, ?, ?)", ("pt2", "r1", "tidal", "12345"),
            )
