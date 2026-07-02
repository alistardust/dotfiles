"""Database schema, connection management, and query helpers."""

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from tuneshift.models import Album, Artist, PlatformMapping, Playlist, PlaylistPin, Track

_SCHEMA_VERSION = 11

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    norm_title TEXT NOT NULL,
    norm_artist TEXT NOT NULL,
    norm_album TEXT,
    duration_seconds INTEGER,
    isrc TEXT,
    energy REAL,
    valence REAL,
    tempo REAL,
    key TEXT,
    themes TEXT,
    metadata JSON,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    mb_recording_id TEXT,
    mb_release_group_id TEXT,
    confidence_tier TEXT,
    confidence_score REAL,
    resolved_at TEXT,
    artist_id INTEGER REFERENCES artists(id),
    album_id INTEGER REFERENCES albums(id)
);

CREATE TABLE IF NOT EXISTS platform_tracks (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    platform_track_id TEXT NOT NULL,
    platform_title TEXT,
    platform_artist TEXT,
    platform_album TEXT,
    match_score INTEGER,
    is_divergent INTEGER NOT NULL DEFAULT 0,
    divergence_note TEXT,
    status TEXT NOT NULL DEFAULT 'matched',
    user_approved INTEGER NOT NULL DEFAULT 0,
    unavailable INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(track_id, platform)
);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    narrative TEXT,
    collection TEXT,
    goal TEXT,
    playlist_type TEXT,
    weights TEXT,
    mood_profile TEXT,
    curation_constraints TEXT,
    preferences TEXT,
    auto_reorder INTEGER NOT NULL DEFAULT 0,
    reorder_arc TEXT NOT NULL DEFAULT 'wave',
    tidal_folder_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    version_override TEXT,
    PRIMARY KEY (playlist_id, position)
);

CREATE TABLE IF NOT EXISTS platform_playlists (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    platform_playlist_id TEXT NOT NULL,
    last_synced_at TEXT,
    UNIQUE(playlist_id, platform)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    action TEXT NOT NULL,
    tracks_added INTEGER DEFAULT 0,
    tracks_removed INTEGER DEFAULT 0,
    tracks_reordered INTEGER DEFAULT 0,
    tracks_unavailable INTEGER DEFAULT 0,
    divergences_flagged INTEGER DEFAULT 0,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    raw_data TEXT,
    is_current INTEGER NOT NULL DEFAULT 1,
    superseded_by INTEGER REFERENCES evidence(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_pins (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    pin_type TEXT NOT NULL,
    group_id TEXT,
    group_order INTEGER,
    UNIQUE(playlist_id, track_id)
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL,
    sort_name TEXT,
    bio TEXT,
    identity JSON,
    tags JSON DEFAULT '[]',
    identity_confidence TEXT DEFAULT 'unconfirmed',
    genres JSON DEFAULT '[]',
    origin TEXT,
    active_start INTEGER,
    active_end INTEGER,
    mb_artist_id TEXT,
    tidal_artist_id INTEGER,
    spotify_artist_uri TEXT,
    lastfm_url TEXT,
    wikipedia_url TEXT,
    enrichment_sources JSON DEFAULT '[]',
    verified INTEGER DEFAULT 0,
    enriched_at TEXT,
    verified_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    norm_title TEXT NOT NULL,
    artist_id INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
    release_date TEXT,
    release_type TEXT DEFAULT 'album',
    edition TEXT DEFAULT 'original',
    genres JSON DEFAULT '[]',
    mb_release_group_id TEXT,
    tidal_album_id INTEGER,
    spotify_album_uri TEXT,
    enriched_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(norm_title, artist_id, edition)
);

CREATE INDEX IF NOT EXISTS idx_tracks_identity
    ON tracks(norm_title, norm_artist, norm_album);
CREATE INDEX IF NOT EXISTS idx_platform_tracks_lookup
    ON platform_tracks(track_id, platform);
CREATE INDEX IF NOT EXISTS idx_playlist_tracks_order
    ON playlist_tracks(playlist_id, position);
CREATE INDEX IF NOT EXISTS idx_tracks_isrc ON tracks(isrc) WHERE isrc IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_track ON evidence(track_id, is_current);
CREATE UNIQUE INDEX IF NOT EXISTS idx_artists_norm ON artists(norm_name);
CREATE INDEX IF NOT EXISTS idx_artists_mb ON artists(mb_artist_id) WHERE mb_artist_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_id);

CREATE TABLE IF NOT EXISTS banned_artists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    norm_name TEXT NOT NULL UNIQUE,
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS batch_history (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL,
    plan_json TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    reverted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_batch_history_playlist ON batch_history(playlist_id);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_collections (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    PRIMARY KEY (playlist_id, collection_id)
);

CREATE TABLE IF NOT EXISTS tidal_folders (
    id INTEGER PRIMARY KEY,
    tidal_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_tidal_id TEXT,
    last_synced_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS track_platform_metadata (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    platform TEXT NOT NULL,
    platform_track_id TEXT NOT NULL,
    release_year INTEGER,
    release_date TEXT,
    genres TEXT,
    audio_qualities TEXT,
    album_name TEXT,
    album_type TEXT,
    explicit INTEGER,
    duration_ms INTEGER,
    popularity INTEGER,
    raw_metadata TEXT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(track_id, platform)
);

CREATE TABLE IF NOT EXISTS track_tags (
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    tag TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (track_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_track_tags_tag ON track_tags(tag);
"""

_REMIX_RE = re.compile(r"\s*\((?:remaster(?:ed)?|deluxe edition)[^)]*\)\s*", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(value: str | None) -> str | None:
    """Normalize title-like text for indexed identity lookups."""
    if value is None:
        return None
    normalized = _REMIX_RE.sub(" ", value.strip().lower())
    normalized = normalized.replace("&", "and")
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized.strip() or None


def normalize_artist(value: str) -> str:
    """Normalize artist text for indexed identity lookups."""
    normalized = value.strip().lower().replace("&", "and")
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    if normalized.startswith("the "):
        normalized = normalized[4:]
    return normalized.strip()


def normalize_ban_name(value: str) -> str:
    """Normalize artist name for ban list matching.

    Stricter than normalize_artist: also strips diacritics and punctuation
    so "Beyonce" matches "Beyonce" and "P!nk" matches "Pink".
    """
    import unicodedata
    # NFD decomposition separates base chars from combining marks
    decomposed = unicodedata.normalize("NFD", value)
    # Strip combining marks (accents, diacritics)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    # Remove punctuation (keep alphanumeric and spaces)
    cleaned = re.sub(r"[^\w\s]", "", stripped)
    # Standard normalization
    cleaned = cleaned.strip().lower().replace("&", "and")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    if cleaned.startswith("the "):
        cleaned = cleaned[4:]
    return cleaned.strip()


def get_default_db_path() -> Path:
    """Return DB path, respecting TUNESHIFT_DB env var."""
    env_path = os.environ.get("TUNESHIFT_DB")
    if env_path:
        return Path(env_path)
    return Path(__file__).parent.parent / "tuneshift.db"


class Database:
    """SQLite database wrapper with schema management."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.path = db_path or get_default_db_path()
        if self.path.exists() and self.path.is_symlink():
            raise ValueError(f"Refusing to open symlinked database: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the lazily-opened SQLite connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _ensure_schema(self) -> None:
        """Create tables if they do not exist."""
        self.conn.executescript(_SCHEMA_SQL)
        self.conn.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES (?, ?)",
            ("version", str(_SCHEMA_VERSION)),
        )
        self.conn.commit()
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Migrate database schema to latest version."""
        row = self.conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'version'"
        ).fetchone()
        if row is None:
            return
        current_version = int(row[0])
        if current_version >= _SCHEMA_VERSION:
            return

        with self.conn:
            if current_version < 2:
                cols = {r[1] for r in self.conn.execute("PRAGMA table_info(tracks)").fetchall()}
                track_identity_columns = {
                    "mb_recording_id": "TEXT",
                    "mb_release_group_id": "TEXT",
                    "confidence_tier": "TEXT",
                    "confidence_score": "REAL",
                    "resolved_at": "TEXT",
                }
                for column_name, column_type in track_identity_columns.items():
                    if column_name not in cols:
                        self.conn.execute(
                            f"ALTER TABLE tracks ADD COLUMN {column_name} {column_type}"
                        )

                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS evidence (
                        id INTEGER PRIMARY KEY,
                        track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                        source TEXT NOT NULL,
                        evidence_type TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        raw_data TEXT,
                        is_current INTEGER NOT NULL DEFAULT 1,
                        superseded_by INTEGER REFERENCES evidence(id),
                        created_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                    """
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_evidence_track ON evidence(track_id, is_current)"
                )

            if current_version < 3:
                playlist_cols = {
                    r[1] for r in self.conn.execute("PRAGMA table_info(playlists)").fetchall()
                }
                if "auto_reorder" not in playlist_cols:
                    self.conn.execute(
                        "ALTER TABLE playlists ADD COLUMN auto_reorder INTEGER NOT NULL DEFAULT 0"
                    )
                if "reorder_arc" not in playlist_cols:
                    self.conn.execute(
                        "ALTER TABLE playlists ADD COLUMN reorder_arc TEXT NOT NULL DEFAULT 'wave'"
                    )

            if current_version < 4:
                self.conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS playlist_pins (
                        id INTEGER PRIMARY KEY,
                        playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                        track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
                        pin_type TEXT NOT NULL,
                        group_id TEXT,
                        group_order INTEGER,
                        UNIQUE(playlist_id, track_id)
                    )
                    """
                )

            if current_version < 5:
                self.conn.execute("""
                    DELETE FROM playlist_pins
                    WHERE NOT EXISTS (
                        SELECT 1 FROM playlist_tracks
                        WHERE playlist_tracks.playlist_id = playlist_pins.playlist_id
                        AND playlist_tracks.track_id = playlist_pins.track_id
                    )
                """)

            if current_version < 6:
                playlist_cols = {
                    r[1] for r in self.conn.execute("PRAGMA table_info(playlists)").fetchall()
                }
                if "narrative" not in playlist_cols:
                    self.conn.execute(
                        "ALTER TABLE playlists ADD COLUMN narrative TEXT"
                    )

            if current_version < 7:
                playlist_cols = {
                    r[1] for r in self.conn.execute("PRAGMA table_info(playlists)").fetchall()
                }
                if "collection" not in playlist_cols:
                    self.conn.execute("ALTER TABLE playlists ADD COLUMN collection TEXT")
                if "goal" not in playlist_cols:
                    self.conn.execute("ALTER TABLE playlists ADD COLUMN goal TEXT")
                if "playlist_type" not in playlist_cols:
                    self.conn.execute("ALTER TABLE playlists ADD COLUMN playlist_type TEXT")
                if "weights" not in playlist_cols:
                    self.conn.execute("ALTER TABLE playlists ADD COLUMN weights TEXT")
                if "mood_profile" not in playlist_cols:
                    self.conn.execute("ALTER TABLE playlists ADD COLUMN mood_profile TEXT")
                if "curation_constraints" not in playlist_cols:
                    self.conn.execute("ALTER TABLE playlists ADD COLUMN curation_constraints TEXT")
                if "preferences" not in playlist_cols:
                    self.conn.execute("ALTER TABLE playlists ADD COLUMN preferences TEXT")

                playlist_track_cols = {
                    r[1] for r in self.conn.execute("PRAGMA table_info(playlist_tracks)").fetchall()
                }
                if "version_override" not in playlist_track_cols:
                    self.conn.execute("ALTER TABLE playlist_tracks ADD COLUMN version_override TEXT")

            if current_version < 8:
                # Create artists table
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS artists (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        norm_name TEXT NOT NULL,
                        sort_name TEXT,
                        bio TEXT,
                        identity JSON,
                        tags JSON DEFAULT '[]',
                        identity_confidence TEXT DEFAULT 'unconfirmed',
                        genres JSON DEFAULT '[]',
                        origin TEXT,
                        active_start INTEGER,
                        active_end INTEGER,
                        mb_artist_id TEXT,
                        tidal_artist_id INTEGER,
                        spotify_artist_uri TEXT,
                        lastfm_url TEXT,
                        wikipedia_url TEXT,
                        enrichment_sources JSON DEFAULT '[]',
                        verified INTEGER DEFAULT 0,
                        enriched_at TEXT,
                        verified_at TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """)
                self.conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_artists_norm ON artists(norm_name)"
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_artists_mb ON artists(mb_artist_id)"
                )

                # Create albums table
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS albums (
                        id INTEGER PRIMARY KEY,
                        title TEXT NOT NULL,
                        norm_title TEXT NOT NULL,
                        artist_id INTEGER NOT NULL REFERENCES artists(id) ON DELETE CASCADE,
                        release_date TEXT,
                        release_type TEXT DEFAULT 'album',
                        edition TEXT DEFAULT 'original',
                        genres JSON DEFAULT '[]',
                        mb_release_group_id TEXT,
                        tidal_album_id INTEGER,
                        spotify_album_uri TEXT,
                        enriched_at TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        UNIQUE(norm_title, artist_id, edition)
                    )
                """)
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_albums_artist ON albums(artist_id)"
                )

                # Add FK columns to tracks
                track_cols = {
                    r[1] for r in self.conn.execute("PRAGMA table_info(tracks)").fetchall()
                }
                if "artist_id" not in track_cols:
                    self.conn.execute(
                        "ALTER TABLE tracks ADD COLUMN artist_id INTEGER REFERENCES artists(id)"
                    )
                if "album_id" not in track_cols:
                    self.conn.execute(
                        "ALTER TABLE tracks ADD COLUMN album_id INTEGER REFERENCES albums(id)"
                    )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tracks_artist_id ON tracks(artist_id)"
                )
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tracks_album_id ON tracks(album_id)"
                )

                # Populate artists from existing track data
                # Use the most common casing for each norm_artist as the canonical name
                self.conn.execute("""
                    INSERT OR IGNORE INTO artists (name, norm_name)
                    SELECT artist, norm_artist FROM (
                        SELECT artist, norm_artist, COUNT(*) as cnt,
                               ROW_NUMBER() OVER (PARTITION BY norm_artist ORDER BY COUNT(*) DESC) as rn
                        FROM tracks
                        GROUP BY artist, norm_artist
                    ) WHERE rn = 1
                """)

                # Link tracks to artists
                self.conn.execute("""
                    UPDATE tracks SET artist_id = (
                        SELECT id FROM artists WHERE artists.norm_name = tracks.norm_artist
                    )
                """)

                # Populate albums from existing track data
                self.conn.execute("""
                    INSERT OR IGNORE INTO albums (title, norm_title, artist_id)
                    SELECT t.album, t.norm_album, t.artist_id
                    FROM (
                        SELECT album, norm_album, artist_id,
                               ROW_NUMBER() OVER (
                                   PARTITION BY norm_album, artist_id ORDER BY COUNT(*) DESC
                               ) as rn
                        FROM tracks
                        WHERE album IS NOT NULL AND artist_id IS NOT NULL
                        GROUP BY album, norm_album, artist_id
                    ) t WHERE t.rn = 1
                """)

                # Link tracks to albums
                self.conn.execute("""
                    UPDATE tracks SET album_id = (
                        SELECT a.id FROM albums a
                        WHERE a.norm_title = tracks.norm_album
                        AND a.artist_id = tracks.artist_id
                    )
                    WHERE tracks.album IS NOT NULL AND tracks.artist_id IS NOT NULL
                """)

            if current_version < 9:
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS banned_artists (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        norm_name TEXT NOT NULL UNIQUE,
                        reason TEXT,
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                """)
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS batch_history (
                        id INTEGER PRIMARY KEY,
                        playlist_id INTEGER NOT NULL,
                        plan_json TEXT NOT NULL,
                        applied_at TEXT NOT NULL DEFAULT (datetime('now')),
                        reverted_at TEXT
                    )
                """)
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_batch_history_playlist "
                    "ON batch_history(playlist_id)"
                )

            if current_version < 10:
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS collections (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                """)
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS playlist_collections (
                        playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                        collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                        PRIMARY KEY (playlist_id, collection_id)
                    )
                """)
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS tidal_folders (
                        id INTEGER PRIMARY KEY,
                        tidal_id TEXT NOT NULL UNIQUE,
                        name TEXT NOT NULL,
                        parent_tidal_id TEXT,
                        last_synced_at TEXT DEFAULT (datetime('now'))
                    )
                """)
                playlist_cols = {
                    r[1] for r in self.conn.execute("PRAGMA table_info(playlists)").fetchall()
                }
                if "tidal_folder_id" not in playlist_cols:
                    self.conn.execute("ALTER TABLE playlists ADD COLUMN tidal_folder_id TEXT")

            if current_version < 11:
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS track_platform_metadata (
                        id INTEGER PRIMARY KEY,
                        track_id INTEGER NOT NULL REFERENCES tracks(id),
                        platform TEXT NOT NULL,
                        platform_track_id TEXT NOT NULL,
                        release_year INTEGER,
                        release_date TEXT,
                        genres TEXT,
                        audio_qualities TEXT,
                        album_name TEXT,
                        album_type TEXT,
                        explicit INTEGER,
                        duration_ms INTEGER,
                        popularity INTEGER,
                        raw_metadata TEXT,
                        fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
                        UNIQUE(track_id, platform)
                    )
                """)
                self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS track_tags (
                        track_id INTEGER NOT NULL REFERENCES tracks(id),
                        tag TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT 'manual',
                        created_at TEXT NOT NULL DEFAULT (datetime('now')),
                        PRIMARY KEY (track_id, tag)
                    )
                """)
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_track_tags_tag ON track_tags(tag)"
                )

            self.conn.execute(
                "UPDATE schema_meta SET value = ? WHERE key = 'version'",
                (str(_SCHEMA_VERSION),),
            )

    def insert_track(self, track: Track) -> int:
        """Insert a track and return its ID."""
        cursor = self.conn.execute(
            """INSERT INTO tracks (
                   title, artist, album, norm_title, norm_artist, norm_album,
                   duration_seconds, isrc, energy, valence, tempo, key, themes, metadata
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                track.title,
                track.artist,
                track.album,
                normalize_title(track.title),
                normalize_artist(track.artist),
                normalize_title(track.album) if track.album else None,
                track.duration_seconds,
                track.isrc,
                track.energy,
                track.valence,
                track.tempo,
                track.key,
                json.dumps(track.themes) if track.themes else None,
                json.dumps(track.metadata) if track.metadata else None,
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_track(self, track: Track) -> int:
        """Insert a track and return its ID."""
        return self.insert_track(track)

    def get_track(self, track_id: int) -> Track | None:
        """Fetch a track by ID."""
        row = self.conn.execute(
            "SELECT * FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_track(row)

    def find_track(self, title: str, artist: str, album: str | None) -> Track | None:
        """Find a track by identity using indexed normalized columns."""
        norm_title = normalize_title(title)
        norm_artist = normalize_artist(artist)
        norm_album = normalize_title(album) if album else None

        if norm_title is None:
            return None

        if norm_album:
            row = self.conn.execute(
                "SELECT * FROM tracks WHERE norm_title = ? AND norm_artist = ? AND norm_album = ?",
                (norm_title, norm_artist, norm_album),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM tracks WHERE norm_title = ? AND norm_artist = ? AND norm_album IS NULL",
                (norm_title, norm_artist),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_track(row)

    def get_resolution_state(
        self,
        track_id: int,
    ) -> tuple[str | None, float | None, str | None]:
        """Get the current resolution state of a track."""
        row = self.conn.execute(
            "SELECT confidence_tier, confidence_score, resolved_at FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
        if row is None:
            return None, None, None
        return row["confidence_tier"], row["confidence_score"], row["resolved_at"]

    def get_isrc(self, track_id: int) -> str | None:
        """Get the ISRC for a track."""
        row = self.conn.execute("SELECT isrc FROM tracks WHERE id = ?", (track_id,)).fetchone()
        return row["isrc"] if row else None

    def store_resolution(
        self,
        track_id: int,
        mb_recording_id: str | None,
        mb_release_group_id: str | None,
        confidence_tier: str,
        confidence_score: float,
        evidence: list[dict],
        isrc: str | None = None,
    ) -> None:
        """Store a successful resolution result."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        with self.conn:
            new_evidence_ids = []
            for evidence_row in evidence:
                cursor = self.conn.execute(
                    """INSERT INTO evidence (track_id, source, evidence_type, confidence, raw_data, is_current)
                       VALUES (?, ?, ?, ?, ?, 1)""",
                    (
                        track_id,
                        evidence_row["source"],
                        evidence_row["evidence_type"],
                        evidence_row["confidence"],
                        evidence_row.get("raw_data"),
                    ),
                )
                new_evidence_ids.append(cursor.lastrowid)

            anchor_id = new_evidence_ids[0] if new_evidence_ids else None
            if anchor_id is not None:
                placeholders = ",".join("?" for _ in new_evidence_ids)
                self.conn.execute(
                    f"""UPDATE evidence
                       SET is_current = 0, superseded_by = ?
                       WHERE track_id = ? AND is_current = 1 AND id NOT IN ({placeholders})""",
                    (anchor_id, track_id, *new_evidence_ids),
                )

            update_sql = """UPDATE tracks SET
                mb_recording_id = ?,
                mb_release_group_id = ?,
                confidence_tier = ?,
                confidence_score = ?,
                resolved_at = ?"""
            params: list[object] = [
                mb_recording_id,
                mb_release_group_id,
                confidence_tier,
                confidence_score,
                now,
            ]
            if isrc is not None:
                update_sql += ", isrc = ?"
                params.append(isrc)
            update_sql += " WHERE id = ?"
            params.append(track_id)
            self.conn.execute(update_sql, params)

    def store_failed_evidence(self, track_id: int, evidence: list[dict]) -> None:
        """Store evidence from a failed resolution attempt."""
        with self.conn:
            for evidence_row in evidence:
                self.conn.execute(
                    """INSERT INTO evidence (track_id, source, evidence_type, confidence, raw_data, is_current)
                       VALUES (?, ?, ?, ?, ?, 1)""",
                    (
                        track_id,
                        evidence_row["source"],
                        evidence_row["evidence_type"],
                        evidence_row["confidence"],
                        evidence_row.get("raw_data"),
                    ),
                )

    def find_unresolved(self, below_tier: str | None = None) -> list[Track]:
        """Find tracks that still need identity resolution."""
        tier_order = {"VERIFIED": 4, "CONFIRMED": 3, "PROBABLE": 2, "UNCERTAIN": 1}

        if below_tier is None:
            rows = self.conn.execute(
                "SELECT * FROM tracks WHERE confidence_tier IS NULL"
            ).fetchall()
        else:
            threshold = tier_order.get(below_tier, 0)
            tiers_below = [tier for tier, order in tier_order.items() if order < threshold]
            if not tiers_below:
                rows = self.conn.execute(
                    "SELECT * FROM tracks WHERE confidence_tier IS NULL"
                ).fetchall()
            else:
                placeholders = ",".join("?" for _ in tiers_below)
                rows = self.conn.execute(
                    f"SELECT * FROM tracks WHERE confidence_tier IS NULL OR confidence_tier IN ({placeholders})",
                    tiers_below,
                ).fetchall()

        return [self._row_to_track(row) for row in rows]

    def find_tracks_by_playlist(self, playlist_id: int) -> list[Track]:
        """Find all tracks in a playlist."""
        return self.get_playlist_tracks(playlist_id)

    def find_tracks_by_title_artist(self, title: str, artist: str) -> list[Track]:
        """Find tracks by title and artist using normalized columns."""
        norm_title = normalize_title(title)
        norm_artist = normalize_artist(artist)
        if norm_title is None:
            return []
        rows = self.conn.execute(
            "SELECT * FROM tracks WHERE norm_title = ? AND norm_artist = ?",
            (norm_title, norm_artist),
        ).fetchall()
        return [self._row_to_track(row) for row in rows]

    def search_tracks_by_metadata(
        self,
        intensity_range: tuple[float, float] | None = None,
        stance: str | None = None,
        keywords: list[str] | None = None,
        limit: int = 20,
    ) -> list[Track]:
        """Search tracks using metadata-backed narrative attributes."""
        rows = self.conn.execute("SELECT * FROM tracks ORDER BY updated_at DESC, id DESC").fetchall()
        normalized_stance = stance.casefold() if stance else None
        normalized_keywords = {
            keyword.casefold().strip()
            for keyword in (keywords or [])
            if keyword and keyword.strip()
        }
        matches: list[tuple[int, Track]] = []

        for row in rows:
            track = self._row_to_track(row)
            metadata = track.metadata or {}

            track_intensity = metadata.get("emotional_intensity", track.energy)
            if intensity_range is not None:
                if track_intensity is None:
                    continue
                try:
                    intensity_value = float(track_intensity)
                except (TypeError, ValueError):
                    continue
                minimum, maximum = intensity_range
                if intensity_value < minimum or intensity_value > maximum:
                    continue

            track_stance = metadata.get("narrator_stance")
            if normalized_stance is not None:
                if not isinstance(track_stance, str):
                    continue
                if track_stance.casefold() != normalized_stance:
                    continue

            overlap_count = 0
            if normalized_keywords:
                term_groups: list[str] = [track.title, track.artist]
                if track.album:
                    term_groups.append(track.album)
                term_groups.extend(track.themes)
                for key in (
                    "vibes",
                    "era_mood",
                    "lastfm_tags",
                    "lyrical_subject",
                    "narrator_stance",
                    "sonic_texture",
                    "space",
                    "groove_feel",
                    "opens_with",
                    "closes_with",
                    "energy_arc_within",
                ):
                    value = metadata.get(key)
                    if isinstance(value, list):
                        term_groups.extend(str(item) for item in value if item)
                    elif value:
                        term_groups.append(str(value))

                haystack = " ".join(term_groups).casefold()
                overlap_count = sum(1 for keyword in normalized_keywords if keyword in haystack)
                if overlap_count == 0:
                    continue

            matches.append((overlap_count, track))

        matches.sort(
            key=lambda item: (
                item[0],
                item[1].metadata.get("classification_confidence", 0.0),
                item[1].id or 0,
            ),
            reverse=True,
        )
        return [track for _, track in matches[:limit]]

    def create_playlist(self, name: str, description: str | None = None) -> int:
        """Create a playlist and return its ID."""
        cursor = self.conn.execute(
            "INSERT INTO playlists (name, description) VALUES (?, ?)",
            (name, description),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_playlists(self) -> list[Playlist]:
        """List all playlists."""
        rows = self.conn.execute("SELECT * FROM playlists ORDER BY name").fetchall()
        return [self._row_to_playlist(row) for row in rows]

    def _row_to_playlist(self, row) -> Playlist:
        """Convert a DB row to a Playlist object."""
        # row is a sqlite3.Row, can check keys directly
        keys = row.keys() if hasattr(row, "keys") else []
        tidal_folder = row["tidal_folder_id"] if "tidal_folder_id" in keys else None
        return Playlist(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            auto_reorder=bool(row["auto_reorder"]),
            reorder_arc=row["reorder_arc"],
            tidal_folder_id=tidal_folder,
        )

    def set_auto_reorder(self, playlist_id: int, enabled: bool, arc: str = "wave") -> None:
        """Enable or disable auto-reorder for a playlist."""
        self.conn.execute(
            "UPDATE playlists SET auto_reorder = ?, reorder_arc = ?, updated_at = datetime('now') WHERE id = ?",
            (int(enabled), arc, playlist_id),
        )
        self.conn.commit()

    def set_narrative(self, playlist_id: int, narrative: str | None) -> None:
        """Set the intended narrative arc description for a playlist."""
        self.conn.execute(
            "UPDATE playlists SET narrative = ?, updated_at = datetime('now') WHERE id = ?",
            (narrative, playlist_id),
        )
        self.conn.commit()

    def get_narrative(self, playlist_id: int) -> str | None:
        """Get the intended narrative arc description for a playlist."""
        row = self.conn.execute(
            "SELECT narrative FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        return row[0] if row else None

    def set_pin(
        self,
        playlist_id: int,
        track_id: int,
        pin_type: str,
        group_id: str | None = None,
        group_order: int | None = None,
    ) -> None:
        """Pin a track in a playlist (opener, closer, or anchor group)."""
        self.conn.execute(
            """INSERT OR REPLACE INTO playlist_pins
               (playlist_id, track_id, pin_type, group_id, group_order)
               VALUES (?, ?, ?, ?, ?)""",
            (playlist_id, track_id, pin_type, group_id, group_order),
        )
        self.conn.commit()

    def remove_pin(self, playlist_id: int, track_id: int) -> None:
        """Remove a pin from a playlist."""
        self.conn.execute(
            "DELETE FROM playlist_pins WHERE playlist_id = ? AND track_id = ?",
            (playlist_id, track_id),
        )
        self.conn.commit()

    def get_pins(self, playlist_id: int) -> list[PlaylistPin]:
        """Get all pins for a playlist."""
        rows = self.conn.execute(
            "SELECT playlist_id, track_id, pin_type, group_id, group_order "
            "FROM playlist_pins WHERE playlist_id = ? ORDER BY pin_type, group_id, group_order",
            (playlist_id,),
        ).fetchall()
        return [
            PlaylistPin(
                playlist_id=row[0],
                track_id=row[1],
                pin_type=row[2],
                group_id=row[3],
                group_order=row[4],
            )
            for row in rows
        ]

    def transfer_pins(self, playlist_id: int, from_track_id: int, to_track_id: int) -> None:
        """Transfer all pins from one track to another within a playlist."""
        with self.conn:
            self.conn.execute(
                """UPDATE playlist_pins SET track_id = ?
                   WHERE playlist_id = ? AND track_id = ?""",
                (to_track_id, playlist_id, from_track_id),
            )

    def merge_tracks(self, keep_id: int, merge_ids: list[int]) -> None:
        """Merge duplicate track rows into a canonical row.

        For each id in ``merge_ids``: reassign its playlist memberships and pins
        to ``keep_id`` (deduplicating within a playlist), delete its auxiliary
        rows (metadata, tags), then delete the track row itself. Runs in a
        single transaction so a failure leaves the database unchanged.

        Playlist positions are rewritten contiguously; the offset technique
        avoids transient UNIQUE(playlist_id, position) collisions during
        reassignment.
        """
        conn = self.conn
        with conn:
            for mid in merge_ids:
                if mid == keep_id:
                    continue
                playlists = [
                    r[0] for r in conn.execute(
                        "SELECT DISTINCT playlist_id FROM playlist_tracks WHERE track_id = ?",
                        (mid,),
                    ).fetchall()
                ]
                for pid in playlists:
                    # Transfer pins where possible; UNIQUE conflicts (keep already
                    # pinned) are ignored and cleaned up by the cascade below.
                    conn.execute(
                        "UPDATE OR IGNORE playlist_pins SET track_id = ? "
                        "WHERE playlist_id = ? AND track_id = ?",
                        (keep_id, pid, mid),
                    )
                    keep_present = conn.execute(
                        "SELECT 1 FROM playlist_tracks WHERE playlist_id = ? "
                        "AND track_id = ? LIMIT 1",
                        (pid, keep_id),
                    ).fetchone()
                    if keep_present:
                        # Avoid a duplicate membership: drop the merge rows.
                        conn.execute(
                            "DELETE FROM playlist_tracks WHERE playlist_id = ? "
                            "AND track_id = ?",
                            (pid, mid),
                        )
                    else:
                        conn.execute(
                            "UPDATE playlist_tracks SET track_id = ? "
                            "WHERE playlist_id = ? AND track_id = ?",
                            (keep_id, pid, mid),
                        )
                    # Reindex positions contiguously without PK collisions.
                    conn.execute(
                        "UPDATE playlist_tracks SET position = position + 1000000 "
                        "WHERE playlist_id = ?",
                        (pid,),
                    )
                    rows = conn.execute(
                        "SELECT rowid FROM playlist_tracks WHERE playlist_id = ? "
                        "ORDER BY position",
                        (pid,),
                    ).fetchall()
                    for idx, (rowid,) in enumerate(rows):
                        conn.execute(
                            "UPDATE playlist_tracks SET position = ? WHERE rowid = ?",
                            (idx, rowid),
                        )
                # Remove auxiliary rows that lack ON DELETE CASCADE.
                conn.execute("DELETE FROM track_platform_metadata WHERE track_id = ?", (mid,))
                conn.execute("DELETE FROM track_tags WHERE track_id = ?", (mid,))
                # Delete the track; cascade removes remaining platform_tracks,
                # playlist_tracks, playlist_pins, and evidence rows.
                conn.execute("DELETE FROM tracks WHERE id = ?", (mid,))

    def set_playlist_tracks(self, playlist_id: int, track_ids: list[int]) -> None:
        """Set the track order for a playlist, replacing existing rows."""
        self.conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        )
        for position, track_id in enumerate(track_ids):
            self.conn.execute(
                "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
                (playlist_id, track_id, position),
            )
        self.conn.commit()

    def clear_playlist_tracks(self, playlist_id: int) -> None:
        """Remove all tracks from a playlist without deleting the playlist."""
        self.conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ?",
            (playlist_id,),
        )
        self.conn.commit()

    def get_playlist_track_ids(self, playlist_id: int) -> list[int]:
        """Return ordered track IDs for a playlist."""
        rows = self.conn.execute(
            "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
            (playlist_id,),
        ).fetchall()
        return [row[0] for row in rows]

    def get_playlist_tracks(self, playlist_id: int) -> list[Track]:
        """Get ordered tracks for a playlist."""
        rows = self.conn.execute(
            """SELECT t.* FROM tracks t
               JOIN playlist_tracks pt ON t.id = pt.track_id
               WHERE pt.playlist_id = ?
               ORDER BY pt.position""",
            (playlist_id,),
        ).fetchall()
        return [self._row_to_track(row) for row in rows]

    def remove_playlist_track_by_position(self, playlist_id: int, position: int) -> None:
        """Remove a track at a position and reindex later rows."""
        self.conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND position = ?",
            (playlist_id, position),
        )
        self.conn.execute(
            """UPDATE playlist_tracks SET position = position - 1
               WHERE playlist_id = ? AND position > ?""",
            (playlist_id, position),
        )
        self.conn.commit()

    def remove_track_from_playlist(self, playlist_id: int, track_id: int) -> None:
        """Remove track from playlist with cascade cleanup of pins and positions."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, track_id),
            )
            self.conn.execute(
                "DELETE FROM playlist_pins WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, track_id),
            )
            rows = self.conn.execute(
                "SELECT rowid FROM playlist_tracks WHERE playlist_id = ? ORDER BY position",
                (playlist_id,),
            ).fetchall()
            for idx, (rowid,) in enumerate(rows):
                self.conn.execute(
                    "UPDATE playlist_tracks SET position = ? WHERE rowid = ?",
                    (idx, rowid),
                )

    def upsert_platform_mapping(self, mapping: PlatformMapping) -> None:
        """Insert or update a platform mapping."""
        self.conn.execute(
            """INSERT INTO platform_tracks
               (track_id, platform, platform_track_id, platform_title,
                platform_artist, platform_album, match_score,
                is_divergent, divergence_note, status, user_approved)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(track_id, platform) DO UPDATE SET
                 platform_track_id = excluded.platform_track_id,
                 platform_title = excluded.platform_title,
                 platform_artist = excluded.platform_artist,
                 platform_album = excluded.platform_album,
                 match_score = excluded.match_score,
                 is_divergent = excluded.is_divergent,
                 divergence_note = excluded.divergence_note,
                 status = excluded.status,
                 user_approved = excluded.user_approved""",
            (
                mapping.track_id,
                mapping.platform,
                mapping.platform_track_id,
                mapping.platform_title,
                mapping.platform_artist,
                mapping.platform_album,
                mapping.match_score,
                int(mapping.is_divergent),
                mapping.divergence_note,
                mapping.status,
                int(mapping.user_approved),
            ),
        )
        self.conn.commit()

    def get_platform_mapping(self, track_id: int, platform: str) -> PlatformMapping | None:
        """Get a platform mapping for a track."""
        row = self.conn.execute(
            "SELECT * FROM platform_tracks WHERE track_id = ? AND platform = ?",
            (track_id, platform),
        ).fetchone()
        if row is None:
            return None
        return PlatformMapping(
            track_id=row["track_id"],
            platform=row["platform"],
            platform_track_id=row["platform_track_id"],
            platform_title=row["platform_title"],
            platform_artist=row["platform_artist"],
            platform_album=row["platform_album"],
            match_score=row["match_score"],
            is_divergent=bool(row["is_divergent"]),
            divergence_note=row["divergence_note"],
            status=row["status"],
            user_approved=bool(row["user_approved"]),
        )

    def get_platform_mappings_for_tracks(
        self,
        track_ids: list[int],
        platform: str,
    ) -> dict[int, PlatformMapping]:
        """Batch-load platform mappings for multiple tracks."""
        if not track_ids:
            return {}
        placeholders = ",".join("?" for _ in track_ids)
        rows = self.conn.execute(
            f"SELECT * FROM platform_tracks WHERE track_id IN ({placeholders}) AND platform = ?",
            (*track_ids, platform),
        ).fetchall()
        result: dict[int, PlatformMapping] = {}
        for row in rows:
            result[row["track_id"]] = PlatformMapping(
                track_id=row["track_id"],
                platform=row["platform"],
                platform_track_id=row["platform_track_id"],
                platform_title=row["platform_title"],
                platform_artist=row["platform_artist"],
                platform_album=row["platform_album"],
                match_score=row["match_score"],
                is_divergent=bool(row["is_divergent"]),
                divergence_note=row["divergence_note"],
                status=row["status"],
                user_approved=bool(row["user_approved"]),
            )
        return result

    def set_platform_mapping(
        self,
        track_id: int,
        platform: str,
        platform_track_id: str,
        user_approved: bool = False,
        platform_title: str | None = None,
        platform_artist: str | None = None,
        platform_album: str | None = None,
        match_score: int | None = None,
    ) -> None:
        """Set or update a platform mapping for a track."""
        with self.conn:
            self.conn.execute(
                """INSERT INTO platform_tracks
                   (track_id, platform, platform_track_id, platform_title, platform_artist,
                    platform_album, match_score, user_approved)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(track_id, platform) DO UPDATE SET
                   platform_track_id = excluded.platform_track_id,
                   platform_title = excluded.platform_title,
                   platform_artist = excluded.platform_artist,
                   platform_album = excluded.platform_album,
                   match_score = excluded.match_score,
                   user_approved = excluded.user_approved""",
                (track_id, platform, platform_track_id, platform_title, platform_artist,
                 platform_album, match_score, int(user_approved)),
            )

    def delete_platform_mapping(self, track_id: int, platform: str) -> None:
        """Remove a platform mapping for a track."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM platform_tracks WHERE track_id = ? AND platform = ?",
                (track_id, platform),
            )

    def _row_to_track(self, row: sqlite3.Row) -> Track:
        """Convert a DB row to a Track model."""
        return Track(
            id=row["id"],
            title=row["title"],
            artist=row["artist"],
            album=row["album"],
            duration_seconds=row["duration_seconds"],
            isrc=row["isrc"],
            energy=row["energy"],
            valence=row["valence"],
            tempo=row["tempo"],
            key=row["key"],
            themes=json.loads(row["themes"]) if row["themes"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def update_track_metadata(self, track_id: int, meta: dict) -> None:
        """Update a track's audio metadata fields from enrichment data."""
        # Remap LLM field name to internal field name
        if "confidence" in meta and "classification_confidence" not in meta:
            meta["classification_confidence"] = meta.pop("confidence")
        updates = []
        params = []
        if "tempo" in meta:
            updates.append("tempo = ?")
            params.append(meta["tempo"])
        if "key" in meta:
            updates.append("key = ?")
            params.append(meta["key"])
        if "duration_seconds" in meta and meta["duration_seconds"]:
            updates.append("duration_seconds = ?")
            params.append(meta["duration_seconds"])
        if "isrc" in meta and meta["isrc"]:
            updates.append("isrc = ?")
            params.append(meta["isrc"])
        # Store extra fields in metadata JSON
        _METADATA_KEYS = (
            "key_scale", "energy", "valence",
            "themes", "vibes", "instruments", "density", "era_mood",
            "emotional_intensity", "lyrical_subject", "narrator_stance",
            "sonic_texture", "space", "groove_feel", "opens_with",
            "closes_with", "energy_arc_within", "classification_confidence",
        )
        track = self.get_track(track_id)
        if track:
            existing_meta = dict(track.metadata) if track.metadata else {}
            for k in _METADATA_KEYS:
                if k in meta:
                    existing_meta[k] = meta[k]
            if existing_meta != (track.metadata or {}):
                updates.append("metadata = ?")
                import json as _json
                params.append(_json.dumps(existing_meta))
        if updates:
            params.append(track_id)
            self.conn.execute(
                f"UPDATE tracks SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            self.conn.commit()

    def close(self) -> None:
        """Close the database connection if it is open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def add_track_to_playlist(self, playlist_id: int, track_id: int, position: int) -> None:
        """Add a track at a specific position (upsert, no error on conflict)."""
        self.conn.execute(
            """INSERT OR REPLACE INTO playlist_tracks (playlist_id, track_id, position)
               VALUES (?, ?, ?)""",
            (playlist_id, track_id, position),
        )
        self.conn.commit()

    def link_platform_playlist(self, playlist_id: int, platform: str, platform_playlist_id: str) -> None:
        """Link a canonical playlist to a platform playlist."""
        self.conn.execute(
            """INSERT OR REPLACE INTO platform_playlists (playlist_id, platform, platform_playlist_id)
               VALUES (?, ?, ?)""",
            (playlist_id, platform, platform_playlist_id),
        )
        self.conn.commit()

    def get_linked_platforms(self, playlist_id: int) -> list[str]:
        """Return platform names linked to this playlist."""
        rows = self.conn.execute(
            "SELECT platform FROM platform_playlists WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchall()
        return [row["platform"] for row in rows]

    def get_platform_playlist_id(self, playlist_id: int, platform: str) -> str | None:
        """Get the platform-specific playlist ID."""
        row = self.conn.execute(
            "SELECT platform_playlist_id FROM platform_playlists WHERE playlist_id = ? AND platform = ?",
            (playlist_id, platform),
        ).fetchone()
        return row["platform_playlist_id"] if row else None

    def mark_playlist_synced(self, playlist_id: int, platform: str) -> None:
        """Record that a playlist was successfully pushed to a platform.

        Call this ONLY after the platform push has succeeded, so the stored
        sync timestamp never claims a playlist is mirrored when the push failed.
        """
        self.conn.execute(
            "UPDATE platform_playlists SET last_synced_at = datetime('now') "
            "WHERE playlist_id = ? AND platform = ?",
            (playlist_id, platform),
        )
        self.conn.commit()

    def get_last_synced(self, playlist_id: int, platform: str) -> str | None:
        """Return the last successful push timestamp, or None if never synced."""
        row = self.conn.execute(
            "SELECT last_synced_at FROM platform_playlists WHERE playlist_id = ? AND platform = ?",
            (playlist_id, platform),
        ).fetchone()
        return row["last_synced_at"] if row else None

    def find_playlist_by_name(self, name: str) -> Playlist | None:
        """Find a playlist by exact name."""
        row = self.conn.execute(
            "SELECT * FROM playlists WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_playlist(row)

    def set_goal(self, playlist_id: int, goal: str | None) -> None:
        """Set the goal for a playlist."""
        self.conn.execute("UPDATE playlists SET goal = ? WHERE id = ?", (goal, playlist_id))
        self.conn.commit()

    def get_goal(self, playlist_id: int) -> str | None:
        """Get the goal for a playlist."""
        row = self.conn.execute("SELECT goal FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        return row[0] if row else None

    def set_collection(self, playlist_id: int, collection: str | None) -> None:
        """Set the collection a playlist belongs to (e.g., Pride, Laurel Canyon)."""
        self.conn.execute("UPDATE playlists SET collection = ? WHERE id = ?", (collection, playlist_id))
        self.conn.commit()

    def get_collection(self, playlist_id: int) -> str | None:
        """Get the collection a playlist belongs to."""
        row = self.conn.execute("SELECT collection FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        return row[0] if row else None

    def list_collections(self) -> list[str]:
        """List all distinct collections."""
        rows = self.conn.execute(
            "SELECT DISTINCT collection FROM playlists WHERE collection IS NOT NULL ORDER BY collection"
        ).fetchall()
        return [r[0] for r in rows]

    def get_playlists_in_collection(self, collection: str) -> list:
        """Get all playlists belonging to a collection."""
        return [p for p in self.list_playlists() if self.get_collection(p.id) == collection]

    def set_weights(self, playlist_id: int, weights: dict | None) -> None:
        """Set the weights for a playlist."""
        val = json.dumps(weights) if weights else None
        self.conn.execute("UPDATE playlists SET weights = ? WHERE id = ?", (val, playlist_id))
        self.conn.commit()

    def get_weights(self, playlist_id: int) -> dict | None:
        """Get the weights for a playlist."""
        row = self.conn.execute("SELECT weights FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def set_constraints(self, playlist_id: int, constraints: dict | None) -> None:
        """Set the curation constraints for a playlist."""
        val = json.dumps(constraints) if constraints else None
        self.conn.execute("UPDATE playlists SET curation_constraints = ? WHERE id = ?", (val, playlist_id))
        self.conn.commit()

    def get_constraints(self, playlist_id: int) -> dict | None:
        """Get the curation constraints for a playlist."""
        row = self.conn.execute("SELECT curation_constraints FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def set_preferences(self, playlist_id: int, prefs: dict | None) -> None:
        """Set the preferences for a playlist."""
        val = json.dumps(prefs) if prefs else None
        self.conn.execute("UPDATE playlists SET preferences = ? WHERE id = ?", (val, playlist_id))
        self.conn.commit()

    def get_preferences(self, playlist_id: int) -> dict | None:
        """Get the preferences for a playlist."""
        row = self.conn.execute("SELECT preferences FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def set_playlist_type(self, playlist_id: int, playlist_type: str | None) -> None:
        """Set the playlist type."""
        self.conn.execute("UPDATE playlists SET playlist_type = ? WHERE id = ?", (playlist_type, playlist_id))
        self.conn.commit()

    def get_playlist_type(self, playlist_id: int) -> str | None:
        """Get the playlist type."""
        row = self.conn.execute("SELECT playlist_type FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        return row[0] if row else None

    def set_mood_profile(self, playlist_id: int, mood_profile: dict | None) -> None:
        """Set the mood profile for a playlist."""
        val = json.dumps(mood_profile) if mood_profile else None
        self.conn.execute("UPDATE playlists SET mood_profile = ? WHERE id = ?", (val, playlist_id))
        self.conn.commit()

    def get_mood_profile(self, playlist_id: int) -> dict | None:
        """Get the mood profile for a playlist."""
        row = self.conn.execute("SELECT mood_profile FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    # ---- Artist methods ----

    def get_artist(self, artist_id: int) -> Artist | None:
        """Get an artist by ID."""
        row = self.conn.execute(
            "SELECT * FROM artists WHERE id = ?", (artist_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_artist(row)

    def get_artist_by_name(self, name: str) -> Artist | None:
        """Get an artist by name (normalized lookup)."""
        norm = normalize_artist(name)
        row = self.conn.execute(
            "SELECT * FROM artists WHERE norm_name = ?", (norm,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_artist(row)

    def get_artists_for_playlist(self, playlist_id: int) -> list[Artist]:
        """Get all unique artists in a playlist."""
        rows = self.conn.execute("""
            SELECT DISTINCT a.* FROM artists a
            JOIN tracks t ON t.artist_id = a.id
            JOIN playlist_tracks pt ON pt.track_id = t.id
            WHERE pt.playlist_id = ?
            ORDER BY a.name
        """, (playlist_id,)).fetchall()
        return [self._row_to_artist(row) for row in rows]

    _UPDATABLE_ARTIST_COLUMNS = frozenset({
        "name", "norm_name", "sort_name", "bio", "identity", "tags",
        "identity_confidence", "genres", "origin", "active_start", "active_end",
        "mb_artist_id", "tidal_artist_id", "spotify_artist_uri", "lastfm_url",
        "wikipedia_url", "enrichment_sources", "verified", "enriched_at",
        "verified_at",
    })

    def update_artist(self, artist_id: int, **fields: Any) -> None:
        """Update artist fields by keyword arguments.

        Field names are validated against an allowlist of updatable columns
        before being interpolated as SQL identifiers, preventing SQL-identifier
        injection via caller-supplied keys.
        """
        json_fields = {"identity", "tags", "genres", "enrichment_sources"}
        sets: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in self._UPDATABLE_ARTIST_COLUMNS:
                raise ValueError(f"Not an updatable artist column: {key!r}")
            sets.append(f"{key} = ?")
            if key in json_fields and not isinstance(value, str):
                values.append(json.dumps(value))
            else:
                values.append(value)
        if not sets:
            return
        sets.append("updated_at = datetime('now')")
        values.append(artist_id)
        self.conn.execute(
            f"UPDATE artists SET {', '.join(sets)} WHERE id = ?", values
        )
        self.conn.commit()

    def _row_to_artist(self, row: sqlite3.Row) -> Artist:
        """Convert a DB row to an Artist dataclass."""
        return Artist(
            id=row["id"],
            name=row["name"],
            norm_name=row["norm_name"],
            sort_name=row["sort_name"],
            bio=row["bio"],
            identity=json.loads(row["identity"]) if row["identity"] else None,
            tags=json.loads(row["tags"]) if row["tags"] else [],
            identity_confidence=row["identity_confidence"] or "unconfirmed",
            genres=json.loads(row["genres"]) if row["genres"] else [],
            origin=row["origin"],
            active_start=row["active_start"],
            active_end=row["active_end"],
            mb_artist_id=row["mb_artist_id"],
            tidal_artist_id=row["tidal_artist_id"],
            spotify_artist_uri=row["spotify_artist_uri"],
            lastfm_url=row["lastfm_url"],
            wikipedia_url=row["wikipedia_url"],
            enrichment_sources=json.loads(row["enrichment_sources"]) if row["enrichment_sources"] else [],
            verified=bool(row["verified"]),
            enriched_at=row["enriched_at"],
            verified_at=row["verified_at"],
        )

    # ---- Album methods ----

    def get_album(self, album_id: int) -> Album | None:
        """Get an album by ID."""
        row = self.conn.execute(
            "SELECT * FROM albums WHERE id = ?", (album_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_album(row)

    def get_albums_by_artist(self, artist_id: int) -> list[Album]:
        """Get all albums by an artist."""
        rows = self.conn.execute(
            "SELECT * FROM albums WHERE artist_id = ? ORDER BY release_date",
            (artist_id,),
        ).fetchall()
        return [self._row_to_album(row) for row in rows]

    def _row_to_album(self, row: sqlite3.Row) -> Album:
        """Convert a DB row to an Album dataclass."""
        return Album(
            id=row["id"],
            title=row["title"],
            norm_title=row["norm_title"],
            artist_id=row["artist_id"],
            release_date=row["release_date"],
            release_type=row["release_type"],
            edition=row["edition"],
            genres=json.loads(row["genres"]) if row["genres"] else [],
            mb_release_group_id=row["mb_release_group_id"],
            tidal_album_id=row["tidal_album_id"],
            spotify_album_uri=row["spotify_album_uri"],
            enriched_at=row["enriched_at"],
        )

    # ---- Banned Artist methods ----

    def ban_artist(self, name: str, reason: str | None = None) -> int:
        """Add an artist to the global ban list. Returns the ban ID."""
        norm = normalize_ban_name(name)
        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO banned_artists (name, norm_name, reason) VALUES (?, ?, ?)",
            (name, norm, reason),
        )
        self.conn.commit()
        return cursor.lastrowid or 0

    def unban_artist(self, name: str) -> bool:
        """Remove an artist from the ban list. Returns True if removed."""
        norm = normalize_ban_name(name)
        cursor = self.conn.execute(
            "DELETE FROM banned_artists WHERE norm_name = ?", (norm,)
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_banned_artists(self) -> list[tuple[str, str | None]]:
        """Get all banned artists as (name, reason) tuples."""
        rows = self.conn.execute(
            "SELECT name, reason FROM banned_artists ORDER BY name"
        ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def is_artist_banned(self, name: str) -> bool:
        """Check if an artist name (or segment) is on the ban list."""
        norm = normalize_ban_name(name)
        row = self.conn.execute(
            "SELECT 1 FROM banned_artists WHERE norm_name = ?", (norm,)
        ).fetchone()
        return row is not None

    # ---- Batch History methods ----

    def record_batch(self, playlist_id: int, plan_json: str) -> int:
        """Record an applied batch plan in history. Returns the history ID."""
        cursor = self.conn.execute(
            "INSERT INTO batch_history (playlist_id, plan_json) VALUES (?, ?)",
            (playlist_id, plan_json),
        )
        self.conn.commit()
        return cursor.lastrowid or 0

    def get_batch_history(self, playlist_id: int) -> list[dict]:
        """Get batch history for a playlist."""
        rows = self.conn.execute(
            "SELECT id, plan_json, applied_at, reverted_at "
            "FROM batch_history WHERE playlist_id = ? ORDER BY applied_at DESC",
            (playlist_id,),
        ).fetchall()
        return [
            {"id": r[0], "plan_json": r[1], "applied_at": r[2], "reverted_at": r[3]}
            for r in rows
        ]

    def mark_batch_reverted(self, history_id: int) -> None:
        """Mark a batch history entry as reverted."""
        self.conn.execute(
            "UPDATE batch_history SET reverted_at = datetime('now') WHERE id = ?",
            (history_id,),
        )
        self.conn.commit()

    # ---- Collection methods ----

    def create_collection(self, name: str, description: str | None = None) -> int:
        """Create a collection. Returns the ID."""
        self.conn.execute(
            "INSERT OR IGNORE INTO collections (name, description) VALUES (?, ?)",
            (name, description),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM collections WHERE name = ?", (name,)).fetchone()
        return row[0]

    def delete_collection(self, name: str) -> bool:
        """Delete a collection and all its playlist associations."""
        row = self.conn.execute("SELECT id FROM collections WHERE name = ?", (name,)).fetchone()
        if not row:
            return False
        self.conn.execute("DELETE FROM playlist_collections WHERE collection_id = ?", (row[0],))
        self.conn.execute("DELETE FROM collections WHERE id = ?", (row[0],))
        self.conn.commit()
        return True

    def tag_playlist(self, playlist_id: int, collection_name: str) -> None:
        """Add a collection tag to a playlist."""
        col_id = self.create_collection(collection_name)
        self.conn.execute(
            "INSERT OR IGNORE INTO playlist_collections (playlist_id, collection_id) VALUES (?, ?)",
            (playlist_id, col_id),
        )
        self.conn.commit()

    def untag_playlist(self, playlist_id: int, collection_name: str) -> bool:
        """Remove a collection tag from a playlist."""
        row = self.conn.execute("SELECT id FROM collections WHERE name = ?", (collection_name,)).fetchone()
        if not row:
            return False
        cursor = self.conn.execute(
            "DELETE FROM playlist_collections WHERE playlist_id = ? AND collection_id = ?",
            (playlist_id, row[0]),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_playlist_collections(self, playlist_id: int) -> list[str]:
        """Get all collection names for a playlist."""
        rows = self.conn.execute(
            "SELECT c.name FROM collections c "
            "JOIN playlist_collections pc ON pc.collection_id = c.id "
            "WHERE pc.playlist_id = ? ORDER BY c.name",
            (playlist_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def get_collection_playlists(self, collection_name: str) -> list:
        """Get all playlists in a collection."""
        rows = self.conn.execute(
            "SELECT p.* FROM playlists p "
            "JOIN playlist_collections pc ON pc.playlist_id = p.id "
            "JOIN collections c ON c.id = pc.collection_id "
            "WHERE c.name = ? ORDER BY p.name",
            (collection_name,),
        ).fetchall()
        return [self._row_to_playlist(r) for r in rows]

    def list_collections_with_counts(self) -> list[tuple[str, int]]:
        """List all collections with playlist counts."""
        rows = self.conn.execute(
            "SELECT c.name, COUNT(pc.playlist_id) FROM collections c "
            "LEFT JOIN playlist_collections pc ON pc.collection_id = c.id "
            "GROUP BY c.id ORDER BY c.name"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # ---- Tidal Folder cache methods ----

    def cache_tidal_folder(self, tidal_id: str, name: str, parent_tidal_id: str | None = None) -> None:
        """Cache a Tidal folder's metadata."""
        self.conn.execute(
            "INSERT OR REPLACE INTO tidal_folders (tidal_id, name, parent_tidal_id, last_synced_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (tidal_id, name, parent_tidal_id),
        )
        self.conn.commit()

    def get_tidal_folder_by_name(self, name: str) -> dict | None:
        """Look up a cached Tidal folder by name."""
        row = self.conn.execute(
            "SELECT tidal_id, name, parent_tidal_id FROM tidal_folders WHERE name = ?",
            (name,),
        ).fetchone()
        if not row:
            return None
        return {"tidal_id": row[0], "name": row[1], "parent_tidal_id": row[2]}

    def get_cached_tidal_folders(self) -> list[dict]:
        """Get all cached Tidal folders."""
        rows = self.conn.execute(
            "SELECT tidal_id, name, parent_tidal_id FROM tidal_folders ORDER BY name"
        ).fetchall()
        return [{"tidal_id": r[0], "name": r[1], "parent_tidal_id": r[2]} for r in rows]

    def remove_tidal_folder_cache(self, tidal_id: str) -> None:
        """Remove a folder from the cache."""
        self.conn.execute("DELETE FROM tidal_folders WHERE tidal_id = ?", (tidal_id,))
        self.conn.commit()

    def set_playlist_tidal_folder(self, playlist_id: int, tidal_folder_id: str | None) -> None:
        """Set or clear the Tidal folder assignment for a playlist."""
        self.conn.execute(
            "UPDATE playlists SET tidal_folder_id = ? WHERE id = ?",
            (tidal_folder_id, playlist_id),
        )
        self.conn.commit()

    def get_playlists_by_tidal_folder(self, tidal_folder_id: str) -> list:
        """Get all playlists assigned to a Tidal folder."""
        rows = self.conn.execute(
            "SELECT * FROM playlists WHERE tidal_folder_id = ? ORDER BY name",
            (tidal_folder_id,),
        ).fetchall()
        return [self._row_to_playlist(r) for r in rows]

    def clear_tidal_folder_assignments(self, tidal_folder_id: str) -> int:
        """Clear folder assignments for all playlists in a folder. Returns count."""
        cursor = self.conn.execute(
            "UPDATE playlists SET tidal_folder_id = NULL WHERE tidal_folder_id = ?",
            (tidal_folder_id,),
        )
        self.conn.commit()
        return cursor.rowcount

    # ---- Platform Metadata methods ----

    def upsert_track_platform_metadata(self, track_id: int, platform: str,
                                        platform_track_id: str, **fields) -> None:
        """Insert or update platform metadata for a track."""
        import json as _json
        # Serialize JSON fields
        for key in ("genres", "audio_qualities", "raw_metadata"):
            if key in fields and not isinstance(fields[key], str):
                fields[key] = _json.dumps(fields[key])

        existing = self.conn.execute(
            "SELECT id FROM track_platform_metadata WHERE track_id = ? AND platform = ?",
            (track_id, platform),
        ).fetchone()

        if existing:
            sets = ", ".join(f"{k} = ?" for k in fields)
            vals = list(fields.values()) + [track_id, platform]
            self.conn.execute(
                f"UPDATE track_platform_metadata SET {sets}, fetched_at = datetime('now') "
                f"WHERE track_id = ? AND platform = ?", vals,
            )
        else:
            cols = ["track_id", "platform", "platform_track_id"] + list(fields.keys())
            placeholders = ", ".join("?" * len(cols))
            vals = [track_id, platform, platform_track_id] + list(fields.values())
            self.conn.execute(
                f"INSERT INTO track_platform_metadata ({', '.join(cols)}) VALUES ({placeholders})",
                vals,
            )
        self.conn.commit()

    def get_track_platform_metadata(self, track_id: int, platform: str) -> dict | None:
        """Get platform metadata for a track."""
        import json as _json
        row = self.conn.execute(
            "SELECT * FROM track_platform_metadata WHERE track_id = ? AND platform = ?",
            (track_id, platform),
        ).fetchone()
        if not row:
            return None
        cols = [d[1] for d in self.conn.execute("PRAGMA table_info(track_platform_metadata)").fetchall()]
        result = dict(zip(cols, row))
        for key in ("genres", "audio_qualities", "raw_metadata"):
            if result.get(key) and isinstance(result[key], str):
                try:
                    result[key] = _json.loads(result[key])
                except _json.JSONDecodeError:
                    pass
        return result

    # ---- Track Tag methods ----

    def add_track_tag(self, track_id: int, tag: str, source: str = "manual") -> None:
        """Add a tag to a track."""
        self.conn.execute(
            "INSERT OR IGNORE INTO track_tags (track_id, tag, source) VALUES (?, ?, ?)",
            (track_id, tag, source),
        )
        self.conn.commit()

    def remove_track_tag(self, track_id: int, tag: str) -> bool:
        """Remove a tag from a track."""
        cursor = self.conn.execute(
            "DELETE FROM track_tags WHERE track_id = ? AND tag = ?",
            (track_id, tag),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def get_track_tags(self, track_id: int) -> list[str]:
        """Get all tags for a track."""
        rows = self.conn.execute(
            "SELECT tag FROM track_tags WHERE track_id = ? ORDER BY tag",
            (track_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def find_tracks_by_tag(self, *tags: str) -> list:
        """Find tracks matching ALL given tags."""
        if not tags:
            return []
        placeholders = ", ".join("?" * len(tags))
        rows = self.conn.execute(
            f"SELECT t.* FROM tracks t "
            f"WHERE (SELECT COUNT(*) FROM track_tags tt WHERE tt.track_id = t.id AND tt.tag IN ({placeholders})) = ?",
            list(tags) + [len(tags)],
        ).fetchall()
        return [self._row_to_track(r) for r in rows]

    def list_all_track_tags(self) -> list[tuple[str, int]]:
        """List all tags with usage counts."""
        rows = self.conn.execute(
            "SELECT tag, COUNT(*) FROM track_tags GROUP BY tag ORDER BY COUNT(*) DESC"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
