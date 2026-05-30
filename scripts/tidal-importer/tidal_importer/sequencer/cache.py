"""SQLite metadata cache for track audio features and classifications."""
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CACHE_DIR = Path.home() / ".local" / "share" / "tidal-importer"
CACHE_DB = CACHE_DIR / "track_metadata.db"


@dataclass
class TrackMetadata:
    """Complete metadata for a single track across all sources."""

    isrc: str
    tidal_id: int
    title: str
    artist: str
    duration_ms: int | None = None

    # Spotify/MusicBrainz features
    bpm: float | None = None
    key_note: int | None = None  # 0-11 (C=0, C#=1, ... B=11)
    mode: int | None = None  # 0=minor, 1=major
    energy: float | None = None  # 0.0-1.0
    valence: float | None = None  # 0.0-1.0
    acousticness: float | None = None  # 0.0-1.0
    loudness: float | None = None  # dB
    danceability: float | None = None  # 0.0-1.0

    # LLM classification
    themes: list[str] = field(default_factory=list)
    vibes: list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    density: str | None = None  # sparse/mid/dense
    era_mood: list[str] = field(default_factory=list)

    # Last.fm
    lastfm_tags: list[str] = field(default_factory=list)

    # Derived
    camelot_code: str | None = None
    source: str | None = None  # spotify/musicbrainz/hybrid

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrackMetadata":
        """Create from a dict (handles JSON list fields)."""
        return cls(
            isrc=data["isrc"],
            tidal_id=data["tidal_id"],
            title=data["title"],
            artist=data["artist"],
            duration_ms=data.get("duration_ms"),
            bpm=data.get("bpm"),
            key_note=data.get("key_note"),
            mode=data.get("mode"),
            energy=data.get("energy"),
            valence=data.get("valence"),
            acousticness=data.get("acousticness"),
            loudness=data.get("loudness"),
            danceability=data.get("danceability"),
            themes=data.get("themes", []),
            vibes=data.get("vibes", []),
            instruments=data.get("instruments", []),
            density=data.get("density"),
            era_mood=data.get("era_mood", []),
            lastfm_tags=data.get("lastfm_tags", []),
            camelot_code=data.get("camelot_code"),
            source=data.get("source"),
        )

    def has_audio_features(self) -> bool:
        """True if Spotify/MB audio features are populated."""
        return self.bpm is not None and self.energy is not None

    def has_classification(self) -> bool:
        """True if LLM classification is populated."""
        return len(self.themes) > 0 and len(self.vibes) > 0


_SCHEMA = """
CREATE TABLE IF NOT EXISTS track_metadata (
    isrc TEXT PRIMARY KEY,
    tidal_id INTEGER,
    title TEXT,
    artist TEXT,
    duration_ms INTEGER,
    bpm REAL,
    key_note INTEGER,
    mode INTEGER,
    energy REAL,
    valence REAL,
    acousticness REAL,
    loudness REAL,
    danceability REAL,
    themes TEXT,
    vibes TEXT,
    instruments TEXT,
    density TEXT,
    era_mood TEXT,
    lastfm_tags TEXT,
    camelot_code TEXT,
    fetched_at TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_tidal_id ON track_metadata(tidal_id);
"""


class MetadataCache:
    """SQLite-backed metadata cache. Thread-safe for single-writer use."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or CACHE_DB
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def save(self, meta: TrackMetadata) -> None:
        """Upsert a track's metadata."""
        from datetime import datetime, timezone

        self._conn.execute(
            """INSERT OR REPLACE INTO track_metadata
               (isrc, tidal_id, title, artist, duration_ms,
                bpm, key_note, mode, energy, valence, acousticness,
                loudness, danceability, themes, vibes, instruments,
                density, era_mood, lastfm_tags, camelot_code, fetched_at, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                meta.isrc, meta.tidal_id, meta.title, meta.artist, meta.duration_ms,
                meta.bpm, meta.key_note, meta.mode, meta.energy, meta.valence,
                meta.acousticness, meta.loudness, meta.danceability,
                json.dumps(meta.themes), json.dumps(meta.vibes),
                json.dumps(meta.instruments), meta.density,
                json.dumps(meta.era_mood), json.dumps(meta.lastfm_tags),
                meta.camelot_code,
                datetime.now(timezone.utc).isoformat(),
                meta.source,
            ),
        )
        self._conn.commit()

    def get(self, isrc: str) -> TrackMetadata | None:
        """Load a single track by ISRC. Returns None if not cached."""
        row = self._conn.execute(
            "SELECT * FROM track_metadata WHERE isrc = ?", (isrc,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_metadata(row)

    def get_many(self, isrcs: list[str]) -> dict[str, TrackMetadata]:
        """Load multiple tracks by ISRC. Returns dict of found entries."""
        if not isrcs:
            return {}
        placeholders = ",".join("?" * len(isrcs))
        rows = self._conn.execute(
            f"SELECT * FROM track_metadata WHERE isrc IN ({placeholders})",
            isrcs,
        ).fetchall()
        return {row["isrc"]: self._row_to_metadata(row) for row in rows}

    def _row_to_metadata(self, row: sqlite3.Row) -> TrackMetadata:
        return TrackMetadata(
            isrc=row["isrc"],
            tidal_id=row["tidal_id"],
            title=row["title"],
            artist=row["artist"],
            duration_ms=row["duration_ms"],
            bpm=row["bpm"],
            key_note=row["key_note"],
            mode=row["mode"],
            energy=row["energy"],
            valence=row["valence"],
            acousticness=row["acousticness"],
            loudness=row["loudness"],
            danceability=row["danceability"],
            themes=json.loads(row["themes"]) if row["themes"] else [],
            vibes=json.loads(row["vibes"]) if row["vibes"] else [],
            instruments=json.loads(row["instruments"]) if row["instruments"] else [],
            density=row["density"],
            era_mood=json.loads(row["era_mood"]) if row["era_mood"] else [],
            lastfm_tags=json.loads(row["lastfm_tags"]) if row["lastfm_tags"] else [],
            camelot_code=row["camelot_code"],
            source=row["source"],
        )

    def close(self) -> None:
        self._conn.close()
