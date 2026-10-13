"""Omitting --album must not fork an existing track into a second row.

``find_track`` had two individually defensible behaviours that combined badly:
``add`` passed its optional album straight through, and the lookup treated a
null album as "match only rows whose album is also null" rather than "album
unspecified". A track stored with a real album was therefore invisible to the
most natural invocation of ``add``, which then created a duplicate carrying no
platform mapping, so the duplicate could be neither resolved nor pushed.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from tuneshift.commands.add_cmd import handle_add
from tuneshift.db import Database
from tuneshift.models import PlatformMapping, Track


def _seed(db: Database, title: str, artist: str, album: str | None) -> int:
    return db.add_track(Track(title=title, artist=artist, album=album))


def test_lookup_without_an_album_finds_a_track_that_has_one(tmp_path: Path) -> None:
    """A null album means unspecified, not "the album column is null"."""
    db = Database(tmp_path / "test.db")
    track_id = _seed(db, "Both Sides Now", "Joni Mitchell", "Clouds")

    found = db.find_track("Both Sides Now", "Joni Mitchell", None)

    assert found is not None, "an album-less lookup could not see the stored track"
    assert found.id == track_id


def test_an_explicit_album_still_has_to_match(tmp_path: Path) -> None:
    """Naming an album remains an exact constraint, not a hint."""
    db = Database(tmp_path / "test.db")
    _seed(db, "Both Sides Now", "Joni Mitchell", "Clouds")

    assert db.find_track("Both Sides Now", "Joni Mitchell", "Blue") is None
    assert db.find_track("Both Sides Now", "Joni Mitchell", "Clouds") is not None


def test_plural_lookup_exposes_every_album_for_the_same_song(tmp_path: Path) -> None:
    """Pins the lookup ``add`` now relies on to detect ambiguity."""
    db = Database(tmp_path / "test.db")
    _seed(db, "Both Sides Now", "Joni Mitchell", "Clouds")
    _seed(db, "Both Sides Now", "Joni Mitchell", "Travelogue")

    matches = db.find_tracks_by_title_artist("Both Sides Now", "Joni Mitchell")

    assert len(matches) == 2
    assert {m.album for m in matches} == {"Clouds", "Travelogue"}


def test_add_without_an_album_reuses_the_existing_row(tmp_path: Path) -> None:
    """The library gains a playlist entry, not a second copy of the song."""
    db = Database(tmp_path / "test.db")
    track_id = _seed(db, "Both Sides Now", "Joni Mitchell", "Clouds")
    before = len(db.all_track_ids())

    args = SimpleNamespace(
        playlist="Laurel Canyon Sunset",
        title="Both Sides Now",
        artist="Joni Mitchell",
        album=None,
    )
    assert handle_add(args, db) == 0

    assert len(db.all_track_ids()) == before, "add created a duplicate track row"
    playlist = db.find_playlist_by_name("Laurel Canyon Sunset")
    assert [t.id for t in db.get_playlist_tracks(playlist.id)] == [track_id]


def test_add_without_an_album_keeps_the_platform_mapping(tmp_path: Path) -> None:
    """The reused row carries its mapping, so it stays resolvable and pushable."""
    db = Database(tmp_path / "test.db")
    track_id = _seed(db, "Both Sides Now", "Joni Mitchell", "Clouds")
    db.upsert_platform_mapping(
        PlatformMapping(
            track_id=track_id,
            platform="tidal",
            platform_track_id="tid_42",
            status="matched",
            user_approved=True,
        )
    )

    args = SimpleNamespace(
        playlist="Laurel Canyon Sunset",
        title="Both Sides Now",
        artist="Joni Mitchell",
        album=None,
    )
    assert handle_add(args, db) == 0

    playlist = db.find_playlist_by_name("Laurel Canyon Sunset")
    added = db.get_playlist_tracks(playlist.id)[0]
    mapping = db.get_platform_mapping(added.id, "tidal")
    assert mapping is not None
    assert mapping.platform_track_id == "tid_42"


def test_add_refuses_rather_than_guessing_between_albums(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ambiguity is reported and refused, never resolved by creating a row."""
    db = Database(tmp_path / "test.db")
    _seed(db, "Both Sides Now", "Joni Mitchell", "Clouds")
    _seed(db, "Both Sides Now", "Joni Mitchell", "Travelogue")
    before = len(db.all_track_ids())

    args = SimpleNamespace(
        playlist="Laurel Canyon Sunset",
        title="Both Sides Now",
        artist="Joni Mitchell",
        album=None,
    )
    assert handle_add(args, db) == 1

    assert len(db.all_track_ids()) == before, "add created a row instead of refusing"
    err = capsys.readouterr().err
    assert "Clouds" in err and "Travelogue" in err
    assert "--album" in err


def test_add_with_a_new_song_still_creates_it(tmp_path: Path) -> None:
    """Nothing matching means create, exactly as before."""
    db = Database(tmp_path / "test.db")
    before = len(db.all_track_ids())

    args = SimpleNamespace(
        playlist="Laurel Canyon Sunset",
        title="A Case of You",
        artist="Joni Mitchell",
        album=None,
    )
    assert handle_add(args, db) == 0

    assert len(db.all_track_ids()) == before + 1
