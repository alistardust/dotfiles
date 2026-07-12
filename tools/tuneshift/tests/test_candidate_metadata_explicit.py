"""BUG/feature: structured explicit flag captured on candidates (Task 1)."""

from tuneshift.models import (
    TrackResult,
    capture_candidate_metadata,
    trackresult_from_metadata,
)


def test_explicit_is_captured_and_roundtrips():
    r = TrackResult(platform_id="1", title="Song", artist="A", album="Al", explicit=True)
    meta = capture_candidate_metadata(r)
    assert meta["explicit"] is True
    back = trackresult_from_metadata("1", meta)
    assert back.explicit is True


def test_explicit_defaults_to_none_unknown():
    r = TrackResult(platform_id="1", title="S", artist="A", album="Al")
    assert r.explicit is None
    # A snapshot without the explicit key reconstructs to None (unknown).
    meta = capture_candidate_metadata(r)
    del meta["explicit"]
    back = trackresult_from_metadata("1", meta)
    assert back.explicit is None
