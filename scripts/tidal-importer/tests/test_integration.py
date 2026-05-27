"""Integration tests: full CSV -> reconcile -> import pipeline."""
import json
from pathlib import Path

from tidal_importer.client import TrackResult
from tidal_importer.reconcile import parse_csv, reconcile_playlist, save_reconciled, load_reconciled
from tidal_importer.importer import import_playlist, build_sync_plan
from tests.conftest import FakeTidalClient


class TestFullPipeline:
    def test_csv_to_new_playlist(self, tmp_path):
        """Full flow: CSV -> reconcile -> save -> load -> import to new playlist."""
        # Create test CSV
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("title,artist,album\nMr. Tambourine Man,The Byrds,Mr. Tambourine Man\nCalifornia Dreamin',The Mamas & the Papas,If You Can Believe Your Eyes and Ears\n")
        
        # Set up fake client with search results
        client = FakeTidalClient(search_results={
            '"Mr. Tambourine Man" The Byrds': [
                TrackResult(tidal_id=101, title="Mr. Tambourine Man", artist="The Byrds", album="Mr. Tambourine Man (Remastered)"),
            ],
            '"California Dreamin\'" The Mamas & the Papas': [
                TrackResult(tidal_id=102, title="California Dreamin'", artist="The Mamas & The Papas", album="If You Can Believe Your Eyes and Ears"),
            ],
        })
        
        # Reconcile
        reconciled = reconcile_playlist(csv_path, client)
        json_path = tmp_path / "test.reconciled.json"
        save_reconciled(reconciled, json_path)
        
        # Import
        result = import_playlist(
            reconciled_path=json_path,
            playlist_name="LC Vibes",
            client=client,
        )
        
        assert result.playlist_id is not None
        assert result.tracks_added == 2
        assert result.tracks_removed == 0
        assert result.total_in_playlist == 2

    def test_sync_existing_playlist_adds_missing(self, tmp_path):
        """Sync adds missing tracks to existing playlist."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("title,artist,album\nSong A,Artist A,Album A\nSong B,Artist B,Album B\nSong C,Artist C,Album C\n")
        
        client = FakeTidalClient(search_results={
            '"Song A" Artist A': [TrackResult(tidal_id=1, title="Song A", artist="Artist A", album="Album A")],
            '"Song B" Artist B': [TrackResult(tidal_id=2, title="Song B", artist="Artist B", album="Album B")],
            '"Song C" Artist C': [TrackResult(tidal_id=3, title="Song C", artist="Artist C", album="Album C")],
        })
        
        # Create existing playlist with only track 1
        info = client.create_playlist("Test Playlist")
        client.add_tracks(info.playlist_id, [1])
        
        # Reconcile with existing playlist
        reconciled = reconcile_playlist(csv_path, client, existing_playlist_id=info.playlist_id)
        json_path = tmp_path / "test.reconciled.json"
        save_reconciled(reconciled, json_path)
        
        # Import/sync
        result = import_playlist(
            reconciled_path=json_path,
            playlist_name="Test Playlist",
            client=client,
            existing_playlist_id=info.playlist_id,
        )
        
        assert result.tracks_added == 2  # Songs B and C added
        assert result.total_in_playlist == 3

    def test_sync_removes_extra_and_reorders(self, tmp_path):
        """Sync removes tracks not in CSV and reorders to match CSV."""
        # CSV has tracks in order: A, B, C
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("title,artist,album\nSong A,Artist A,Album A\nSong B,Artist B,Album B\nSong C,Artist C,Album C\n")
        
        client = FakeTidalClient(search_results={
            '"Song A" Artist A': [TrackResult(tidal_id=1, title="Song A", artist="Artist A", album="Album A")],
            '"Song B" Artist B': [TrackResult(tidal_id=2, title="Song B", artist="Artist B", album="Album B")],
            '"Song C" Artist C': [TrackResult(tidal_id=3, title="Song C", artist="Artist C", album="Album C")],
        })
        
        # Existing playlist has: D, C, B, A (extra track D, wrong order)
        info = client.create_playlist("Test")
        client.add_tracks(info.playlist_id, [99, 3, 2, 1])  # 99 = extra track
        
        # Reconcile
        reconciled = reconcile_playlist(csv_path, client, existing_playlist_id=info.playlist_id)
        json_path = tmp_path / "test.reconciled.json"
        save_reconciled(reconciled, json_path)
        
        # Import/sync
        result = import_playlist(
            reconciled_path=json_path,
            playlist_name="Test",
            client=client,
            existing_playlist_id=info.playlist_id,
        )
        
        assert result.tracks_removed == 1  # Track 99 removed
        assert result.tracks_reordered is True
        # Verify final order
        final_tracks = client.get_playlist_tracks(info.playlist_id)
        final_ids = [t.tidal_id for t in final_tracks]
        assert final_ids == [1, 2, 3]  # CSV order

    def test_dry_run_no_changes(self, tmp_path):
        """Dry run reports plan without modifying playlist."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("title,artist,album\nSong A,Artist A,Album A\n")
        
        client = FakeTidalClient(search_results={
            '"Song A" Artist A': [TrackResult(tidal_id=1, title="Song A", artist="Artist A", album="Album A")],
        })
        
        reconciled = reconcile_playlist(csv_path, client)
        json_path = tmp_path / "test.reconciled.json"
        save_reconciled(reconciled, json_path)
        
        result = import_playlist(
            reconciled_path=json_path,
            playlist_name="Test",
            client=client,
            dry_run=True,
        )
        
        assert result.tracks_added == 1
        # No playlist was actually created
        assert client.get_playlist(result.playlist_id) is None

    def test_ambiguous_tracks_skipped(self, tmp_path):
        """Ambiguous and not_found tracks are not imported."""
        csv_path = tmp_path / "test.csv"
        csv_path.write_text("title,artist,album\nSong A,Artist A,Album A\nUnknown Song,Unknown Artist,Unknown Album\n")
        
        client = FakeTidalClient(search_results={
            '"Song A" Artist A': [TrackResult(tidal_id=1, title="Song A", artist="Artist A", album="Album A")],
            '"Unknown Song" Unknown Artist': [],  # No results
        })
        
        reconciled = reconcile_playlist(csv_path, client)
        json_path = tmp_path / "test.reconciled.json"
        save_reconciled(reconciled, json_path)
        
        result = import_playlist(
            reconciled_path=json_path,
            playlist_name="Test",
            client=client,
        )
        
        assert result.tracks_added == 1
        assert result.tracks_skipped >= 1
