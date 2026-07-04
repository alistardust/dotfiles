"""Tests for the engine-native score_track_match entry point."""
from dataclasses import dataclass

from tuneshift.matching import score_match_with_version, score_track_match
from tuneshift.matching.engine import Recommendation, recommend


@dataclass
class T:
    title: str = ""
    artist: str = ""
    album: str | None = None
    isrc: str | None = None
    duration_seconds: int | None = None


def test_perfect_match_zero_distance_and_auto():
    # NB: avoid album/title text that trips legacy version regexes (e.g. the
    # "at the" substring matches _LIVE_RE — a known false positive that Chunk 4
    # version-safety will fix; Chunk 2 preserves it for byte-parity).
    src = T("Bohemian Rhapsody", "Queen", "Studio Album", "GBUM71029604", 355)
    cand = T("Bohemian Rhapsody", "Queen", "Studio Album", "GBUM71029604", 355)
    d = score_track_match(src, cand)
    assert d.total == 0.0
    assert recommend(d) is Recommendation.AUTO


def test_karaoke_candidate_is_rejected_despite_title_match():
    src = T("Bohemian Rhapsody", "Queen", "A Night at the Opera")
    cand = T("Bohemian Rhapsody (Karaoke Version)", "Queen", "Karaoke Hits")
    d = score_track_match(src, cand)
    # Source-aware: a studio source REJECTs a karaoke recording (the specific
    # class is collapsed into the verdict signal).
    assert d.has_signal("version:reject")
    assert recommend(d) is Recommendation.REJECT


def test_live_candidate_rejected_for_studio_source():
    # Studio source, live candidate -> wrong recording -> REJECT.
    src = T("Heroes", "David Bowie", '"Heroes"')
    cand = T("Heroes (Live)", "David Bowie", "Stage")
    d = score_track_match(src, cand)
    assert d.has_signal("version:reject")
    assert recommend(d) is Recommendation.REJECT


def test_live_source_matches_live_candidate():
    # Source is itself a live take -> a live candidate must MATCH, not be penalised.
    src = T("Heroes (Live)", "David Bowie", "Stage")
    cand = T("Heroes (Live)", "David Bowie", "Stage")
    d = score_track_match(src, cand)
    assert d.has_signal("version:match")
    assert not d.has_signal("version:reject")


def test_live_source_gets_studio_as_substitute():
    # Source is live; only the studio master exists -> SUBSTITUTE (findable,
    # capped below AUTO), not a silent perfect match.
    src = T("Heroes (Live)", "David Bowie", "Stage", None, 360)
    cand = T("Heroes", "David Bowie", '"Heroes"', None, 360)
    d = score_track_match(src, cand)
    assert d.has_signal("version:substitute")
    assert recommend(d) is not Recommendation.AUTO


def test_wrong_artist_increases_distance():
    src = T("Yesterday", "The Beatles", "Help!")
    cand = T("Yesterday", "Some Cover Band", "Tribute Hits")
    d = score_track_match(src, cand)
    # tribute keyword + artist mismatch -> not an auto accept
    assert recommend(d) is not Recommendation.AUTO


def test_points_matches_legacy_base_when_no_version_or_duration():
    from tuneshift.matching import score_match
    src = T("Song Title", "Artist", "Album")
    cand = T("Song Titel", "Artist", "Album")
    d = score_track_match(src, cand)
    # no version/duration signals fire, isrc absent -> raw point sum equals
    # the legacy object-form base score
    legacy = score_match(src, cand)
    assert d.points == legacy


# --- Descriptive-subtitle retitle blend (score_match_with_version) -----------


class TestSubtitleRetitleBlend:
    """A retitle that differs only in a trailing descriptive subtitle must
    still match, while genuinely different songs are not merged."""

    def test_true_retitle_is_rescued(self):
        # Same recording, same core title + album/duration, differing only in a
        # trailing descriptive subtitle — synthetic to keep the assertion honest.
        score = score_match_with_version(
            "Sample Song (One Descriptive Phrase)", "Some Artist",
            "Some Album",
            "Sample Song (Another Descriptive Phrase)", "Some Artist",
            "Some Album",
            result_duration=224, reference_duration=224,
        )
        assert score >= 80

    def test_retitle_still_costs_a_residual_penalty(self):
        # Same album, but the differing subtitle must not score a perfect 100 —
        # the residual penalty keeps a gap below an identical-title match.
        retitle = score_match_with_version(
            "Sample Song (One Descriptive Phrase)", "Some Artist",
            "Some Album",
            "Sample Song (Another Descriptive Phrase)", "Some Artist",
            "Some Album",
        )
        identical = score_match_with_version(
            "Sample Song (Another Descriptive Phrase)", "Some Artist",
            "Some Album",
            "Sample Song (Another Descriptive Phrase)", "Some Artist",
            "Some Album",
        )
        assert retitle < identical

    def test_different_songs_sharing_base_title_are_not_merged(self):
        # Same base "Untitled" but different subtitle, artist and album: the
        # title rescue must not lift this into match territory.
        score = score_match_with_version(
            "Untitled (How Does It Feel)", "D'Angelo", "Voodoo",
            "Untitled (Rise)", "Some Other Band", "Different Album",
        )
        assert score < 50

    def test_leading_paren_title_unaffected(self):
        # "(You Drive Me) Crazy" is a leading paren, not a trailing subtitle;
        # an identical match still scores a perfect 100.
        score = score_match_with_version(
            "(You Drive Me) Crazy", "Britney Spears", "...Baby One More Time",
            "(You Drive Me) Crazy", "Britney Spears", "...Baby One More Time",
        )
        assert score == 100
