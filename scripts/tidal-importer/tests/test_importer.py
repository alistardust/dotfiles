"""Tests for import/sync module."""
import json
from pathlib import Path

import pytest

from tidal_importer.importer import (
    build_sync_plan,
    import_playlist,
    ImportResult,
    SyncPlan,
)
from tidal_importer.reconcile import ReconciledTrack, SourceTrack


def make_reconciled_track(
    row_number: int,
    status: str = "matched",
    tidal_id: int | None = None,
    title: str = "Song",
    artist: str = "Artist",
    album: str = "Album",
) -> ReconciledTrack:
    """Helper to create a ReconciledTrack for testing."""
    return ReconciledTrack(
        source=SourceTrack(
            title=title,
            artist=artist,
            album=album,
            row_number=row_number,
        ),
        status=status,
        confidence="high" if status == "matched" else status,
        tidal_id=tidal_id,
        tidal_title=title if tidal_id else None,
        tidal_artist=artist if tidal_id else None,
        tidal_album=album if tidal_id else None,
        score=100 if status == "matched" else 50,
        alternatives=[],
    )


def make_reconciled_json(tmp_path: Path, tracks: list[ReconciledTrack]) -> Path:
    """Helper to create a reconciled JSON file for testing."""
    status_counts = {
        "matched": 0,
        "ambiguous": 0,
        "not_found": 0,
        "already_in_playlist": 0,
    }
    for track in tracks:
        if track.status in status_counts:
            status_counts[track.status] += 1

    data = {
        "generated_at": "2026-05-27T12:00:00+00:00",
        "total": len(tracks),
        "matched": status_counts["matched"],
        "ambiguous": status_counts["ambiguous"],
        "not_found": status_counts["not_found"],
        "already_in_playlist": status_counts["already_in_playlist"],
        "tracks": [
            {
                "source": {
                    "title": t.source.title,
                    "artist": t.source.artist,
                    "album": t.source.album,
                    "row_number": t.source.row_number,
                },
                "status": t.status,
                "confidence": t.confidence,
                "tidal_id": t.tidal_id,
                "tidal_title": t.tidal_title,
                "tidal_artist": t.tidal_artist,
                "tidal_album": t.tidal_album,
                "score": t.score,
                "alternatives": t.alternatives,
            }
            for t in tracks
        ],
    }
    json_path = tmp_path / "test.reconciled.json"
    json_path.write_text(json.dumps(data))
    return json_path


class TestBuildSyncPlan:
    """Test suite for build_sync_plan function."""

    def test_new_playlist_all_to_add(self):
        """New playlist: all matched tracks should be added."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "matched", 200, "Song B"),
            make_reconciled_track(3, "matched", 300, "Song C"),
        ]
        plan = build_sync_plan(reconciled, current_track_ids=[])

        assert plan.to_add == [100, 200, 300]
        assert plan.to_remove == []
        assert plan.final_order == [100, 200, 300]
        assert plan.already_present == 0

    def test_existing_playlist_partial_overlap(self):
        """Existing playlist: only add missing tracks."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "matched", 200, "Song B"),
            make_reconciled_track(3, "matched", 300, "Song C"),
        ]
        plan = build_sync_plan(reconciled, current_track_ids=[100, 300])

        assert plan.to_add == [200]
        assert plan.to_remove == []
        assert plan.final_order == [100, 200, 300]
        assert plan.already_present == 2

    def test_existing_with_extra_tracks_removed(self):
        """Extra tracks in playlist should be removed when remove_extra=True."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "matched", 200, "Song B"),
        ]
        plan = build_sync_plan(
            reconciled,
            current_track_ids=[100, 200, 999],
            remove_extra=True,
        )

        assert plan.to_add == []
        assert plan.to_remove == [999]
        assert plan.final_order == [100, 200]
        assert plan.already_present == 2

    def test_no_remove_keeps_extras(self):
        """Extra tracks in playlist should be kept when remove_extra=False."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
        ]
        plan = build_sync_plan(
            reconciled,
            current_track_ids=[100, 999],
            remove_extra=False,
        )

        assert plan.to_add == []
        assert plan.to_remove == []
        assert plan.final_order == [100]
        assert plan.already_present == 1

    def test_order_matches_csv_sequence(self):
        """Final order should match CSV sequence, not playlist order."""
        reconciled = [
            make_reconciled_track(1, "matched", 300, "Song C"),
            make_reconciled_track(2, "matched", 100, "Song A"),
            make_reconciled_track(3, "matched", 200, "Song B"),
        ]
        plan = build_sync_plan(
            reconciled,
            current_track_ids=[100, 200, 300],
        )

        assert plan.final_order == [300, 100, 200]
        assert plan.to_add == []
        assert plan.to_remove == []

    def test_empty_reconciled(self):
        """Empty reconciled list should result in empty plan."""
        plan = build_sync_plan([], current_track_ids=[100, 200])

        assert plan.to_add == []
        assert plan.to_remove == [100, 200]
        assert plan.final_order == []
        assert plan.already_present == 0

    def test_skips_ambiguous_and_not_found(self):
        """Only matched and already_in_playlist tracks should be in plan."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "ambiguous", 200, "Song B"),
            make_reconciled_track(3, "not_found", None, "Song C"),
            make_reconciled_track(4, "already_in_playlist", 300, "Song D"),
        ]
        plan = build_sync_plan(reconciled, current_track_ids=[])

        assert plan.to_add == [100, 300]
        assert plan.final_order == [100, 300]

    def test_already_in_playlist_status_included(self):
        """Tracks with 'already_in_playlist' status should be in final order."""
        reconciled = [
            make_reconciled_track(1, "already_in_playlist", 100, "Song A"),
            make_reconciled_track(2, "matched", 200, "Song B"),
        ]
        plan = build_sync_plan(reconciled, current_track_ids=[100])

        assert plan.to_add == [200]
        assert plan.final_order == [100, 200]
        assert plan.already_present == 1


class TestImportPlaylist:
    """Test suite for import_playlist function."""

    def test_creates_new_playlist(self, fake_client, tmp_path):
        """Should create a new playlist when no existing_playlist_id."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "matched", 200, "Song B"),
        ]
        json_path = make_reconciled_json(tmp_path, reconciled)

        result = import_playlist(
            json_path,
            "Test Playlist",
            fake_client,
        )

        assert result.playlist_name == "Test Playlist"
        assert result.tracks_added == 2
        assert result.tracks_removed == 0
        assert result.total_in_playlist == 2

        # Verify playlist was created
        playlist_info = fake_client.get_playlist(result.playlist_id)
        assert playlist_info is not None
        assert playlist_info.name == "Test Playlist"

    def test_adds_only_matched_tracks(self, fake_client, tmp_path):
        """Should only add tracks with status matched or already_in_playlist."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "ambiguous", 200, "Song B"),
            make_reconciled_track(3, "not_found", None, "Song C"),
            make_reconciled_track(4, "matched", 300, "Song D"),
        ]
        json_path = make_reconciled_json(tmp_path, reconciled)

        result = import_playlist(json_path, "Test", fake_client)

        assert result.tracks_added == 2
        assert result.tracks_skipped == 2
        assert result.total_in_playlist == 2

        # Verify only matched tracks in playlist
        tracks = fake_client.get_playlist_tracks(result.playlist_id)
        track_ids = [t.tidal_id for t in tracks]
        assert track_ids == [100, 300]

    def test_syncs_existing_playlist(self, fake_client, tmp_path):
        """Should sync to existing playlist, adding missing tracks."""
        # Create existing playlist with one track
        info = fake_client.create_playlist("Existing")
        fake_client.add_tracks(info.playlist_id, [100])

        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "matched", 200, "Song B"),
        ]
        json_path = make_reconciled_json(tmp_path, reconciled)

        result = import_playlist(
            json_path,
            "Existing",
            fake_client,
            existing_playlist_id=info.playlist_id,
        )

        assert result.playlist_id == info.playlist_id
        assert result.tracks_added == 1
        assert result.tracks_removed == 0
        assert result.total_in_playlist == 2

    def test_removes_extra_tracks(self, fake_client, tmp_path):
        """Should remove tracks not in CSV when remove_extra=True."""
        # Create existing playlist with extra track
        info = fake_client.create_playlist("Test")
        fake_client.add_tracks(info.playlist_id, [100, 999])

        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
        ]
        json_path = make_reconciled_json(tmp_path, reconciled)

        result = import_playlist(
            json_path,
            "Test",
            fake_client,
            existing_playlist_id=info.playlist_id,
            remove_extra=True,
        )

        assert result.tracks_removed == 1
        assert result.total_in_playlist == 1

        tracks = fake_client.get_playlist_tracks(info.playlist_id)
        track_ids = [t.tidal_id for t in tracks]
        assert 999 not in track_ids

    def test_reorders_to_csv_sequence(self, fake_client, tmp_path):
        """Should reorder playlist to match CSV sequence."""
        # Create playlist with tracks in wrong order
        info = fake_client.create_playlist("Test")
        fake_client.add_tracks(info.playlist_id, [300, 100, 200])

        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "matched", 200, "Song B"),
            make_reconciled_track(3, "matched", 300, "Song C"),
        ]
        json_path = make_reconciled_json(tmp_path, reconciled)

        result = import_playlist(
            json_path,
            "Test",
            fake_client,
            existing_playlist_id=info.playlist_id,
        )

        assert result.tracks_reordered is True

        # Verify order matches CSV
        tracks = fake_client.get_playlist_tracks(info.playlist_id)
        track_ids = [t.tidal_id for t in tracks]
        assert track_ids == [100, 200, 300]

    def test_dry_run_no_modifications(self, fake_client, tmp_path):
        """Dry run should not create playlist or modify anything."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
        ]
        json_path = make_reconciled_json(tmp_path, reconciled)

        result = import_playlist(
            json_path,
            "Test",
            fake_client,
            dry_run=True,
        )

        # Should return correct counts
        assert result.tracks_added == 1
        assert result.total_in_playlist == 1

        # But playlist should not exist
        assert fake_client.get_playlist(result.playlist_id) is None

    def test_skips_ambiguous_and_not_found(self, fake_client, tmp_path):
        """Should skip ambiguous and not_found tracks."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "ambiguous", 200, "Song B"),
            make_reconciled_track(3, "not_found", None, "Song C"),
        ]
        json_path = make_reconciled_json(tmp_path, reconciled)

        result = import_playlist(json_path, "Test", fake_client)

        assert result.tracks_added == 1
        assert result.tracks_skipped == 2

    def test_progress_callback(self, fake_client, tmp_path):
        """Should call progress callback with correct phases."""
        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
            make_reconciled_track(2, "matched", 200, "Song B"),
        ]
        json_path = make_reconciled_json(tmp_path, reconciled)

        phases = []

        def callback(phase: str, current: int, total: int):
            phases.append(phase)

        import_playlist(
            json_path,
            "Test",
            fake_client,
            progress_callback=callback,
        )

        assert "loading" in phases

    def test_keeps_extras_when_remove_extra_false(self, fake_client, tmp_path):
        """Should keep extra tracks when remove_extra=False."""
        info = fake_client.create_playlist("Test")
        fake_client.add_tracks(info.playlist_id, [100, 999])

        reconciled = [
            make_reconciled_track(1, "matched", 100, "Song A"),
        ]
        json_path = make_reconciled_json(tmp_path, reconciled)

        result = import_playlist(
            json_path,
            "Test",
            fake_client,
            existing_playlist_id=info.playlist_id,
            remove_extra=False,
        )

        assert result.tracks_removed == 0

        # Track 999 should still be there (but order may change)
        tracks = fake_client.get_playlist_tracks(info.playlist_id)
        track_ids = [t.tidal_id for t in tracks]
        assert 999 in track_ids
        assert 100 in track_ids
