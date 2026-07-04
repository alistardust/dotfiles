"""FL2 proof: `resolve` now runs the enricher (was wired to None by FL1).

FL1 wired the resolution pipeline but left the worker's ``enricher`` hook
``None`` -- so resolved tracks got identity metadata but never got classified
(no vibes/themes) and energy/valence stayed blank. This drives the real
``run_resolve`` entrypoint and asserts the enricher fires: the track gains a
grounded classification and energy/valence. The network boundaries (MusicBrainz
artist lookup and the grounded classifier) are patched so the test is hermetic
and fast; the WIRING (worker constructed with a real enricher) runs for real.
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
    platform_name = "tidal"

    def search_track(self, query: str, limit: int = 10) -> list[TrackResult]:
        del query, limit
        return [
            TrackResult(
                platform_id="tidal-1",
                title="Levitating",
                artist="Dua Lipa",
                album="Future Nostalgia",
                duration_seconds=203,
                isrc="GBAHT2000455",
                available=True,
                audio_modes=["STEREO"],
            )
        ]

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


def _resolve_args() -> Namespace:
    return Namespace(
        playlist="EnrichProof", platform="tidal", track=None, all=False,
        upgrade=False, force=False, status=False, verbose=False,
    )


def test_resolve_runs_enricher_and_classifies(tmp_path: Path) -> None:
    db = Database(tmp_path / "enrich.db")
    add_args = Namespace(
        playlist="EnrichProof", title="Levitating", artist="Dua Lipa",
        album=None, replace=None,
    )
    assert handle_add(add_args, db) == 0

    track_id = db.get_playlist_tracks(db.find_playlist_by_name("EnrichProof").id)[0].id

    # Track starts unclassified (no vibes) and with no energy/valence.
    before = db.get_track(track_id)
    assert not (before.metadata or {}).get("vibes")
    assert before.energy is None and before.valence is None

    classification = {
        "vibes": ["euphoric", "danceable"],
        "themes": ["love"],
        "narrator_stance": "celebratory",
    }

    fake = _FakeTidalClient()
    with (
        patch("tuneshift.commands.resolve._load_client", return_value=fake),
        # Patch the network seams the enricher uses (keep it hermetic).
        patch("tuneshift.enrichment.pipeline.classify_track_grounded", return_value=classification),
        patch("tuneshift.library.enrichment._enrich_artist_via_llm"),
        patch(
            "tuneshift.library.enrichment._ensure_energy_valence",
            side_effect=lambda db, tid, **kw: db.set_track_fields(
                tid, {"energy": 0.8, "valence": 0.9}, source="test"
            ),
        ),
    ):
        run_resolve(_resolve_args(), db)

    # Enricher fired: classification persisted onto the track.
    after = db.get_track(track_id)
    assert (after.metadata or {}).get("vibes") == ["euphoric", "danceable"]
    assert after.metadata.get("narrator_stance") == "celebratory"
    # Energy/valence populated via the enricher's energy/valence step.
    assert after.energy == 0.8
    assert after.valence == 0.9
    # Resolution still completed (wiring did not break the pipeline).
    assert db.get_resolution_queue_state(track_id) == "resolved"


def test_make_enricher_builds_callable() -> None:
    from tuneshift.library.enrichment import make_enricher

    enricher = make_enricher(tidal_client=None)
    assert callable(enricher)
