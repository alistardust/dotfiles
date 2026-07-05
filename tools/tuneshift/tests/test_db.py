"""Database schema and CRUD tests for tuneshift."""

import sqlite3
from pathlib import Path

import pytest

from tuneshift.db import Database, get_default_db_path
from tuneshift.models import PlatformMapping, Track


def test_create_schema(tmp_db: Path) -> None:
    """Schema creates all expected tables."""
    Database(tmp_db)
    conn = sqlite3.connect(tmp_db)
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    assert "tracks" in tables
    assert "platform_tracks" in tables
    assert "playlists" in tables
    assert "playlist_tracks" in tables
    assert "platform_playlists" in tables
    assert "sync_log" in tables


def test_schema_idempotent(tmp_db: Path) -> None:
    """Creating DB twice does not error."""
    Database(tmp_db)
    Database(tmp_db)


def test_env_var_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """TUNESHIFT_DB env var overrides default path."""
    custom_path = tmp_path / "custom.db"
    monkeypatch.setenv("TUNESHIFT_DB", str(custom_path))
    assert get_default_db_path() == custom_path


def test_insert_and_get_track(tmp_db: Path) -> None:
    db = Database(tmp_db)
    track = Track(title="Five Years", artist="David Bowie", album="Ziggy Stardust")
    track_id = db.insert_track(track)
    assert track_id > 0
    fetched = db.get_track(track_id)
    assert fetched is not None
    assert fetched.title == "Five Years"
    assert fetched.artist == "David Bowie"


def test_insert_playlist_and_tracks(tmp_db: Path) -> None:
    db = Database(tmp_db)
    first_track_id = db.insert_track(
        Track(title="Future Legend", artist="David Bowie", album="Diamond Dogs")
    )
    second_track_id = db.insert_track(
        Track(title="Diamond Dogs", artist="David Bowie", album="Diamond Dogs")
    )
    playlist_id = db.create_playlist("Diamond Dogs", "Bowie 1974")
    db.set_playlist_tracks(playlist_id, [first_track_id, second_track_id])
    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 2
    assert tracks[0].title == "Future Legend"
    assert tracks[1].title == "Diamond Dogs"


def test_upsert_platform_mapping(tmp_db: Path) -> None:
    db = Database(tmp_db)
    track_id = db.insert_track(Track(title="Heroes", artist="David Bowie"))
    mapping = PlatformMapping(
        track_id=track_id,
        platform="spotify",
        platform_track_id="spotify:track:abc",
        match_score=95,
    )
    db.upsert_platform_mapping(mapping)
    fetched = db.get_platform_mapping(track_id, "spotify")
    assert fetched is not None
    assert fetched.platform_track_id == "spotify:track:abc"


def test_find_track_by_identity(tmp_db: Path) -> None:
    db = Database(tmp_db)
    db.insert_track(Track(title="Heroes", artist="David Bowie", album="Heroes"))
    found = db.find_track("Heroes", "David Bowie", "Heroes")
    assert found is not None
    assert found.title == "Heroes"


def test_find_track_not_found(tmp_db: Path) -> None:
    db = Database(tmp_db)
    found = db.find_track("Nonexistent", "Nobody", None)
    assert found is None


def test_list_playlists(tmp_db: Path) -> None:
    db = Database(tmp_db)
    db.create_playlist("Playlist A")
    db.create_playlist("Playlist B")
    playlists = db.list_playlists()
    assert len(playlists) == 2
    names = [playlist.name for playlist in playlists]
    assert "Playlist A" in names
    assert "Playlist B" in names


def test_remove_playlist_track_by_position(tmp_db: Path) -> None:
    db = Database(tmp_db)
    first_track_id = db.insert_track(Track(title="A", artist="X"))
    second_track_id = db.insert_track(Track(title="B", artist="X"))
    third_track_id = db.insert_track(Track(title="C", artist="X"))
    playlist_id = db.create_playlist("Test")
    db.set_playlist_tracks(playlist_id, [first_track_id, second_track_id, third_track_id])
    db.remove_playlist_track_by_position(playlist_id, 1)
    tracks = db.get_playlist_tracks(playlist_id)
    assert len(tracks) == 2
    assert tracks[0].title == "A"
    assert tracks[1].title == "C"


def test_match_audit_round_trip(tmp_db: Path) -> None:
    """A persisted MatchAudit round-trips through the match_audits table."""
    from tuneshift.matching import Availability, MatchAudit, ReasonCode, RejectedCandidate

    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Heroes", artist="David Bowie", album="Heroes"))

    audit = MatchAudit(
        availability=Availability.EXACT_AVAILABLE,
        reason_code=ReasonCode.MATCHED,
        chosen_platform_id="sp1",
        chosen_score=98,
        decisive_signal="title:exact",
        distance=0.02,
        rejected=[RejectedCandidate(
            platform_id="sp2", title="Heroes (Live)", artist="David Bowie",
            album="Live", score=40, decisive_signal="version:reject",
        )],
    )
    db.save_match_audit(track_id, "spotify", audit)

    loaded = db.get_match_audit(track_id, "spotify")
    assert loaded is not None
    assert loaded.availability == Availability.EXACT_AVAILABLE
    assert loaded.reason_code == ReasonCode.MATCHED
    assert loaded.chosen_platform_id == "sp1"
    assert loaded.chosen_score == 98
    assert len(loaded.rejected) == 1
    assert loaded.rejected[0].decisive_signal == "version:reject"


def test_save_match_audit_none_is_noop(tmp_db: Path) -> None:
    """Saving a None audit is a no-op, not an error."""
    db = Database(tmp_db)
    track_id = db.add_track(Track(title="X", artist="Y", album="Z"))
    db.save_match_audit(track_id, "spotify", None)
    assert db.get_match_audit(track_id, "spotify") is None


def test_save_match_audit_upserts(tmp_db: Path) -> None:
    """Re-saving replaces the prior audit for the same (track, platform)."""
    from tuneshift.matching import Availability, MatchAudit, ReasonCode

    db = Database(tmp_db)
    track_id = db.add_track(Track(title="X", artist="Y", album="Z"))
    db.save_match_audit(track_id, "spotify", MatchAudit(
        availability=Availability.NOT_FOUND, reason_code=ReasonCode.NO_CANDIDATES))
    db.save_match_audit(track_id, "spotify", MatchAudit(
        availability=Availability.EXACT_AVAILABLE, reason_code=ReasonCode.MATCHED,
        chosen_platform_id="sp9"))

    loaded = db.get_match_audit(track_id, "spotify")
    assert loaded.availability == Availability.EXACT_AVAILABLE
    assert loaded.chosen_platform_id == "sp9"


def test_get_match_audits_for_track_keyed_by_platform(tmp_db: Path) -> None:
    from tuneshift.matching import Availability, MatchAudit, ReasonCode

    db = Database(tmp_db)
    track_id = db.add_track(Track(title="X", artist="Y", album="Z"))
    db.save_match_audit(track_id, "spotify", MatchAudit(
        availability=Availability.EXACT_AVAILABLE, reason_code=ReasonCode.MATCHED))
    db.save_match_audit(track_id, "tidal", MatchAudit(
        availability=Availability.EXACT_UNAVAILABLE, reason_code=ReasonCode.BLOCKED_IN_MARKET))

    audits = db.get_match_audits_for_track(track_id)
    assert set(audits) == {"spotify", "tidal"}
    assert audits["tidal"].availability == Availability.EXACT_UNAVAILABLE


def test_match_audit_is_playlist_scoped(tmp_db: Path) -> None:
    """The same (track, platform) can carry a distinct audit per playlist.

    Selection is now playlist-dependent, so ``explain`` must not clobber one
    playlist's decision with another's (spec §4.1a item 5, AC-CLI3/CLI5).
    """
    from tuneshift.matching import Availability, MatchAudit, ReasonCode

    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Flower", artist="Liam", album="A"))
    p_atmos = db.create_playlist("Atmos Mix")
    p_stereo = db.create_playlist("Stereo Mix")

    db.save_match_audit(track_id, "tidal", MatchAudit(
        availability=Availability.EXACT_AVAILABLE, reason_code=ReasonCode.MATCHED,
        chosen_platform_id="atmos-id"), playlist_id=p_atmos)
    db.save_match_audit(track_id, "tidal", MatchAudit(
        availability=Availability.EXACT_AVAILABLE, reason_code=ReasonCode.MATCHED,
        chosen_platform_id="stereo-id"), playlist_id=p_stereo)

    a = db.get_match_audit(track_id, "tidal", playlist_id=p_atmos)
    s = db.get_match_audit(track_id, "tidal", playlist_id=p_stereo)
    assert a.chosen_platform_id == "atmos-id"
    assert s.chosen_platform_id == "stereo-id", "second playlist must not clobber the first"


def test_match_audit_default_scope_is_global_sentinel(tmp_db: Path) -> None:
    """Writer/readers default to the global sentinel (playlist_id=0), so legacy
    call sites that don't pass a playlist keep working after the migration."""
    from tuneshift.matching import Availability, MatchAudit, ReasonCode

    db = Database(tmp_db)
    track_id = db.add_track(Track(title="X", artist="Y", album="Z"))
    db.save_match_audit(track_id, "spotify", MatchAudit(
        availability=Availability.EXACT_AVAILABLE, reason_code=ReasonCode.MATCHED))
    assert db.get_match_audit(track_id, "spotify") is not None
    assert db.get_match_audit(track_id, "spotify", playlist_id=0) is not None
    # a real playlist scope is a distinct slot, initially empty
    pid = db.create_playlist("P")
    assert db.get_match_audit(track_id, "spotify", playlist_id=pid) is None


def test_match_audit_playlist_column_migration(tmp_db: Path) -> None:
    """A pre-v16 match_audits (PK track_id,platform) migrates: existing rows land
    at the global sentinel and the playlist_id column exists."""
    import sqlite3

    conn = sqlite3.connect(tmp_db)
    conn.executescript(
        """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
            album TEXT, norm_title TEXT NOT NULL, norm_artist TEXT NOT NULL,
            norm_album TEXT, isrc TEXT
        );
        CREATE TABLE match_audits (
            track_id INTEGER NOT NULL, platform TEXT NOT NULL,
            availability TEXT NOT NULL, reason_code TEXT NOT NULL,
            audit_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (track_id, platform)
        );
        INSERT INTO tracks (id, title, artist, album, norm_title, norm_artist, norm_album)
            VALUES (1, 'T', 'A', 'Al', 't', 'a', 'al');
        INSERT INTO match_audits (track_id, platform, availability, reason_code, audit_json)
            VALUES (1, 'tidal', 'exact_available', 'matched', '{"availability":"exact_available","reason_code":"matched"}');
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO schema_meta (key, value) VALUES ('version', '15');
        """
    )
    conn.commit()
    conn.close()

    db = Database(tmp_db)
    cols = {r[1] for r in db.conn.execute("PRAGMA table_info(match_audits)").fetchall()}
    assert "playlist_id" in cols
    row = db.conn.execute(
        "SELECT playlist_id FROM match_audits WHERE track_id=1 AND platform='tidal'"
    ).fetchone()
    assert row["playlist_id"] == 0
    db.close()
