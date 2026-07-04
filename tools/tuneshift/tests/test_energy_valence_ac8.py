"""FL2 AC8: energy/valence sourcing + manual override + wave-arc warning.

The wave sequencer orders by energy/valence; nothing populated them, so it
silently fell back to 0.5 for every track (a flat, meaningless order). AC8:
estimate them (Spotify-via-ISRC -> LLM), let the user override manually with
`edit --energy/--valence` (manual provenance), and warn before a wave order when
most tracks lack data.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from tuneshift.commands.edit_cmd import handle_edit
from tuneshift.commands.order_cmd import _warn_if_energy_sparse
from tuneshift.db import Database
from tuneshift.enrichment.audio_features import (
    estimate_energy_valence,
    spotify_audio_features_via_isrc,
)
from tuneshift.models import Track


# --- manual override (edit --energy/--valence) -------------------------------
def test_edit_sets_energy_valence_with_manual_provenance(tmp_path: Path) -> None:
    db = Database(tmp_path / "edit.db")
    track_id = db.add_track(Track(title="Levitating", artist="Dua Lipa"))

    args = Namespace(
        track_id=track_id, title=None, artist=None, album=None,
        energy=0.85, valence=0.9, strip_album_from_title=False, dry_run=False,
    )
    assert handle_edit(args, db) == 0

    track = db.get_track(track_id)
    assert track.energy == 0.85
    assert track.valence == 0.9
    assert track.field_provenance["energy"]["source"] == "manual"


def test_edit_rejects_out_of_range(tmp_path: Path) -> None:
    db = Database(tmp_path / "edit2.db")
    track_id = db.add_track(Track(title="X", artist="Y"))
    args = Namespace(
        track_id=track_id, title=None, artist=None, album=None,
        energy=1.5, valence=None, strip_album_from_title=False, dry_run=False,
    )
    assert handle_edit(args, db) == 1
    assert db.get_track(track_id).energy is None


# --- estimation chain --------------------------------------------------------
def test_spotify_via_isrc_returns_none_without_client() -> None:
    # Spotify audio-features deprecated 2024-11; no fabrication without a client.
    assert spotify_audio_features_via_isrc("USUM71234567") is None
    assert spotify_audio_features_via_isrc(None) is None


def test_spotify_via_isrc_reads_injected_client() -> None:
    class _Client:
        def audio_features_by_isrc(self, _isrc):
            return {"energy": 0.7, "valence": 0.3}

    assert spotify_audio_features_via_isrc("X", client=_Client()) == (0.7, 0.3)


def test_estimate_uses_llm_and_clamps() -> None:
    class _Backend:
        def complete(self, *_a, **_k):
            return '{"energy": 1.4, "valence": -0.2}'  # out of range -> clamped

    class _Classifier:
        available = True
        _backend = _Backend()
        _model = "test"

    result = estimate_energy_valence("Song", "Artist", classifier=_Classifier())
    assert result == (1.0, 0.0)


def test_estimate_none_when_classifier_unavailable() -> None:
    class _Classifier:
        available = False

    assert estimate_energy_valence("S", "A", classifier=_Classifier()) is None


# --- wave-arc coverage warning ----------------------------------------------
def test_wave_warning_fires_when_sparse(capsys) -> None:
    tracks = [
        Track(title="a", artist="x", energy=0.5, valence=0.5),
        Track(title="b", artist="x"),
        Track(title="c", artist="x"),
    ]
    _warn_if_energy_sparse(tracks)
    err = capsys.readouterr().err
    assert "lack energy/valence" in err
    assert "2/3" in err


def test_wave_warning_silent_when_covered(capsys) -> None:
    tracks = [Track(title="a", artist="x", energy=0.5, valence=0.5)]
    _warn_if_energy_sparse(tracks)
    assert capsys.readouterr().err == ""
