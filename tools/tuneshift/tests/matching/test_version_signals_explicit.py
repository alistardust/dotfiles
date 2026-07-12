"""Structured explicit flag drives the lyric axis in both scoring paths (Task 4)."""

from tuneshift.matching.track import score_match_with_version, score_track_match
from tuneshift.models import TrackResult


def _legacy(cand_explicit, prefer=frozenset()):
    return score_match_with_version(
        "Song", "Artist", "Album",
        "Song", "Artist", "Album",
        cand_explicit=cand_explicit, prefer=prefer,
    )


def test_clean_candidate_scores_below_explicit_by_default():
    explicit = _legacy(True)
    clean = _legacy(False)
    unknown = _legacy(None)
    # Default prefers explicit: a structurally-clean candidate is down-ranked
    # (SUBSTITUTE) relative to an explicit/unknown one.
    assert clean < explicit
    assert unknown == _legacy(None)  # unknown is stable / parity


def test_prefer_clean_keeps_clean_a_match():
    explicit = _legacy(True, prefer=frozenset({"clean"}))
    clean = _legacy(False, prefer=frozenset({"clean"}))
    # With clean preferred, the clean candidate is no longer down-ranked.
    assert clean >= explicit


def _cand(explicit):
    return TrackResult(
        platform_id="c", title="Song", artist="Artist", album="Album",
        isrc="ISRC1", duration_seconds=200, explicit=explicit,
    )


def test_engine_path_also_prefers_explicit():
    # The engine ScoringContext path must behave like the legacy path. Distance
    # .total is a distance (higher == worse), so the clean candidate must score
    # a strictly greater distance than the explicit one.
    source = _cand(None)  # canonical source has no explicit signal
    explicit_dist = score_track_match(source, _cand(True)).total
    clean_dist = score_track_match(source, _cand(False)).total
    assert clean_dist > explicit_dist
