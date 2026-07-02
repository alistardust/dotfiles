"""Security + correctness tests for Database.update_artist.

update_artist builds ``SET <col> = ?`` by interpolating the keyword name as a
SQL identifier. Unknown/attacker-controlled names must be rejected rather than
spliced into the statement.
"""
import tempfile
from pathlib import Path

import pytest

from tuneshift.db import Database


def _db_with_artist() -> tuple[Database, int]:
    db = Database(Path(tempfile.mkdtemp()) / "artists.db")
    cur = db.conn.execute(
        "INSERT INTO artists (name, norm_name) VALUES (?, ?)",
        ("A Tribe Called Quest", "a tribe called quest"),
    )
    db.conn.commit()
    return db, cur.lastrowid


def test_update_artist_known_column_updates():
    db, artist_id = _db_with_artist()
    db.update_artist(artist_id, bio="Hip hop group", verified=True)
    artist = db.get_artist(artist_id)
    assert artist.bio == "Hip hop group"
    assert artist.verified is True


def test_update_artist_json_column_serialized():
    db, artist_id = _db_with_artist()
    db.update_artist(artist_id, genres=["hip hop", "jazz rap"])
    assert db.get_artist(artist_id).genres == ["hip hop", "jazz rap"]


def test_update_artist_rejects_unknown_column():
    db, artist_id = _db_with_artist()
    with pytest.raises(ValueError):
        db.update_artist(artist_id, not_a_real_column="x")


def test_update_artist_rejects_sql_injection_identifier():
    db, artist_id = _db_with_artist()
    with pytest.raises(ValueError):
        db.update_artist(artist_id, **{"name = 'pwned', bio": "x"})


def test_update_artist_rejects_protected_columns():
    db, artist_id = _db_with_artist()
    for protected in ("id", "created_at"):
        with pytest.raises(ValueError):
            db.update_artist(artist_id, **{protected: "x"})
