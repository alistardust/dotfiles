"""Task 1.1 (H3 fix): runtime artist/album creation + linking on insert_track.

insert_track must link every runtime-added track to the normalized artists/albums
tables (artist_id/album_id), not only via the one-time migration backfill. This is
a gate on AC-D1/AC-D3 (coverage floor + first-class metadata).
"""

import pytest

from tuneshift.db import Database, normalize_artist, normalize_title
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def test_insert_track_links_artist_and_album(db):
    tid = db.insert_track(
        Track(title="Sloop John B", artist="The Beach Boys", album="Pet Sounds")
    )
    row = db.conn.execute(
        "SELECT artist_id, album_id FROM tracks WHERE id=?", (tid,)
    ).fetchone()
    assert row["artist_id"] is not None, "runtime insert must set artist_id"
    assert row["album_id"] is not None, "runtime insert must set album_id"

    artist = db.get_artist(row["artist_id"])
    assert artist is not None and artist.name == "The Beach Boys"
    album = db.get_album(row["album_id"])
    assert album is not None and album.title == "Pet Sounds"
    assert album.artist_id == row["artist_id"]


def test_insert_track_reuses_existing_artist_and_album(db):
    tid1 = db.insert_track(
        Track(title="Sloop John B", artist="The Beach Boys", album="Pet Sounds")
    )
    tid2 = db.insert_track(
        Track(title="Wouldn't It Be Nice", artist="The Beach Boys", album="Pet Sounds")
    )
    r1 = db.conn.execute(
        "SELECT artist_id, album_id FROM tracks WHERE id=?", (tid1,)
    ).fetchone()
    r2 = db.conn.execute(
        "SELECT artist_id, album_id FROM tracks WHERE id=?", (tid2,)
    ).fetchone()
    assert r2["artist_id"] == r1["artist_id"], "same artist must be reused"
    assert r2["album_id"] == r1["album_id"], "same album must be reused"

    norm = normalize_artist("The Beach Boys")
    count = db.conn.execute(
        "SELECT COUNT(*) c FROM artists WHERE norm_name=?", (norm,)
    ).fetchone()["c"]
    assert count == 1, "get-or-create must not duplicate the artist row"


def test_insert_track_without_album_leaves_album_id_null(db):
    tid = db.insert_track(Track(title="Untitled", artist="Aphex Twin", album=None))
    row = db.conn.execute(
        "SELECT artist_id, album_id FROM tracks WHERE id=?", (tid,)
    ).fetchone()
    assert row["artist_id"] is not None
    assert row["album_id"] is None


def test_get_or_create_album_matches_default_edition(db):
    """The album get-or-create must key on the same columns the INSERT uses
    (norm_title, artist_id, edition='original') so the lookup does not miss."""
    tid1 = db.insert_track(Track(title="A", artist="Same Artist", album="Same Album"))
    tid2 = db.insert_track(Track(title="B", artist="Same Artist", album="Same Album"))
    a1 = db.conn.execute("SELECT album_id FROM tracks WHERE id=?", (tid1,)).fetchone()
    a2 = db.conn.execute("SELECT album_id FROM tracks WHERE id=?", (tid2,)).fetchone()
    assert a1["album_id"] == a2["album_id"]
    norm = normalize_title("Same Album")
    count = db.conn.execute(
        "SELECT COUNT(*) c FROM albums WHERE norm_title=?", (norm,)
    ).fetchone()["c"]
    assert count == 1
