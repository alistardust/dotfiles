"""Tests for the sequence optimizer."""
import pytest

from tidal_importer.sequencer.cache import TrackMetadata
from tidal_importer.sequencer.optimizer import (
    break_artist_runs,
    optimize_sequence,
    select_closer,
    select_opener,
)
from tidal_importer.sequencer.profiles import DEFAULT_WEIGHTS


def _make_track(
    idx: int,
    artist: str = "Artist",
    energy: float = 0.5,
    themes: list[str] | None = None,
    bpm: float = 120.0,
) -> TrackMetadata:
    """Helper to create test tracks."""
    return TrackMetadata(
        isrc=f"ISRC{idx:010d}",
        tidal_id=idx,
        title=f"Track {idx}",
        artist=artist,
        bpm=bpm,
        energy=energy,
        valence=0.5,
        acousticness=0.5,
        mode=1,
        key_note=0,
        camelot_code="8B",
        themes=themes or ["love"],
        vibes=["warm"],
        instruments=["guitar"],
        density="mid",
        era_mood=["70s rock"],
    )


class TestBreakArtistRuns:
    def test_no_runs_unchanged(self):
        tracks = [_make_track(i, f"Artist{i}") for i in range(5)]
        result = break_artist_runs(tracks, min_separation=4)
        assert [track.tidal_id for track in result] == [0, 1, 2, 3, 4]

    def test_breaks_run_of_three(self):
        tracks = [
            _make_track(0, "A"),
            _make_track(1, "A"),
            _make_track(2, "A"),
            _make_track(3, "B"),
            _make_track(4, "C"),
        ]
        result = break_artist_runs(tracks, min_separation=2)
        artists = [track.artist for track in result]
        for index in range(len(artists) - 2):
            assert not (artists[index] == artists[index + 1] == artists[index + 2] == "A")


class TestSelectOpener:
    def test_prefers_mid_energy_for_wave(self):
        tracks = [
            _make_track(0, energy=0.9),
            _make_track(1, energy=0.5),
            _make_track(2, energy=0.1),
        ]
        opener = select_opener(tracks, arc="wave")
        assert opener.energy == 0.5


class TestSelectCloser:
    def test_prefers_low_energy_major_mode(self):
        tracks = [
            _make_track(0, energy=0.9),
            _make_track(1, energy=0.3),
            _make_track(2, energy=0.2),
        ]
        closer = select_closer(tracks, arc="wave")
        assert closer.energy <= 0.3


class TestOptimizeSequence:
    def test_returns_all_tracks(self):
        tracks = [_make_track(i, f"Artist{i}") for i in range(10)]
        result = optimize_sequence(tracks, DEFAULT_WEIGHTS, arc="free")
        assert len(result) == 10
        assert {track.tidal_id for track in result} == set(range(10))

    def test_respects_artist_separation(self):
        tracks = [_make_track(i, "Same") for i in range(5)]
        tracks += [_make_track(i + 5, f"Other{i}") for i in range(5)]
        result = optimize_sequence(
            tracks,
            DEFAULT_WEIGHTS,
            arc="free",
            artist_min_separation=2,
        )
        artists = [track.artist for track in result]
        for index in range(len(artists) - 2):
            assert not (
                artists[index] == artists[index + 1] == artists[index + 2] == "Same"
            )

    def test_short_playlist_works(self):
        tracks = [_make_track(i, f"A{i}") for i in range(3)]
        result = optimize_sequence(tracks, DEFAULT_WEIGHTS, arc="free")
        assert len(result) == 3
