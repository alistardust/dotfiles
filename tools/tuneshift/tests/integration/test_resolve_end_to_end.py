"""FL1a end-to-end proof: `add` -> `resolve` wires the real resolution pipeline.

This is the anti-stub proof gate. Unlike ``test_library_first_flow`` (which
injects ``resolver=lambda t: [...]`` and never drives the real CLI), this test
drives the *actual* ``handle_add`` and ``run_resolve`` command entrypoints with
a fake-but-realistic platform client. The resolver logic runs for real; only the
network boundary (the platform client) is faked with realistic ``TrackResult``
data.

It asserts the three failures Alice found on real data:
  1. the ``resolution_queue`` row transitions pending -> resolved (never stuck);
  2. the track's ``isrc``/``duration_seconds``/``album`` are hydrated;
  3. top-N candidates are persisted to ``track_candidates``.

On current HEAD (legacy ``resolve`` path) all three fail: the queue stays
pending, metadata stays NULL, and no candidates are written.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from tuneshift.commands.add_cmd import handle_add
from tuneshift.commands.resolve import run_resolve
from tuneshift.db import Database
from tuneshift.models import TrackResult


class _FakeTidalClient:
    """A fake platform client returning realistic candidate versions.

    Exercises the real multi-strategy resolver: ``search_track`` returns two
    versions of the track (a stereo master and a Dolby Atmos version), each
    hydrated with the metadata the version-selection engine and hydration step
    consume. All other strategy hooks return empty so the fake stays minimal
    without short-circuiting the real gather logic.
    """

    platform_name = "tidal"

    def __init__(self, results: list[TrackResult]) -> None:
        self._results = results

    def search_track(self, query: str, limit: int = 10) -> list[TrackResult]:
        del query, limit
        return list(self._results)

    def search_isrc(self, isrc: str):
        del isrc
        return None

    def search_album(self, query: str, limit: int = 5):
        del query, limit
        return []

    def get_album_tracks(self, album_id: str):
        del album_id
        return []

    def search_artist(self, query: str, limit: int = 3):
        del query, limit
        return []

    def get_artist_albums(self, artist_id: str, limit: int = 20):
        del artist_id, limit
        return []


def _candidates() -> list[TrackResult]:
    return [
        TrackResult(
            platform_id="tidal-stereo-1",
            title="Blinding Lights",
            artist="The Weeknd",
            album="After Hours",
            duration_seconds=200,
            isrc="USUG11904206",
            available=True,
            audio_modes=["STEREO"],
        ),
        TrackResult(
            platform_id="tidal-atmos-2",
            title="Blinding Lights",
            artist="The Weeknd",
            album="After Hours",
            duration_seconds=200,
            isrc="USUG11904206",
            available=True,
            audio_modes=["DOLBY_ATMOS"],
        ),
    ]


def _resolve_args() -> Namespace:
    return Namespace(
        playlist="EndToEnd",
        platform="tidal",
        track=None,
        all=False,
        upgrade=False,
        force=False,
        status=False,
        verbose=False,
    )


def test_add_then_resolve_hydrates_queue_metadata_and_candidates(tmp_path: Path) -> None:
    db = Database(tmp_path / "e2e.db")

    add_args = Namespace(
        playlist="EndToEnd",
        title="Blinding Lights",
        artist="The Weeknd",
        album=None,
        replace=None,
    )
    assert handle_add(add_args, db) == 0

    playlist = db.find_playlist_by_name("EndToEnd")
    assert playlist is not None
    tracks = db.get_playlist_tracks(playlist.id)
    assert len(tracks) == 1
    track_id = tracks[0].id

    # (1) add enqueues for resolution, pending.
    assert db.get_resolution_queue_state(track_id) == "pending"

    fake = _FakeTidalClient(_candidates())
    with (
        patch("tuneshift.commands.resolve._load_client", return_value=fake),
        # The enricher now fires on resolve (FL2). Patch its network seams so
        # this identity-hydration test stays hermetic; the enricher wiring is
        # exercised for real in test_resolve_enriches.py.
        patch("tuneshift.library.enrichment._enrich_artist_via_llm"),
        patch("tuneshift.enrichment.pipeline.classify_track_grounded", return_value=None),
        patch("tuneshift.library.enrichment._ensure_energy_valence"),
    ):
        run_resolve(_resolve_args(), db)

    # (1) queue transitioned out of pending.
    assert db.get_resolution_queue_state(track_id) == "resolved"

    # (2) identity metadata hydrated onto the track (was NULL on HEAD).
    hydrated = db.get_track(track_id)
    assert hydrated.isrc == "USUG11904206"
    assert hydrated.duration_seconds == 200
    assert hydrated.album == "After Hours"

    # (3) top-N candidates persisted (both versions).
    candidates = db.get_track_candidates(track_id, platform="tidal")
    ids = {c["platform_track_id"] for c in candidates}
    assert {"tidal-stereo-1", "tidal-atmos-2"} <= ids


def test_resolve_quarantines_when_no_candidate(tmp_path: Path) -> None:
    db = Database(tmp_path / "e2e2.db")
    add_args = Namespace(
        playlist="EndToEnd",
        title="Nonexistent Song",
        artist="Nobody",
        album=None,
        replace=None,
    )
    assert handle_add(add_args, db) == 0
    playlist = db.find_playlist_by_name("EndToEnd")
    track_id = db.get_playlist_tracks(playlist.id)[0].id

    fake = _FakeTidalClient([])  # platform finds nothing
    with (
        patch("tuneshift.commands.resolve._load_client", return_value=fake),
        patch("tuneshift.library.enrichment._enrich_artist_via_llm"),
        patch("tuneshift.enrichment.pipeline.classify_track_grounded", return_value=None),
        patch("tuneshift.library.enrichment._ensure_energy_valence"),
    ):
        run_resolve(_resolve_args(), db)

    assert db.get_resolution_queue_state(track_id) == "quarantined"
    assert db.get_track(track_id).quarantine_state is not None


class _UnauthenticatedClient(_FakeTidalClient):
    """A client that fails its session load (mirrors an expired Tidal token)."""

    def load_session(self) -> bool:
        return False


def test_resolve_fails_fast_when_not_logged_in(tmp_path: Path, capsys) -> None:
    """An unauthenticated client must error out, not silently quarantine.

    Regression for the real-data bug where `resolve` built a TidalClient but
    never loaded its session, so every track quarantined as "no candidate"
    despite a valid stored login.
    """
    db = Database(tmp_path / "e2e3.db")
    add_args = Namespace(
        playlist="EndToEnd", title="Blinding Lights", artist="The Weeknd",
        album=None, replace=None,
    )
    assert handle_add(add_args, db) == 0
    playlist = db.find_playlist_by_name("EndToEnd")
    track_id = db.get_playlist_tracks(playlist.id)[0].id

    fake = _UnauthenticatedClient(_candidates())
    with patch("tuneshift.commands.resolve._load_client", return_value=fake):
        try:
            run_resolve(_resolve_args(), db)
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("expected SystemExit when not logged in")

    assert "not logged in" in capsys.readouterr().err.lower()
    # Never touched the queue: not a silent quarantine.
    assert db.get_resolution_queue_state(track_id) == "pending"
