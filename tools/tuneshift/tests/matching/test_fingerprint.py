"""Tests for the durable track fingerprint (self-healing lock identity)."""
from tuneshift.matching import (
    TrackFingerprint,
    build_fingerprint,
    fingerprint_equal,
)


def test_isrc_is_authoritative_when_both_present():
    a = build_fingerprint(title="Heroes", artist="David Bowie", isrc="GBAYE7700012",
                          duration_seconds=371)
    # Different title/artist/duration but same ISRC -> same recording.
    b = build_fingerprint(title="Held", artist="D. Bowie", isrc="gb-aye-77-00012",
                          duration_seconds=999)
    assert fingerprint_equal(a, b)


def test_different_isrc_never_equal():
    a = build_fingerprint(title="Heroes", artist="David Bowie", isrc="GBAYE7700012")
    b = build_fingerprint(title="Heroes", artist="David Bowie", isrc="USRC17607839")
    assert not fingerprint_equal(a, b)


def test_falls_back_to_title_artist_class_when_isrc_absent():
    a = build_fingerprint(title="Heroes", artist="David Bowie", duration_seconds=371)
    b = build_fingerprint(title="heroes", artist="DAVID BOWIE", duration_seconds=372)
    assert fingerprint_equal(a, b)


def test_isrc_on_one_side_only_uses_fallback():
    a = build_fingerprint(title="Heroes", artist="David Bowie", isrc="GBAYE7700012",
                          duration_seconds=371)
    b = build_fingerprint(title="Heroes", artist="David Bowie", duration_seconds=371)
    assert fingerprint_equal(a, b)


def test_duration_bucket_rejects_far_durations():
    a = build_fingerprint(title="Song", artist="A", duration_seconds=200)
    b = build_fingerprint(title="Song", artist="A", duration_seconds=260)
    assert not fingerprint_equal(a, b)
    assert not fingerprint_equal(a, b, duration_bucket_seconds=2)
    assert fingerprint_equal(a, b, duration_bucket_seconds=60)


def test_unknown_duration_is_not_a_mismatch():
    a = build_fingerprint(title="Song", artist="A", duration_seconds=None)
    b = build_fingerprint(title="Song", artist="A", duration_seconds=200)
    assert fingerprint_equal(a, b)


def test_version_class_distinguishes_live_from_studio():
    studio = build_fingerprint(title="Song", artist="A", duration_seconds=200)
    live = build_fingerprint(title="Song (Live)", artist="A", duration_seconds=200)
    assert studio.recording_class == "studio"
    assert live.recording_class == "live"
    assert not fingerprint_equal(studio, live)


def test_explicit_recording_class_override():
    fp = build_fingerprint(title="Song", artist="A", recording_class="live")
    assert fp.recording_class == "live"


def test_round_trip_dict():
    fp = build_fingerprint(title="Heroes", artist="David Bowie", isrc="GBAYE7700012",
                          duration_seconds=371)
    restored = TrackFingerprint.from_dict(fp.as_dict())
    assert restored == fp
