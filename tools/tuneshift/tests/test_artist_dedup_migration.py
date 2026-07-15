"""BUG-9: artist dedup + UNIQUE index migration (schema v22)."""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import Database
from tuneshift.models import Track


def _break_into_pre_fix_state(db: Database) -> None:
    """Recreate the shipped-bug state: non-unique idx + version rolled back."""
    db.conn.execute("DROP INDEX IF EXISTS idx_artists_norm")
    db.conn.execute("CREATE INDEX idx_artists_norm ON artists(norm_name)")
    db.conn.execute("UPDATE schema_meta SET value = '21' WHERE key = 'version'")
    db.conn.commit()


def test_migration_dedupes_and_enforces_unique(tmp_path: Path):
    path = tmp_path / "t.db"
    db = Database(path)
    _break_into_pre_fix_state(db)

    # keeper (lower id) richer in tags; dupe carries an mb_artist_id the keeper lacks.
    db.conn.execute(
        "INSERT INTO artists (name, norm_name, tags) VALUES (?, ?, ?)",
        ("Spice Girls", "spice girls", '["pop"]'),
    )
    keeper_id = db.conn.execute(
        "SELECT id FROM artists WHERE norm_name = 'spice girls'"
    ).fetchone()["id"]
    db.conn.execute(
        "INSERT INTO artists (name, norm_name, mb_artist_id) VALUES (?, ?, ?)",
        ("Spice Girls", "spice girls", "MBID-123"),
    )
    dupe_id = db.conn.execute(
        "SELECT id FROM artists WHERE norm_name = 'spice girls' AND id != ?",
        (keeper_id,),
    ).fetchone()["id"]
    # A track referencing the DUPE row, to prove the FK is repointed.
    db.conn.execute(
        "INSERT INTO tracks (title, artist, norm_title, norm_artist, artist_id) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Wannabe", "Spice Girls", "wannabe", "spice girls", dupe_id),
    )
    db.conn.commit()

    # Reopen: _ensure_schema -> _migrate_schema applies the v22 fix.
    db2 = Database(path)

    # Exactly one artist row for the group now.
    rows = db2.conn.execute(
        "SELECT id FROM artists WHERE norm_name = 'spice girls'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["id"] == keeper_id  # lowest id kept

    # The index is genuinely UNIQUE now.
    idx_sql = db2.conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'idx_artists_norm'"
    ).fetchone()["sql"]
    assert "UNIQUE" in idx_sql.upper()

    # Enrichment merged: keeper keeps its tags AND gains the dupe's mb_artist_id.
    keeper = db2.conn.execute(
        "SELECT tags, mb_artist_id FROM artists WHERE id = ?", (keeper_id,)
    ).fetchone()
    assert keeper["tags"] == '["pop"]'
    assert keeper["mb_artist_id"] == "MBID-123"

    # The track FK was repointed from the dupe to the keeper.
    track_artist = db2.conn.execute(
        "SELECT artist_id FROM tracks WHERE norm_title = 'wannabe'"
    ).fetchone()["artist_id"]
    assert track_artist == keeper_id


def test_get_or_create_artist_is_idempotent_after_fix(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    first = db._get_or_create_artist("Destiny's Child")
    second = db._get_or_create_artist("Destiny's Child")
    assert first == second
    count = db.conn.execute(
        "SELECT COUNT(*) c FROM artists WHERE norm_name = ?",
        ("destiny's child",),
    ).fetchone()["c"]
    assert count == 1


def test_unique_index_blocks_duplicate_insert(tmp_path: Path):
    import sqlite3

    db = Database(tmp_path / "t.db")
    db.conn.execute(
        "INSERT INTO artists (name, norm_name) VALUES (?, ?)", ("TLC", "tlc")
    )
    db.conn.commit()
    try:
        db.conn.execute(
            "INSERT INTO artists (name, norm_name) VALUES (?, ?)", ("TLC", "tlc")
        )
        db.conn.commit()
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    assert raised  # the UNIQUE constraint is real on a fresh DB too


def test_add_track_twice_same_artist_single_row(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    db.add_track(Track(title="A", artist="Britney Spears", album="X"))
    db.add_track(Track(title="B", artist="Britney Spears", album="Y"))
    count = db.conn.execute(
        "SELECT COUNT(*) c FROM artists WHERE norm_name = ?",
        ("britney spears",),
    ).fetchone()["c"]
    assert count == 1
