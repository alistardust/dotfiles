"""Database schema, connection management, and query helpers."""

import json
import os
import re
import sqlite3
from pathlib import Path

from tuneshift.models import PlatformMapping, Playlist, Track

_SCHEMA_VERSION = 3

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
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS platform_tracks (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
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
    auto_reorder INTEGER NOT NULL DEFAULT 0,
    reorder_arc TEXT NOT NULL DEFAULT 'wave',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id),
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    position INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, position)
);

CREATE TABLE IF NOT EXISTS platform_playlists (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id),
    platform TEXT NOT NULL,
    platform_playlist_id TEXT NOT NULL,
    last_synced_at TEXT,
    UNIQUE(playlist_id, platform)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY,
    playlist_id INTEGER NOT NULL REFERENCES playlists(id),
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
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    source TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    raw_data TEXT,
    is_current INTEGER NOT NULL DEFAULT 1,
    superseded_by INTEGER REFERENCES evidence(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tracks_identity
    ON tracks(norm_title, norm_artist, norm_album);
CREATE INDEX IF NOT EXISTS idx_platform_tracks_lookup
    ON platform_tracks(track_id, platform);
CREATE INDEX IF NOT EXISTS idx_playlist_tracks_order
    ON playlist_tracks(playlist_id, position);
CREATE INDEX IF NOT EXISTS idx_tracks_isrc ON tracks(isrc) WHERE isrc IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_track ON evidence(track_id, is_current);
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
                        track_id INTEGER NOT NULL REFERENCES tracks(id),
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
        return [
            Playlist(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                auto_reorder=bool(row["auto_reorder"]),
                reorder_arc=row["reorder_arc"],
            )
            for row in rows
        ]

    def set_auto_reorder(self, playlist_id: int, enabled: bool, arc: str = "wave") -> None:
        """Enable or disable auto-reorder for a playlist."""
        self.conn.execute(
            "UPDATE playlists SET auto_reorder = ?, reorder_arc = ?, updated_at = datetime('now') WHERE id = ?",
            (int(enabled), arc, playlist_id),
        )
        self.conn.commit()

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
        track = self.get_track(track_id)
        if track:
            existing_meta = track.metadata or {}
            for k in ("key_scale", "energy", "valence"):
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

    def find_playlist_by_name(self, name: str) -> Playlist | None:
        """Find a playlist by exact name."""
        row = self.conn.execute(
            "SELECT * FROM playlists WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return Playlist(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            auto_reorder=bool(row["auto_reorder"]),
            reorder_arc=row["reorder_arc"],
        )
