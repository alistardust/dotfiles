"""Re-ingesting a linked playlist must not silently discard local-only tracks.

The destructive mechanism is positional, not a delete. ``playlist_tracks`` is
keyed ``PRIMARY KEY (playlist_id, position)`` and the old ingest loop wrote the
remote tracks over positions 1..N with ``INSERT OR REPLACE``. Every local row
occupying one of those positions was evicted, and because the key is position
rather than track, a remote track could also land at two positions at once.

These tests pin the merge contract: remote order leads, local-only tracks are
kept, and anything that does drop tracks has to be asked for and counted.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tuneshift import ingest as ingest_module
from tuneshift.db import Database
from tuneshift.ingest import ingest_from_platform
from tuneshift.models import PlaylistInfo, Track, TrackResult


@pytest.fixture(autouse=True)
def _no_background_enrichment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep these tests on the merge logic, off the network and the LLM."""
    monkeypatch.setattr(ingest_module, "_enrich_tracks", lambda *a, **k: None)
    monkeypatch.setattr(ingest_module, "_auto_classify_batch", lambda *a, **k: None)


def _client(*titles: str, name: str = "Laurel Canyon Sunset") -> MagicMock:
    """Build a fake platform client serving ``titles`` as the remote playlist."""
    client = MagicMock()
    client.platform_name = "tidal"
    client.get_playlist.return_value = PlaylistInfo(
        platform_id="pl_1", name=name, num_tracks=len(titles)
    )
    client.get_playlist_tracks.return_value = [
        TrackResult(
            platform_id=f"tid_{title.replace(' ', '_')}",
            title=title,
            artist="Joni Mitchell",
            album="Blue",
        )
        for title in titles
    ]
    return client


def _seed_local(db: Database, name: str, *titles: str) -> int:
    """Create a local playlist holding ``titles`` and return its id."""
    playlist_id = db.create_playlist(name)
    track_ids = [
        db.add_track(Track(title=title, artist="Joni Mitchell", album="Blue"))
        for title in titles
    ]
    db.set_playlist_tracks(playlist_id, track_ids)
    return playlist_id


def _titles(db: Database, playlist_id: int) -> list[str]:
    return [t.title for t in db.get_playlist_tracks(playlist_id)]


def test_local_only_track_survives_a_reingest(tmp_db: Path) -> None:
    """A track present locally and absent remotely is kept, not evicted."""
    db = Database(tmp_db)
    playlist_id = _seed_local(db, "Laurel Canyon Sunset", "Carey", "River", "Blue")

    # Remote lacks "River", which exists only locally.
    result = ingest_from_platform(db, _client("Carey", "Blue", "All I Want"), "pl_1")

    assert "River" in _titles(db, playlist_id), (
        "the local-only track was discarded by re-ingest"
    )
    assert result.kept_local_only == 1


def test_reingest_does_not_duplicate_a_track_across_positions(tmp_db: Path) -> None:
    """A remote track already held locally occupies exactly one position."""
    db = Database(tmp_db)
    playlist_id = _seed_local(db, "Laurel Canyon Sunset", "Carey", "River", "Blue")

    ingest_from_platform(db, _client("Carey", "Blue", "All I Want"), "pl_1")

    titles = _titles(db, playlist_id)
    assert len(titles) == len(set(titles)), f"duplicate rows created: {titles}"


def test_merge_keeps_remote_order_and_appends_local_only(tmp_db: Path) -> None:
    """Remote order leads; local-only tracks follow in their existing order."""
    db = Database(tmp_db)
    playlist_id = _seed_local(
        db, "Laurel Canyon Sunset", "Carey", "River", "Blue", "Willy"
    )

    # Remote keeps Blue and Carey, in that order, and drops River and Willy.
    ingest_from_platform(db, _client("Blue", "Carey", "All I Want"), "pl_1")

    assert _titles(db, playlist_id) == [
        "Blue",
        "Carey",
        "All I Want",
        "River",
        "Willy",
    ]


def test_merge_reports_additions_and_retentions(tmp_db: Path) -> None:
    """The result counts playlist additions and local-only retentions."""
    db = Database(tmp_db)
    _seed_local(db, "Laurel Canyon Sunset", "Carey", "River")

    result = ingest_from_platform(db, _client("Carey", "All I Want"), "pl_1")

    assert result.added_to_playlist == 1  # All I Want
    assert result.kept_local_only == 1  # River
    assert result.removed_from_playlist == 0


def test_replace_drops_local_only_tracks_and_counts_them(tmp_db: Path) -> None:
    """Replace is still available, but it has to be asked for and is counted."""
    db = Database(tmp_db)
    playlist_id = _seed_local(db, "Laurel Canyon Sunset", "Carey", "River", "Blue")

    result = ingest_from_platform(
        db, _client("Carey", "Blue"), "pl_1", replace=True
    )

    assert _titles(db, playlist_id) == ["Carey", "Blue"]
    assert result.removed_from_playlist == 1
    assert result.kept_local_only == 0


def test_first_ingest_of_a_new_playlist_is_unaffected(tmp_db: Path) -> None:
    """With no local playlist there is nothing to merge; behaviour is unchanged."""
    db = Database(tmp_db)

    result = ingest_from_platform(db, _client("Carey", "River"), "pl_1")

    playlist = db.find_playlist_by_name("Laurel Canyon Sunset")
    assert playlist is not None
    assert _titles(db, playlist.id) == ["Carey", "River"]
    assert result.new_tracks == 2
    assert result.added_to_playlist == 2
    assert result.kept_local_only == 0


def test_a_track_listed_twice_remotely_lands_once(tmp_db: Path) -> None:
    """A remote playlist may list a track twice; the local model may not hold it twice.

    Membership is a set locally: ``remove_track_from_playlist`` deletes every
    occurrence of a track id and ``get_track_position`` returns a single row,
    so a second row for the same track is one neither path can address. The
    old positional write created exactly that, because the key was position
    rather than track.
    """
    db = Database(tmp_db)
    playlist_id = _seed_local(db, "Laurel Canyon Sunset")

    result = ingest_from_platform(db, _client("Carey", "Blue", "Carey"), "pl_1")

    titles = _titles(db, playlist_id)
    assert titles.count("Carey") == 1, f"duplicate playlist row created: {titles}"
    assert sorted(titles) == ["Blue", "Carey"]
    assert result.added_to_playlist == 2, (
        "the duplicate was counted as a distinct addition"
    )
