"""SQLite database for track identity resolution."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tidal_importer.identity.models import (
    Album,
    Artist,
    Evidence,
    Recording,
    RecordingCandidate,
    ResolutionResult,
)

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS artists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    mb_artist_id TEXT,
    discogs_artist_id INTEGER,
    sort_name TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recordings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist_id TEXT NOT NULL REFERENCES artists(id),
    mb_recording_id TEXT,
    duration_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS isrcs (
    isrc TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(id),
    source TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS albums (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist_id TEXT REFERENCES artists(id),
    mb_release_group_id TEXT,
    discogs_master_id INTEGER,
    primary_type TEXT,
    secondary_types TEXT,
    release_year INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS releases (
    id TEXT PRIMARY KEY,
    album_id TEXT NOT NULL REFERENCES albums(id),
    title TEXT NOT NULL,
    mb_release_id TEXT,
    discogs_release_id INTEGER,
    release_year INTEGER,
    release_country TEXT,
    is_remaster INTEGER DEFAULT 0,
    is_deluxe INTEGER DEFAULT 0,
    is_expanded INTEGER DEFAULT 0,
    label TEXT,
    catalog_number TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS platform_tracks (
    id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(id),
    platform TEXT NOT NULL,
    platform_track_id TEXT NOT NULL,
    platform_album_id TEXT,
    album_id TEXT REFERENCES albums(id),
    release_id TEXT REFERENCES releases(id),
    duration_ms INTEGER,
    isrc TEXT,
    quality_tier TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(platform, platform_track_id)
);

CREATE TABLE IF NOT EXISTS recording_albums (
    recording_id TEXT NOT NULL REFERENCES recordings(id),
    album_id TEXT NOT NULL REFERENCES albums(id),
    track_number INTEGER,
    is_original_album INTEGER DEFAULT 0,
    PRIMARY KEY (recording_id, album_id)
);

CREATE TABLE IF NOT EXISTS resolution_evidence (
    id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(id),
    source TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    raw_data TEXT,
    is_current INTEGER DEFAULT 1,
    superseded_by TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resolution_candidates (
    id TEXT PRIMARY KEY,
    artist_query TEXT NOT NULL,
    title_query TEXT NOT NULL,
    tidal_track_id TEXT,
    duration_ms INTEGER,
    status TEXT DEFAULT 'pending',
    resolved_recording_id TEXT REFERENCES recordings(id),
    candidate_data TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS playlists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version_preference TEXT DEFAULT 'original',
    platform TEXT DEFAULT 'tidal',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id TEXT NOT NULL REFERENCES playlists(id),
    recording_id TEXT NOT NULL REFERENCES recordings(id),
    position INTEGER NOT NULL,
    platform_track_id TEXT,
    version_preference TEXT,
    pinned_platform_track_id TEXT,
    confidence TEXT DEFAULT 'UNCERTAIN',
    is_pinned INTEGER DEFAULT 0,
    PRIMARY KEY (playlist_id, position)
);

CREATE TABLE IF NOT EXISTS recording_preferences (
    recording_id TEXT PRIMARY KEY REFERENCES recordings(id),
    preferred_platform_track_id TEXT,
    version_preference TEXT NOT NULL,
    reason TEXT,
    pinned_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audio_features (
    recording_id TEXT PRIMARY KEY REFERENCES recordings(id),
    bpm REAL,
    key TEXT,
    energy REAL,
    valence REAL,
    danceability REAL,
    acousticness REAL,
    instrumentalness REAL,
    speechiness REAL,
    loudness_integrated REAL,
    loudness_range REAL,
    dynamic_range REAL,
    true_peak REAL,
    source TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_artists_mb
    ON artists(mb_artist_id) WHERE mb_artist_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_recordings_mb
    ON recordings(mb_recording_id) WHERE mb_recording_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_albums_mb
    ON albums(mb_release_group_id) WHERE mb_release_group_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_artists_discogs
    ON artists(discogs_artist_id) WHERE discogs_artist_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_albums_discogs
    ON albums(discogs_master_id) WHERE discogs_master_id IS NOT NULL;
"""


class IdentityDB:
    """SQLite database for track identity resolution."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn = sqlite3.connect(str(path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version < SCHEMA_VERSION:
            self.conn.executescript(SCHEMA_SQL)
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def list_tables(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return [r[0] for r in rows]

    def upsert_artist(self, artist: Artist) -> None:
        self.conn.execute(
            "INSERT INTO artists (id, name, mb_artist_id, discogs_artist_id, sort_name) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "name=excluded.name, mb_artist_id=excluded.mb_artist_id, "
            "discogs_artist_id=excluded.discogs_artist_id, sort_name=excluded.sort_name, "
            "updated_at=datetime('now')",
            (artist.id, artist.name, artist.mb_artist_id, artist.discogs_artist_id, artist.sort_name),
        )
        self.conn.commit()

    def get_artist(self, artist_id: str) -> Artist | None:
        row = self.conn.execute(
            "SELECT id, name, mb_artist_id, discogs_artist_id, sort_name "
            "FROM artists WHERE id = ?", (artist_id,)
        ).fetchone()
        if row is None:
            return None
        return Artist(id=row[0], name=row[1], mb_artist_id=row[2],
                      discogs_artist_id=row[3], sort_name=row[4])

    def get_artist_by_mb_id(self, mb_artist_id: str) -> Artist | None:
        row = self.conn.execute(
            "SELECT id, name, mb_artist_id, discogs_artist_id, sort_name "
            "FROM artists WHERE mb_artist_id = ?", (mb_artist_id,)
        ).fetchone()
        if row is None:
            return None
        return Artist(id=row[0], name=row[1], mb_artist_id=row[2],
                      discogs_artist_id=row[3], sort_name=row[4])

    def upsert_recording(self, recording: Recording) -> None:
        self.conn.execute(
            "INSERT INTO recordings (id, title, artist_id, mb_recording_id, duration_ms) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "title=excluded.title, mb_recording_id=excluded.mb_recording_id, "
            "duration_ms=excluded.duration_ms, updated_at=datetime('now')",
            (recording.id, recording.title, recording.artist_id,
             recording.mb_recording_id, recording.duration_ms),
        )
        self.conn.commit()

    def get_recording(self, recording_id: str) -> Recording | None:
        row = self.conn.execute(
            "SELECT id, title, artist_id, mb_recording_id, duration_ms "
            "FROM recordings WHERE id = ?", (recording_id,)
        ).fetchone()
        if row is None:
            return None
        return Recording(id=row[0], title=row[1], artist_id=row[2],
                         mb_recording_id=row[3], duration_ms=row[4])

    def get_recording_by_mb_id(self, mb_recording_id: str) -> Recording | None:
        row = self.conn.execute(
            "SELECT id, title, artist_id, mb_recording_id, duration_ms "
            "FROM recordings WHERE mb_recording_id = ?", (mb_recording_id,)
        ).fetchone()
        if row is None:
            return None
        return Recording(id=row[0], title=row[1], artist_id=row[2],
                         mb_recording_id=row[3], duration_ms=row[4])

    def upsert_album(self, album: Album) -> None:
        secondary_json = json.dumps(album.secondary_types)
        self.conn.execute(
            "INSERT INTO albums (id, title, artist_id, mb_release_group_id, "
            "discogs_master_id, primary_type, secondary_types, release_year) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "title=excluded.title, primary_type=excluded.primary_type, "
            "secondary_types=excluded.secondary_types, release_year=excluded.release_year, "
            "updated_at=datetime('now')",
            (album.id, album.title, album.artist_id, album.mb_release_group_id,
             album.discogs_master_id, album.primary_type, secondary_json, album.release_year),
        )
        self.conn.commit()

    def get_album(self, album_id: str) -> Album | None:
        row = self.conn.execute(
            "SELECT id, title, artist_id, mb_release_group_id, discogs_master_id, "
            "primary_type, secondary_types, release_year FROM albums WHERE id = ?",
            (album_id,),
        ).fetchone()
        if row is None:
            return None
        secondary = json.loads(row[6]) if row[6] else []
        return Album(id=row[0], title=row[1], artist_id=row[2],
                     mb_release_group_id=row[3], discogs_master_id=row[4],
                     primary_type=row[5], secondary_types=secondary, release_year=row[7])

    def add_evidence(self, evidence: Evidence) -> None:
        self.conn.execute(
            "INSERT INTO resolution_evidence "
            "(id, recording_id, source, evidence_type, confidence, raw_data, is_current) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (evidence.id, evidence.recording_id, evidence.source, evidence.evidence_type,
             evidence.confidence, evidence.raw_data, 1 if evidence.is_current else 0),
        )
        self.conn.commit()

    def supersede_evidence(self, old_id: str, new_id: str) -> None:
        self.conn.execute(
            "UPDATE resolution_evidence SET is_current = 0, superseded_by = ? WHERE id = ?",
            (new_id, old_id),
        )
        self.conn.commit()

    def get_evidence_for_recording(self, recording_id: str) -> list[Evidence]:
        rows = self.conn.execute(
            "SELECT id, recording_id, source, evidence_type, confidence, raw_data, "
            "is_current, superseded_by, created_at FROM resolution_evidence WHERE recording_id = ?",
            (recording_id,),
        ).fetchall()
        return [
            Evidence(id=r[0], recording_id=r[1], source=r[2], evidence_type=r[3],
                     confidence=r[4], raw_data=r[5], is_current=bool(r[6]),
                     superseded_by=r[7], created_at=r[8])
            for r in rows
        ]

    def get_current_evidence_for_recording(self, recording_id: str) -> list[Evidence]:
        rows = self.conn.execute(
            "SELECT id, recording_id, source, evidence_type, confidence, raw_data, "
            "is_current, superseded_by, created_at FROM resolution_evidence "
            "WHERE recording_id = ? AND is_current = 1",
            (recording_id,),
        ).fetchall()
        return [
            Evidence(id=r[0], recording_id=r[1], source=r[2], evidence_type=r[3],
                     confidence=r[4], raw_data=r[5], is_current=bool(r[6]),
                     superseded_by=r[7], created_at=r[8])
            for r in rows
        ]

    def close(self) -> None:
        self.conn.close()

    def get_resolved_track(self, platform: str, platform_id: str) -> ResolutionResult | None:
        """Get a resolved track by platform and platform ID."""
        row = self.execute(
            """SELECT pt.recording_id, r.title, a.name, r.mb_recording_id,
                      pt.platform, pt.platform_track_id, pt.created_at
               FROM platform_tracks pt
               JOIN recordings r ON pt.recording_id = r.id
               JOIN artists a ON r.artist_id = a.id
               WHERE pt.platform = ? AND pt.platform_track_id = ?""",
            (platform, platform_id),
        ).fetchone()
        if row is None:
            return None

        evidence = self.get_current_evidence_for_recording(row[0])

        from tidal_importer.identity.confidence import compute_confidence
        from tidal_importer.identity.models import ConfidenceTier
        from datetime import datetime, timezone

        if evidence:
            score, _ = compute_confidence(evidence)
        else:
            score = 0.0
        resolved_at_str = row[6]
        resolved_at = None
        if resolved_at_str:
            try:
                resolved_at = datetime.fromisoformat(resolved_at_str).replace(
                    tzinfo=timezone.utc
                )
            except (ValueError, TypeError):
                resolved_at = datetime.now(timezone.utc)

        return ResolutionResult(
            platform=row[4],
            platform_id=row[5],
            title=row[1],
            artist=row[2],
            mb_recording_id=row[3],
            confidence=score,
            tier=ConfidenceTier.from_score(score),
            evidence=evidence,
            resolved_at=resolved_at,
        )

    def store_resolved_track(self, resolved: ResolutionResult) -> None:
        """Store a resolved track (artist, recording, platform_track, evidence)."""
        import uuid

        artist_id = str(uuid.uuid4())
        self.execute(
            "INSERT OR IGNORE INTO artists (id, name) VALUES (?, ?)",
            (artist_id, resolved.artist),
        )
        # Get actual artist_id (may already exist)
        row = self.execute(
            "SELECT id FROM artists WHERE name = ?", (resolved.artist,)
        ).fetchone()
        if row:
            artist_id = row[0]

        recording_id = str(uuid.uuid4())
        self.execute(
            """INSERT OR IGNORE INTO recordings (id, title, artist_id, mb_recording_id)
               VALUES (?, ?, ?, ?)""",
            (recording_id, resolved.title, artist_id, resolved.mb_recording_id),
        )
        # Get actual recording_id
        if resolved.mb_recording_id:
            row = self.execute(
                "SELECT id FROM recordings WHERE mb_recording_id = ?",
                (resolved.mb_recording_id,),
            ).fetchone()
            if row:
                recording_id = row[0]

        pt_id = str(uuid.uuid4())
        resolved_at_str = None
        if resolved.resolved_at:
            resolved_at_str = resolved.resolved_at.strftime("%Y-%m-%d %H:%M:%S")
        self.execute(
            """INSERT OR REPLACE INTO platform_tracks
               (id, recording_id, platform, platform_track_id, created_at)
               VALUES (?, ?, ?, ?, COALESCE(?, datetime('now')))""",
            (pt_id, recording_id, resolved.platform, resolved.platform_id, resolved_at_str),
        )

        for ev in resolved.evidence:
            ev_with_recording = Evidence(
                id=ev.id,
                recording_id=recording_id,
                source=ev.source,
                evidence_type=ev.evidence_type,
                confidence=ev.confidence,
                raw_data=ev.raw_data,
                is_current=ev.is_current,
                superseded_by=ev.superseded_by,
                created_at=ev.created_at,
            )
            self.add_evidence(ev_with_recording)

    def store_candidates(
        self, platform: str, platform_id: str, candidates: list[RecordingCandidate]
    ) -> None:
        """Store unresolved candidates for future processing."""
        import json
        import uuid

        candidate_data = json.dumps([
            {
                "title": c.title,
                "artist": c.artist,
                "mb_recording_id": c.mb_recording_id,
                "duration_ms": c.duration_ms,
                "score": c.score,
            }
            for c in candidates
        ])

        artist_query = candidates[0].artist if candidates else ""
        title_query = candidates[0].title if candidates else ""

        self.execute(
            """INSERT OR REPLACE INTO resolution_candidates
               (id, artist_query, title_query, tidal_track_id, status, candidate_data)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (str(uuid.uuid4()), artist_query, title_query, platform_id, candidate_data),
        )

