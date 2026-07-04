"""Integration: the reconcile engine threads its real decision into MatchAudit.

These prove the AC-CLI3 (match explanation) and AC-CLI5 (failed-match rejection
reasons) data is sourced from the live two-phase selection engine — the criteria
that fired (hard vs soft), the winner's weighted signal breakdown, the precedence
tie-break, and the Phase-1 eliminations with per-candidate reasons — not synthesized
after the fact. A regression that stopped threading ``SelectionResult`` into the
audit would leave these fields empty and fail here.
"""
from pathlib import Path
from unittest.mock import MagicMock

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.reconcile import reconcile_track


def _client(results: list[TrackResult]) -> MagicMock:
    client = MagicMock()
    client.platform_name = "spotify"
    client.search_isrc.return_value = None
    client.search_track.return_value = results
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    return client


def _setup(tmp_db: Path) -> tuple[Database, int, int]:
    db = Database(tmp_db)
    track_id = db.add_track(Track(title="Flowerz", artist="Armand", album="Flowerz"))
    playlist_id = db.create_playlist("Atmos Playlist")
    db.add_track_to_playlist(playlist_id, track_id, 0)
    return db, track_id, playlist_id


def _stereo_and_atmos() -> list[TrackResult]:
    return [
        TrackResult(platform_id="stereo", title="Flowerz", artist="Armand",
                    album="Flowerz", audio_modes=["STEREO"]),
        TrackResult(platform_id="atmos", title="Flowerz", artist="Armand",
                    album="Flowerz", audio_modes=["DOLBY_ATMOS"]),
    ]


class TestMatchExplainEnrichment:
    """AC-CLI3: the winning decision is fully explainable from the stored audit."""

    def test_winner_has_weighted_signal_breakdown_even_without_prefs(
        self, tmp_db: Path
    ) -> None:
        # A plain confident match carries the winner's per-signal weighted
        # breakdown regardless of preferences (byte-parity path).
        db, track_id, playlist_id = _setup(tmp_db)
        result = reconcile_track(
            db, track_id, _client(_stereo_and_atmos()), playlist_id=playlist_id
        )
        audit = result.audit
        assert audit is not None
        assert audit.signal_breakdown, "winner should carry a weighted signal breakdown"
        # Default prefs => no active user criteria (byte-parity: nothing perturbs).
        assert audit.criteria == []
        assert audit.tie_break is None

    def test_soft_preference_tie_break_is_recorded(self, tmp_db: Path) -> None:
        # "prefer atmos" resolves the stereo/atmos tie by precedence: the audit
        # names the criterion that broke it and records it as a soft criterion
        # that fired.
        db, track_id, playlist_id = _setup(tmp_db)
        db.set_preferences(playlist_id, {"prefer": ["atmos"]})
        result = reconcile_track(
            db, track_id, _client(_stereo_and_atmos()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos"
        audit = result.audit
        assert audit is not None
        assert audit.tie_break is not None
        soft_fired = [c for c in audit.criteria if c.kind == "soft" and c.fired]
        assert soft_fired, "the deciding soft criterion should be recorded as fired"
        assert any(c.criterion == audit.tie_break for c in soft_fired)


class TestFailedMatchRejectionReasons:
    """AC-CLI5: rejected candidates carry a per-candidate rejection reason."""

    def test_hard_filter_elimination_surfaces_in_rejected(self, tmp_db: Path) -> None:
        # A per-playlist "require atmos" eliminates the stereo release in Phase 1.
        # That elimination never reaches the scored list, so the audit must append
        # it to rejected with a machine-stable hard_filter reason (AC-CLI5).
        db, track_id, playlist_id = _setup(tmp_db)
        db.set_preferences(
            playlist_id,
            {"criteria": [{"criterion": "spatial", "strength": "require", "target": "atmos"}]},
        )
        result = reconcile_track(
            db, track_id, _client(_stereo_and_atmos()), playlist_id=playlist_id
        )
        assert result.platform_track_id == "atmos"
        audit = result.audit
        assert audit is not None
        stereo_rej = [r for r in audit.rejected if r.platform_id == "stereo"]
        assert stereo_rej, "the hard-filtered stereo release must be listed as rejected"
        assert stereo_rej[0].rejection == "hard_filter"
        assert stereo_rej[0].rejection_detail == "spatial=dolbyatmos"
        # The hard criterion is recorded as having fired.
        hard_fired = [c for c in audit.criteria if c.kind == "hard" and c.fired]
        assert any(c.criterion == "spatial" for c in hard_fired)

    def test_scored_losers_are_marked_lost(self, tmp_db: Path) -> None:
        # Two available survivors: the runner-up is marked as an out-ranked loss,
        # distinct from a hard-filter or unavailable rejection.
        db, track_id, playlist_id = _setup(tmp_db)
        result = reconcile_track(
            db, track_id, _client(_stereo_and_atmos()), playlist_id=playlist_id
        )
        audit = result.audit
        assert audit is not None
        assert audit.rejected, "the runner-up should be listed"
        assert all(r.rejection in {"lost", "below_threshold"} for r in audit.rejected)
