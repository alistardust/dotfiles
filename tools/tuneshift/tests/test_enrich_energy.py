"""Contract tests for energy/valence population on the `enrich` path (BUG-17).

BUG-17: `tuneshift enrich` could never write `tracks.energy`. The only route to
:func:`ensure_energy_valence` was ``enrich_track`` -> ``make_enricher`` ->
``resolve``, so the one command named after enrichment was the one command that
could not perform it. Users were told to run ``resolve --force`` to fill energy,
which is an unrelated and far heavier operation.

These tests pin the fix: the enrich path populates energy/valence itself, using
the Spotify-then-LLM chain, and never talks to Tidal to do it.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tuneshift.commands.enrich_cmd import handle_enrich
from tuneshift.db import Database
from tuneshift.models import Track

ESTIMATE = "tuneshift.enrichment.audio_features.estimate_energy_valence"
SPOTIFY = "tuneshift.enrichment.audio_features.spotify_audio_features_via_isrc"
CLASSIFY = "tuneshift.commands.enrich_cmd._run_classification"


@pytest.fixture(autouse=True)
def no_llm_classification():
    """Isolate the energy pass from LLM narrative classification.

    handle_enrich runs classification whenever no --platform is given, and a
    reachable local Ollama makes that a real network call. These tests are
    about energy/valence only.
    """
    with patch(CLASSIFY, return_value=0):
        yield


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "energy.db")


def _seed(db: Database, titles=("Alpha",)) -> tuple[int, list[int]]:
    playlist_id = db.create_playlist("Mix")
    track_ids = []
    for position, title in enumerate(titles, start=1):
        track_id = db.add_track(Track(title=title, artist="Artist"))
        db.add_track_to_playlist(playlist_id, track_id, position)
        track_ids.append(track_id)
    return playlist_id, track_ids


def _args(**overrides) -> SimpleNamespace:
    base = {"playlist": "Mix", "platform": None, "classify": False}
    base.update(overrides)
    return SimpleNamespace(**base)


class TestEnrichWritesEnergy:
    def test_enrich_populates_energy_and_valence(self, db: Database) -> None:
        """The headline bug: enrich now fills a null energy/valence pair."""
        playlist_id, (track_id,) = _seed(db)
        assert db.get_track(track_id).energy is None

        with patch(SPOTIFY, return_value=None), patch(
            ESTIMATE, return_value=(0.7, 0.4)
        ):
            assert handle_enrich(_args(), db) == 0

        track = db.get_track(track_id)
        assert track.energy == 0.7
        assert track.valence == 0.4

    def test_energy_is_written_without_any_platform_client(self, db: Database) -> None:
        """The energy pass must not depend on, or contact, Tidal.

        Ali's standing constraint is that nothing in this change may touch her
        Tidal account. The fallback chain is Spotify-then-LLM, so a run with no
        --platform must still produce energy while loading no client at all.
        """
        _playlist_id, (track_id,) = _seed(db)

        with patch("tuneshift.commands.ingest_cmd._load_client") as load_client, patch(
            SPOTIFY, return_value=None
        ), patch(ESTIMATE, return_value=(0.5, 0.5)):
            assert handle_enrich(_args(), db) == 0
            load_client.assert_not_called()

        assert db.get_track(track_id).energy == 0.5

    def test_existing_energy_is_not_overwritten(self, db: Database) -> None:
        _playlist_id, (track_id,) = _seed(db)
        db.set_track_fields(track_id, {"energy": 0.9, "valence": 0.9}, source="enrichment")

        with patch(SPOTIFY, return_value=None), patch(ESTIMATE) as estimate:
            assert handle_enrich(_args(), db) == 0
            estimate.assert_not_called()

        assert db.get_track(track_id).energy == 0.9

    def test_refresh_re_estimates(self, db: Database) -> None:
        _playlist_id, (track_id,) = _seed(db)
        db.set_track_fields(track_id, {"energy": 0.9, "valence": 0.9}, source="enrichment")

        with patch(SPOTIFY, return_value=None), patch(
            ESTIMATE, return_value=(0.2, 0.3)
        ):
            assert handle_enrich(_args(refresh=True), db) == 0

        assert db.get_track(track_id).energy == 0.2

    def test_manual_values_survive_refresh(self, db: Database) -> None:
        """A hand-edited value is never clobbered, even by --refresh."""
        _playlist_id, (track_id,) = _seed(db)
        db.set_track_fields(track_id, {"energy": 0.85}, source="manual")

        with patch(SPOTIFY, return_value=None), patch(
            ESTIMATE, return_value=(0.1, 0.1)
        ):
            assert handle_enrich(_args(refresh=True), db) == 0

        track = db.get_track(track_id)
        assert track.energy == 0.85  # manual, untouched
        assert track.valence == 0.1  # was null, filled

    def test_no_energy_flag_skips_the_pass(self, db: Database) -> None:
        _playlist_id, (track_id,) = _seed(db)

        with patch(SPOTIFY, return_value=None), patch(ESTIMATE) as estimate:
            assert handle_enrich(_args(no_energy=True), db) == 0
            estimate.assert_not_called()

        assert db.get_track(track_id).energy is None

    def test_spotify_tier_wins_when_it_answers(self, db: Database) -> None:
        _playlist_id, (track_id,) = _seed(db)

        with patch(SPOTIFY, return_value=(0.6, 0.2)), patch(ESTIMATE) as estimate:
            assert handle_enrich(_args(), db) == 0
            estimate.assert_not_called()

        assert db.get_track(track_id).energy == 0.6


class TestEnergyPassBatching:
    def test_classifier_is_built_once_for_the_whole_playlist(
        self, db: Database
    ) -> None:
        """One backend detection per run, not one per track.

        make_enricher already established this pattern for resolve; the enrich
        path must not regress it into a per-track construction.
        """
        _seed(db, titles=("Alpha", "Beta", "Gamma"))
        built = []

        real = MagicMock()
        real.available = False

        def _factory(*args, **kwargs):
            built.append(1)
            return real

        with patch("tuneshift.sequencer.classifier.TrackClassifier", _factory), patch(
            SPOTIFY, return_value=None
        ), patch(ESTIMATE, return_value=(0.5, 0.5)):
            assert handle_enrich(_args(), db) == 0

        assert len(built) == 1


class TestEnrichAllRunsEnergy:
    def test_all_path_also_populates_energy(self, db: Database) -> None:
        """--all is the whole-library sweep; it must not skip energy either."""
        _playlist_id, (track_id,) = _seed(db)

        with patch(
            "tuneshift.enrichment.platform_metadata.enrich_all_playlists",
            return_value=0,
        ), patch(SPOTIFY, return_value=None), patch(ESTIMATE, return_value=(0.3, 0.8)):
            assert handle_enrich(_args(playlist=None, all=True), db) == 0

        assert db.get_track(track_id).energy == 0.3
