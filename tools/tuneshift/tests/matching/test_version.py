"""Tests for the source-aware version-class model (Chunk 4)."""
import pytest

from tuneshift.matching.version import (
    RecordingClass,
    VersionProfile,
    VersionVerdict,
    compare_version,
    infer_version,
)


# --- infer_version -----------------------------------------------------------


class TestInferVersion:
    def test_plain_studio_track_is_studio(self):
        p = infer_version("Bohemian Rhapsody", "A Night at the Opera")
        assert p.recording is RecordingClass.STUDIO
        assert not p.is_remaster

    def test_a_night_at_the_opera_is_not_live(self):
        # Regression for the _LIVE_RE bare "at the" false positive.
        p = infer_version("Bohemian Rhapsody", "A Night at the Opera")
        assert p.recording is RecordingClass.STUDIO

    def test_live_at_the_apollo_is_live(self):
        # "live" boundary still fires even with "at the" removed from the regex.
        p = infer_version("Can I Kick It? (Live)", "Live at the Apollo")
        assert p.recording is RecordingClass.LIVE

    def test_karaoke_beats_live_in_priority(self):
        p = infer_version("Song (Karaoke Live Version)", "")
        assert p.recording is RecordingClass.KARAOKE

    @pytest.mark.parametrize("title,expected", [
        ("Song (Karaoke Version)", RecordingClass.KARAOKE),
        ("Song - Instrumental", RecordingClass.INSTRUMENTAL),
        ("Song (Remix)", RecordingClass.REMIX),
        ("Song (Acoustic)", RecordingClass.ACOUSTIC),
        ("Song (Live)", RecordingClass.LIVE),
        ("Song (Tribute)", RecordingClass.TRIBUTE),
        ("Song", RecordingClass.STUDIO),
    ])
    def test_recording_class_detection(self, title, expected):
        assert infer_version(title, "").recording is expected

    def test_remaster_flag(self):
        p = infer_version("Song", "Album (2011 Remaster)")
        assert p.is_remaster
        assert p.recording is RecordingClass.STUDIO

    def test_explicit_and_clean_flags(self):
        assert infer_version("Song (Explicit)", "").is_explicit
        assert infer_version("Song (Clean)", "").is_clean
        assert not infer_version("Song", "").is_explicit


# --- compare_version ---------------------------------------------------------


STUDIO = VersionProfile(RecordingClass.STUDIO)
LIVE = VersionProfile(RecordingClass.LIVE)
KARAOKE = VersionProfile(RecordingClass.KARAOKE)


class TestCompareVersion:
    def test_studio_to_studio_matches(self):
        assert compare_version(STUDIO, STUDIO) is VersionVerdict.MATCH

    def test_studio_source_rejects_live_candidate(self):
        assert compare_version(STUDIO, LIVE) is VersionVerdict.REJECT

    def test_studio_source_rejects_karaoke_candidate(self):
        assert compare_version(STUDIO, KARAOKE) is VersionVerdict.REJECT

    def test_live_source_matches_live_candidate(self):
        assert compare_version(LIVE, LIVE) is VersionVerdict.MATCH

    def test_live_source_gets_studio_as_substitute(self):
        # Requested a live take; only the studio master exists -> fallback.
        assert compare_version(LIVE, STUDIO) is VersionVerdict.SUBSTITUTE

    def test_two_different_non_studio_recordings_reject(self):
        assert compare_version(LIVE, KARAOKE) is VersionVerdict.REJECT

    def test_remaster_of_same_recording_is_soft(self):
        remastered = VersionProfile(RecordingClass.STUDIO, is_remaster=True)
        assert compare_version(STUDIO, remastered) is VersionVerdict.SOFT

    def test_remaster_source_and_candidate_still_matches(self):
        remastered = VersionProfile(RecordingClass.STUDIO, is_remaster=True)
        assert compare_version(remastered, remastered) is VersionVerdict.MATCH


class TestExplicitCleanAxis:
    def test_explicit_source_rejects_clean_candidate(self):
        # CeeLo Green "Fuck You" (explicit) must NOT match "Forget You" (clean).
        explicit = VersionProfile(RecordingClass.STUDIO, is_explicit=True)
        clean = VersionProfile(RecordingClass.STUDIO, is_clean=True)
        assert compare_version(explicit, clean) is VersionVerdict.REJECT

    def test_clean_source_gets_explicit_as_substitute(self):
        clean = VersionProfile(RecordingClass.STUDIO, is_clean=True)
        explicit = VersionProfile(RecordingClass.STUDIO, is_explicit=True)
        assert compare_version(clean, explicit) is VersionVerdict.SUBSTITUTE


class TestPreferenceOverrides:
    def test_prefer_live_lets_live_beat_studio_source(self):
        # A live-takes playlist: live candidate must win against a studio source.
        assert compare_version(
            STUDIO, LIVE, prefer=frozenset({"live"})
        ) is VersionVerdict.MATCH

    def test_avoid_live_hard_rejects_even_for_live_source(self):
        assert compare_version(
            LIVE, LIVE, avoid=frozenset({"live"})
        ) is VersionVerdict.REJECT

    def test_avoid_takes_precedence_over_prefer(self):
        assert compare_version(
            STUDIO, LIVE, prefer=frozenset({"live"}), avoid=frozenset({"live"})
        ) is VersionVerdict.REJECT


class TestTribeRealWorldCases:
    def test_studio_source_rejects_live_compilation_take(self):
        src = infer_version("Can I Kick It?",
                            "People's Instinctive Travels and the Paths of Rhythm")
        cand = infer_version("Can I Kick It? (Live)", "Live at the Apollo")
        assert compare_version(src, cand) is VersionVerdict.REJECT

    def test_studio_source_matches_remastered_reissue_softly(self):
        src = infer_version("Can I Kick It?",
                            "People's Instinctive Travels and the Paths of Rhythm")
        cand = infer_version(
            "Can I Kick It?",
            "People's Instinctive Travels (25th Anniversary Remaster)",
        )
        assert compare_version(src, cand) is VersionVerdict.SOFT
