"""Reconcile strategies must degrade on operational errors, not swallow bugs.

Each strategy previously wrapped its client calls in a bare ``except Exception``
that turned genuine programming errors (AttributeError/TypeError) into silent
``not_found`` results. Operational/platform errors (connection, timeout, auth,
parsing) should degrade to the next strategy AND log a warning; programming
errors must propagate.
"""
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.reconcile import (
    _strategy_title_artist,
    reconcile_track,
)


def _track() -> Track:
    return Track(title="Heroes", artist="David Bowie", album="Heroes")


def test_strategy_degrades_on_connection_error_and_logs(caplog):
    client = MagicMock()
    client.search_track.side_effect = ConnectionError("network down")
    with caplog.at_level(logging.WARNING):
        result = _strategy_title_artist(_track(), client)
    assert result == []
    assert any("title_artist" in r.message for r in caplog.records)


def test_strategy_degrades_on_runtime_error(caplog):
    client = MagicMock()
    client.search_track.side_effect = RuntimeError("Not logged in")
    with caplog.at_level(logging.WARNING):
        assert _strategy_title_artist(_track(), client) == []
    assert caplog.records


def test_strategy_propagates_programming_error():
    client = MagicMock()
    client.search_track.side_effect = AttributeError("bug: 'NoneType' has no attr")
    with pytest.raises(AttributeError):
        _strategy_title_artist(_track(), client)


def test_reconcile_propagates_programming_error(tmp_db: Path):
    db = Database(tmp_db)
    track_id = db.add_track(_track())
    client = MagicMock()
    client.platform_name = "spotify"
    client.search_isrc.return_value = None
    client.search_album.return_value = []
    client.get_album_tracks.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    client.search_track.side_effect = TypeError("bug in candidate handling")
    with pytest.raises(TypeError):
        reconcile_track(db, track_id, client)


def test_reconcile_degrades_across_strategies(tmp_db: Path, caplog):
    """A failing text search still resolves via an album strategy."""
    db = Database(tmp_db)
    track_id = db.add_track(_track())
    client = MagicMock()
    client.platform_name = "spotify"
    client.search_isrc.return_value = None
    client.search_track.side_effect = ConnectionError("flaky search endpoint")
    # Album strategies succeed and provide the correct candidate.
    from tuneshift.models import AlbumResult
    client.search_album.return_value = [
        AlbumResult(platform_id="alb1", title="Heroes", artist="David Bowie")
    ]
    client.get_album_tracks.return_value = [
        TrackResult(platform_id="sp1", title="Heroes", artist="David Bowie", album="Heroes")
    ]
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []

    with caplog.at_level(logging.WARNING):
        result = reconcile_track(db, track_id, client)

    assert result.platform_track_id == "sp1"
    assert any("title_artist" in r.message for r in caplog.records)
