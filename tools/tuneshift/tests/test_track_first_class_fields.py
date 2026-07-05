"""Task 1.3: first-class metadata columns + provenance on ``tracks`` (AC-D3/D4).

New canonical metadata fields (album_artist, album_type, label, dates, audio_modes,
audio_quality, tidal_version, language, composer, availability, quarantine_*) become
first-class columns the matching path can read — not buried in the metadata JSON blob.
Each enrichable field records provenance (source + timestamp) so later precedence and
idempotency rules (AC-D4) have something to reason over.
"""

import sqlite3

import pytest

from tuneshift.db import Database, _SCHEMA_VERSION
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


NEW_COLUMNS = {
    "album_artist",
    "album_type",
    "label",
    "recording_date",
    "release_date",
    "remaster_year",
    "audio_modes",
    "audio_quality",
    "tidal_version",
    "language",
    "composer",
    "availability",
    "quarantine_state",
    "quarantine_reason",
    "field_provenance",
}


def test_fresh_db_has_first_class_columns(db):
    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(tracks)").fetchall()}
    missing = NEW_COLUMNS - cols
    assert not missing, f"fresh schema missing columns: {missing}"


def test_schema_version_bumped(db):
    row = db.conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'version'"
    ).fetchone()
    assert int(row[0]) == _SCHEMA_VERSION
    assert _SCHEMA_VERSION >= 15


def test_migration_adds_columns_to_legacy_db(tmp_path):
    """A v14 DB (pre-first-class-columns) migrates up idempotently."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
            album TEXT, norm_title TEXT NOT NULL, norm_artist TEXT NOT NULL,
            norm_album TEXT, duration_seconds INTEGER, isrc TEXT, energy REAL,
            valence REAL, tempo REAL, key TEXT, themes TEXT, metadata JSON,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO schema_meta (key, value) VALUES ('version', '14');
        """
    )
    conn.commit()
    conn.close()

    db = Database(path)
    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(tracks)").fetchall()}
    assert NEW_COLUMNS <= cols
    assert int(
        db.conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
    ) == _SCHEMA_VERSION
    db.close()


def test_set_track_fields_persists_and_records_provenance(db):
    tid = db.insert_track(Track(title="Flowers", artist="Miley Cyrus", album="Endless Summer Vacation"))
    db.set_track_fields(
        tid,
        {"album_type": "ALBUM", "audio_modes": ["DOLBY_ATMOS"], "label": "Columbia"},
        source="tidal",
    )
    track = db.get_track(tid)
    assert track.album_type == "ALBUM"
    assert track.audio_modes == ["DOLBY_ATMOS"]
    assert track.label == "Columbia"

    prov = track.field_provenance
    assert prov["album_type"]["source"] == "tidal"
    assert prov["audio_modes"]["source"] == "tidal"
    assert "at" in prov["album_type"] and prov["album_type"]["at"]


def test_set_track_fields_is_incremental(db):
    tid = db.insert_track(Track(title="A", artist="B", album="C"))
    db.set_track_fields(tid, {"album_type": "SINGLE"}, source="tidal")
    db.set_track_fields(tid, {"label": "XL"}, source="musicbrainz")
    track = db.get_track(tid)
    assert track.album_type == "SINGLE"
    assert track.label == "XL"
    assert track.field_provenance["album_type"]["source"] == "tidal"
    assert track.field_provenance["label"]["source"] == "musicbrainz"


def test_matching_path_reads_new_column(db):
    """AC-D3 read-proof: the field flows through get_track — the exact loader the
    reconcile/matching path uses (reconcile.py:591) — not merely PRAGMA existence."""
    tid = db.insert_track(Track(title="There You'll Be", artist="Faith Hill", album="Pearl Harbor"))
    db.set_track_fields(tid, {"album_type": "COMPILATION"}, source="tidal")
    loaded = db.get_track(tid)
    assert loaded.album_type == "COMPILATION"
