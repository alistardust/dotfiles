"""Task 1.2 (BUILD-FIRST): capture native Tidal version/audio metadata.

TidalClient.get_track_metadata must preserve the native audio_modes / audio_quality
/ version / media_metadata_tags that settle the Atmos/named-mix/fidelity axes, and
TrackResult must carry them (plus album_artist / album_type) for the matching path.
This spec OWNS the capture edit (spec §14); enrichment owns derive_tags wiring.
"""

from tuneshift.models import TrackResult
from tuneshift.platforms.tidal import TidalClient


class _FakeSession:
    def __init__(self, track):
        self._track = track

    def check_login(self):
        return True

    def track(self, _id):
        return self._track


class _FakeTrack:
    bpm = 120.0
    duration = 245
    key = "C"
    key_scale = "major"
    isrc = "USUM71234567"
    audio_modes = ["DOLBY_ATMOS"]
    audio_quality = "HI_RES_LOSSLESS"
    version = "Dolby Atmos"
    media_metadata_tags = ["HIRES_LOSSLESS", "DOLBY_ATMOS"]


def _client_with(track):
    client = TidalClient()
    client._session = _FakeSession(track)
    return client


def test_get_track_metadata_captures_native_audio_fields():
    meta = _client_with(_FakeTrack()).get_track_metadata("123")
    assert meta is not None
    assert meta["audio_modes"] == ["DOLBY_ATMOS"]
    assert meta["audio_quality"] == "HI_RES_LOSSLESS"
    assert meta["tidal_version"] == "Dolby Atmos"
    assert meta["media_metadata_tags"] == ["HIRES_LOSSLESS", "DOLBY_ATMOS"]
    # existing fields still captured
    assert meta["isrc"] == "USUM71234567"
    assert meta["tempo"] == 120.0


def test_get_track_metadata_defensive_when_attrs_absent():
    class _Bare:
        bpm = None
        duration = 200
        key = None
        isrc = None

    meta = _client_with(_Bare()).get_track_metadata("1")
    assert meta is not None
    assert "audio_modes" not in meta
    assert "audio_quality" not in meta
    assert "tidal_version" not in meta
    assert meta["duration_seconds"] == 200


def test_track_result_carries_native_audio_fields():
    r = TrackResult(
        platform_id="1",
        title="T",
        artist="A",
        album="Al",
        audio_modes=["DOLBY_ATMOS"],
        audio_quality="HI_RES_LOSSLESS",
        tidal_version="Dolby Atmos",
        album_artist="A",
        album_type="ALBUM",
    )
    assert r.audio_modes == ["DOLBY_ATMOS"]
    assert r.audio_quality == "HI_RES_LOSSLESS"
    assert r.tidal_version == "Dolby Atmos"
    assert r.album_artist == "A"
    assert r.album_type == "ALBUM"


def test_track_result_native_audio_fields_default_none():
    r = TrackResult(platform_id="1", title="T", artist="A", album="Al")
    assert r.audio_modes is None
    assert r.audio_quality is None
    assert r.tidal_version is None
    assert r.album_artist is None
    assert r.album_type is None
