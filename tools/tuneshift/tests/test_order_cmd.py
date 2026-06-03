"""Tests for the order command and CLI wiring."""

from pathlib import Path

from tuneshift.cli import main
from tuneshift.db import Database
from tuneshift.models import Track


def test_order_command_reorders_playlist(tmp_db: Path, capsys) -> None:
    """The order command rewrites playlist positions using the sequencer."""
    db = Database(tmp_db)
    first_id = db.insert_track(
        Track(title="High", artist="A", energy=0.9, valence=0.8, duration_seconds=200)
    )
    second_id = db.insert_track(
        Track(title="Low", artist="B", energy=0.2, valence=0.2, duration_seconds=210)
    )
    third_id = db.insert_track(
        Track(title="Mid", artist="C", energy=0.5, valence=0.5, duration_seconds=220)
    )
    playlist_id = db.create_playlist("Test Playlist")
    db.set_playlist_tracks(playlist_id, [first_id, second_id, third_id])
    db.close()

    exit_code = main(["--db", str(tmp_db), "order", "Test Playlist", "--arc", "ascending"])

    assert exit_code == 0
    reordered_db = Database(tmp_db)
    reordered_tracks = reordered_db.get_playlist_tracks(playlist_id)
    reordered_db.close()
    assert [track.id for track in reordered_tracks] == [second_id, third_id, first_id]
    assert 'Reordered "Test Playlist" (3 tracks, arc=ascending)' in capsys.readouterr().out
