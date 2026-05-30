"""Tests for the metadata cache."""
import json
import pytest
from tidal_importer.sequencer.cache import TrackMetadata, MetadataCache


def test_track_metadata_from_dict():
    data = {
        "isrc": "USRC17607839",
        "tidal_id": 123456,
        "title": "Hotel California",
        "artist": "Eagles",
        "duration_ms": 391000,
        "bpm": 147.0,
        "key_note": 7,
        "mode": 0,
        "energy": 0.54,
        "valence": 0.24,
        "acousticness": 0.02,
        "loudness": -7.5,
        "danceability": 0.5,
        "themes": ["loneliness", "excess", "california"],
        "vibes": ["haunting", "dark", "hypnotic"],
        "instruments": ["electric guitar", "drums", "bass"],
        "density": "mid",
        "era_mood": ["mid 70s rock", "west coast"],
        "lastfm_tags": ["classic rock", "70s"],
        "camelot_code": "7A",
        "source": "spotify",
    }
    meta = TrackMetadata.from_dict(data)
    assert meta.isrc == "USRC17607839"
    assert meta.bpm == 147.0
    assert meta.themes == ["loneliness", "excess", "california"]
    assert meta.density == "mid"


@pytest.fixture
def cache(tmp_path):
    db_path = tmp_path / "test_metadata.db"
    return MetadataCache(db_path)


def test_cache_save_and_load(cache):
    meta = TrackMetadata(
        isrc="USRC17607839",
        tidal_id=123456,
        title="Hotel California",
        artist="Eagles",
        bpm=147.0,
        key_note=7,
        mode=0,
        energy=0.54,
        valence=0.24,
        themes=["loneliness", "excess"],
        vibes=["haunting", "dark"],
        instruments=["electric guitar", "drums"],
        density="mid",
        era_mood=["mid 70s rock"],
        source="spotify",
    )
    cache.save(meta)
    loaded = cache.get("USRC17607839")
    assert loaded is not None
    assert loaded.isrc == "USRC17607839"
    assert loaded.bpm == 147.0
    assert loaded.themes == ["loneliness", "excess"]


def test_cache_get_missing_returns_none(cache):
    assert cache.get("NONEXISTENT") is None


def test_cache_get_many(cache):
    for i in range(3):
        cache.save(TrackMetadata(
            isrc=f"ISRC{i:010d}",
            tidal_id=i,
            title=f"Track {i}",
            artist=f"Artist {i}",
        ))
    results = cache.get_many(["ISRC0000000000", "ISRC0000000002", "MISSING"])
    assert len(results) == 2
    assert results["ISRC0000000000"].title == "Track 0"
    assert "MISSING" not in results


def test_cache_save_overwrites(cache):
    meta1 = TrackMetadata(isrc="X", tidal_id=1, title="Old", artist="A")
    meta2 = TrackMetadata(isrc="X", tidal_id=1, title="New", artist="A", bpm=120.0)
    cache.save(meta1)
    cache.save(meta2)
    loaded = cache.get("X")
    assert loaded.title == "New"
    assert loaded.bpm == 120.0
