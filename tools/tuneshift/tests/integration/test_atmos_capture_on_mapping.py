"""FL2 AC4/AC10/AC11: Atmos/catalog auto-capture on every Tidal mapping path.

The gap (Alice's live smoke test): an "Atmos" playlist matched all-stereo IDs,
and even when an Atmos ID WAS mapped the ``atmos-available`` tag was only ever
derived behind the manual ``enrich --catalog`` flag. These tests drive the real
mapping-creation entrypoints -- the shared hook, ``map``, ``doctor --apply``,
``ingest`` and a bare ``enrich --platform tidal`` (no ``--catalog``) -- and
assert the tag is derived automatically. The Tidal session boundary is faked
(returns a DOLBY_ATMOS track); the WIRING runs for real.
"""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from tuneshift.db import Database
from tuneshift.library.enrichment import capture_tidal_catalog
from tuneshift.models import PlatformMapping, Track, TrackResult


class _FakeAtmosTrack:
    name = "Levitating"
    duration = 203
    audio_modes = ["DOLBY_ATMOS"]
    audio_quality = "HI_RES_LOSSLESS"
    explicit = False
    album = None
    artist = None
    popularity = None
    isrc = "GBAHT2000455"


class _FakeSession:
    def track(self, _id):
        return _FakeAtmosTrack()

    def check_login(self):
        return True


class _FakeTidalClient:
    platform_name = "tidal"

    def __init__(self):
        self._session = _FakeSession()

    def load_session(self):
        return True

    def get_track(self, platform_id):
        return TrackResult(
            platform_id=platform_id, title="Levitating", artist="Dua Lipa",
            album="Future Nostalgia", duration_seconds=203,
            audio_modes=["DOLBY_ATMOS"], audio_quality="HI_RES_LOSSLESS",
        )

    # ingest surface
    def get_playlist(self, _pid):
        return Namespace(name="Atmos Mix")

    def get_playlist_tracks(self, _pid):
        return [Namespace(
            title="Levitating", artist="Dua Lipa", album="Future Nostalgia",
            duration_seconds=203, isrc="GBAHT2000455", platform_id="12270106",
        )]

    def get_track_metadata(self, _pid):
        return {}


@pytest.fixture(autouse=True)
def _fast_limiter(monkeypatch):
    from tuneshift.enrichment import platform_metadata
    monkeypatch.setattr(platform_metadata._tidal_limiter, "wait", lambda: None)


def _mapped(db: Database, tidal_id: str = "12270106") -> int:
    track_id = db.add_track(Track(title="Levitating", artist="Dua Lipa"))
    db.upsert_platform_mapping(PlatformMapping(
        track_id=track_id, platform="tidal", platform_track_id=tidal_id,
        platform_title="Levitating", platform_artist="Dua Lipa",
        status="matched", user_approved=True,
    ))
    return track_id


# --- AC10: shared hook -------------------------------------------------------
def test_capture_hook_derives_atmos_tag(tmp_path: Path) -> None:
    db = Database(tmp_path / "hook.db")
    track_id = _mapped(db)

    tags = capture_tidal_catalog(db, track_id, "tidal", "12270106", client=_FakeTidalClient())

    assert "atmos-available" in tags
    assert "atmos-available" in db.get_track_tags(track_id)


def test_capture_hook_noops_for_non_tidal_or_no_client(tmp_path: Path) -> None:
    db = Database(tmp_path / "hook2.db")
    track_id = _mapped(db)
    assert capture_tidal_catalog(db, track_id, "spotify", "x", client=_FakeTidalClient()) == []
    assert capture_tidal_catalog(db, track_id, "tidal", "12270106", client=None) == []
    assert db.get_track_tags(track_id) == []


# --- AC10: map command -------------------------------------------------------
def test_map_verify_captures_atmos(tmp_path: Path) -> None:
    from tuneshift.commands.map_cmd import handle_map

    db = Database(tmp_path / "map.db")
    track_id = db.add_track(Track(title="Levitating", artist="Dua Lipa"))

    args = Namespace(
        track_id=track_id, tidal="12270106", ytmusic=None, verify=True, dry_run=False,
    )
    with patch("tuneshift.commands.map_cmd._load_client", return_value=_FakeTidalClient()):
        assert handle_map(args, db) == 0

    assert db.get_platform_mapping(track_id, "tidal").platform_track_id == "12270106"
    assert "atmos-available" in db.get_track_tags(track_id)


# --- AC10: doctor --apply ----------------------------------------------------
def test_doctor_apply_derives_atmos_tag(tmp_path: Path) -> None:
    from tuneshift.doctor.applier import apply_plan
    from tuneshift.doctor.plan import DoctorPlan, PlanItem

    db = Database(tmp_path / "doctor.db")
    track_id = _mapped(db, tidal_id="OLD")
    item = PlanItem(
        id=1, track_id=track_id, playlist="P", title="Levitating", artist="Dua Lipa",
        issue="version_mismatch", current_platform_id="OLD",
        proposed_platform_id="12270106", proposed_title="Levitating",
        proposed_album="Future Nostalgia", confidence=95, resolution="auto",
    )
    plan = DoctorPlan(scope="P", items=[item])

    apply_plan(db, plan, [item], client=_FakeTidalClient(), do_sync=False)

    assert item.status == "applied"
    assert "atmos-available" in db.get_track_tags(track_id)


# --- AC10: ingest ------------------------------------------------------------
def test_ingest_captures_atmos(tmp_path: Path) -> None:
    from tuneshift import ingest

    db = Database(tmp_path / "ingest.db")
    # Skip the LLM auto-classify batch (network); we assert only catalog capture.
    with patch.object(ingest, "_auto_classify_batch"):
        ingest.ingest_from_platform(db, _FakeTidalClient(), "pl-1")

    playlist = db.find_playlist_by_name("Atmos Mix")
    track_id = db.get_playlist_tracks(playlist.id)[0].id
    assert "atmos-available" in db.get_track_tags(track_id)


# --- AC11: bare `enrich --platform tidal` (no --catalog) ---------------------
def test_enrich_platform_tidal_captures_atmos_without_catalog_flag(tmp_path: Path) -> None:
    from tuneshift.commands import enrich_cmd

    db = Database(tmp_path / "enrich.db")
    playlist_id = db.create_playlist("Atmos Mix")
    track_id = _mapped(db)
    db.add_track_to_playlist(playlist_id, track_id, 1)

    args = Namespace(
        playlist="Atmos Mix", platform="tidal", all=False, catalog=False,
        classify=False, refresh=False, max_retries=1, model=None, reclassify=False,
    )
    with patch("tuneshift.commands.ingest_cmd._load_client", return_value=_FakeTidalClient()):
        assert enrich_cmd.handle_enrich(args, db) == 0

    assert "atmos-available" in db.get_track_tags(track_id)
