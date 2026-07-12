"""Tidal captures the structured explicit flag on search candidates (Task 2)."""

from types import SimpleNamespace

from tuneshift.platforms.tidal import TidalClient


def _fake_track(explicit):
    return SimpleNamespace(
        id=1, name="Song", artist=SimpleNamespace(name="A"),
        album=None, duration=200, isrc="X", available=True,
        premium_streaming_only=False, pay_to_stream=False,
        audio_modes=None, media_metadata_tags=None, audio_quality=None,
        version=None, explicit=explicit,
    )


def test_track_to_result_captures_explicit_true():
    assert TidalClient._track_to_result(_fake_track(True)).explicit is True


def test_track_to_result_captures_explicit_false():
    assert TidalClient._track_to_result(_fake_track(False)).explicit is False


def test_track_to_result_missing_explicit_is_none():
    t = _fake_track(True)
    del t.explicit
    assert TidalClient._track_to_result(t).explicit is None
