"""AC1/AC2: reconcile selects explicit by default, clean when preferred (Task 5)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tuneshift.db import Database
from tuneshift.models import Track, TrackResult
from tuneshift.reconcile import reconcile_track


@pytest.fixture
def db_with_track(tmp_path: Path) -> tuple[Database, int]:
    db = Database(tmp_path / "test.db")
    tid = db.add_track(Track(
        title="Bodak Yellow", artist="Cardi B",
        album="Invasion of Privacy", duration_seconds=224,
    ))
    return db, tid


def _client_two_lyric_versions() -> MagicMock:
    """Two same-identity candidates differing only by the structured explicit
    flag; neither title carries a (Clean)/(Explicit) marker."""
    client = MagicMock()
    client.platform_name = "tidal"
    client.search_isrc.return_value = None
    client.search_album.return_value = []
    client.search_artist.return_value = []
    client.get_artist_albums.return_value = []
    client.get_album_tracks.return_value = []
    client.search_track.return_value = [
        TrackResult(
            platform_id="clean_id", title="Bodak Yellow", artist="Cardi B",
            album="Invasion of Privacy", duration_seconds=224,
            isrc="US1", explicit=False,
        ),
        TrackResult(
            platform_id="explicit_id", title="Bodak Yellow", artist="Cardi B",
            album="Invasion of Privacy", duration_seconds=224,
            isrc="US1", explicit=True,
        ),
    ]
    return client


def test_explicit_selected_by_default(db_with_track):
    db, tid = db_with_track
    result = reconcile_track(db, tid, _client_two_lyric_versions(), force=True)
    assert result.platform_track_id == "explicit_id"


def test_prefer_clean_selects_clean(db_with_track):
    db, tid = db_with_track
    db.set_global_preferences({"prefer": ["clean"], "avoid": []})
    result = reconcile_track(db, tid, _client_two_lyric_versions(), force=True)
    assert result.platform_track_id == "clean_id"


def test_quick_top_score_does_not_over_score_clean_candidate():
    # Review-gate regression: _quick_top_score drives the ISRC short-circuit
    # (threshold 100). A clean ISRC hit must NOT score 100, or the search stops
    # before a later strategy can find the explicit release.
    from tuneshift.models import Track as _T
    from tuneshift.reconcile import _quick_top_score

    track = _T(title="Bodak Yellow", artist="Cardi B", album="Invasion of Privacy",
               duration_seconds=224)
    clean = TrackResult(
        platform_id="clean_id", title="Bodak Yellow", artist="Cardi B",
        album="Invasion of Privacy", duration_seconds=224, isrc="US1", explicit=False,
    )
    explicit = TrackResult(
        platform_id="explicit_id", title="Bodak Yellow", artist="Cardi B",
        album="Invasion of Privacy", duration_seconds=224, isrc="US1", explicit=True,
    )
    # A clean-only candidate set is down-ranked below the 100 short-circuit bar;
    # an explicit candidate still reaches it.
    assert _quick_top_score(track, [clean]) < 100
    assert _quick_top_score(track, [explicit]) >= 100
