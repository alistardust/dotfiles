"""``rm`` must identify the remote track by its recorded platform id.

The platform-side removal used to re-find the track by case-insensitive title
*containment* and delete the first hit, so removing "Blue" could delete
"Blue Moon", "Bluebird" or "Blue in Green". These tests pin the identity rules
that replace it:

* remove by recorded platform id, preferring a per-playlist override over the
  library-wide mapping;
* fall back to exact title AND artist only when no id was ever recorded, and
  only when exactly one remote track matches;
* never take that fallback for a pinned track;
* distinguish "already absent" (a success) from "something is there that I
  cannot safely identify" (a refusal).
"""

from pathlib import Path
from types import SimpleNamespace

import tuneshift.commands.ingest_cmd as ingest_cmd
import tuneshift.persistence.primary as primary
from tuneshift.commands.rm_cmd import handle_rm
from tuneshift.db import Database
from tuneshift.models import Track

PLATFORM = "tidal"
ARTIST = "Joni Mitchell"


class _FakeClient:
    """Records the positions asked for, so a wrong deletion is visible."""

    def __init__(self, tracks):
        self._tracks = tracks
        self.removed = None

    def load_session(self):
        return True

    def get_playlist_tracks(self, platform_playlist_id):
        return self._tracks

    def remove_tracks_by_positions(self, platform_playlist_id, positions):
        self.removed = positions


def _remote(platform_id, title, artist=ARTIST):
    """A track as the platform reports it."""
    return SimpleNamespace(platform_id=platform_id, title=title, artist=artist)


def _seed(db, local=(("Blue", ARTIST),)):
    """Insert ``local`` (title, artist) pairs and link a platform playlist."""
    playlist_id = db.create_playlist("Mix")
    track_ids = [db.insert_track(Track(title=t, artist=a)) for t, a in local]
    db.set_playlist_tracks(playlist_id, track_ids)
    db.link_platform_playlist(playlist_id, PLATFORM, "pl-1")
    return playlist_id, track_ids


def _run(db, tmp_db, client, monkeypatch, target="Blue"):
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)
    primary.set_primary_db(Path(tmp_db))
    args = SimpleNamespace(playlist="Mix", target=target, yes=True)
    return handle_rm(args, db)


def test_mapped_id_beats_a_substring_title_match(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """The bug itself: removing "Blue" must not delete "Blue Moon"."""
    db = Database(tmp_db)
    _, track_ids = _seed(db)
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue")
    client = _FakeClient(
        [_remote("t-bluemoon", "Blue Moon"), _remote("t-blue", "Blue")]
    )

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed == [1]


def test_per_playlist_override_wins_over_the_library_mapping(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """A curated per-playlist release is the one sitting in this playlist."""
    db = Database(tmp_db)
    playlist_id, track_ids = _seed(db)
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue-1999")
    db.set_playlist_track_mapping(playlist_id, track_ids[0], PLATFORM, "t-blue-2009")
    client = _FakeClient(
        [_remote("t-blue-1999", "Blue"), _remote("t-blue-2009", "Blue")]
    )

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed == [1]


def test_library_mapping_is_used_when_there_is_no_override(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    db = Database(tmp_db)
    _, track_ids = _seed(db)
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue")
    client = _FakeClient([_remote("t-other", "Blue"), _remote("t-blue", "Blue")])

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed == [1]


def test_either_recorded_id_is_accepted(tmp_db: Path, capsys, monkeypatch) -> None:
    """``order`` pushes the library id, ``apply`` the override; both are real.

    Only one of them can be the id actually sitting remotely, and both name a
    verified release of this same track, so matching either is safe.
    """
    db = Database(tmp_db)
    playlist_id, track_ids = _seed(db)
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue-1999")
    db.set_playlist_track_mapping(playlist_id, track_ids[0], PLATFORM, "t-blue-2009")
    client = _FakeClient([_remote("t-blue-1999", "Blue")])

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed == [0]


def test_mapped_id_absent_with_a_plausible_candidate_refuses(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """A different version of the curated release is not ours to delete."""
    db = Database(tmp_db)
    _, track_ids = _seed(db)
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue-2009")
    client = _FakeClient([_remote("t-blue-2019", "Blue (2019 Remaster)")])

    assert _run(db, tmp_db, client, monkeypatch) == 1
    assert client.removed is None
    assert "refusing to remove" in capsys.readouterr().err


def test_mapped_id_absent_with_nothing_plausible_is_already_absent(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """The end state asked for already holds, so this item succeeds."""
    db = Database(tmp_db)
    _, track_ids = _seed(db)
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue")
    client = _FakeClient([_remote("t-river", "River")])

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed is None
    assert "already absent" in capsys.readouterr().out


def test_unmapped_track_falls_back_to_exact_title_and_artist(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """With no id ever recorded, title is the only evidence available."""
    db = Database(tmp_db)
    _seed(db)
    client = _FakeClient(
        [_remote("t-bluemoon", "Blue Moon"), _remote("t-blue", "Blue")]
    )

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed == [1]


def test_unmapped_track_refuses_a_containment_only_candidate(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """The bug in its purest form: "Blue Moon" is not "Blue".

    With no id recorded, the exact matcher finds nothing. The old code fell
    back to containment here and deleted "Blue Moon". The wider candidate
    probe catches it and refuses instead of reporting it already gone.
    """
    db = Database(tmp_db)
    _seed(db)
    client = _FakeClient([_remote("t-bluemoon", "Blue Moon")])

    assert _run(db, tmp_db, client, monkeypatch) == 1
    assert client.removed is None
    assert "refusing to remove" in capsys.readouterr().err


def test_exact_fallback_ignores_case_and_surrounding_whitespace(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """Platforms vary casing and padding; that is not a version difference."""
    db = Database(tmp_db)
    _seed(db)
    client = _FakeClient([_remote("t-blue", "  blue ", artist="joni mitchell")])

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed == [0]


def test_unmapped_track_refuses_two_exact_matches(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    db = Database(tmp_db)
    _seed(db)
    client = _FakeClient([_remote("t-a", "Blue"), _remote("t-b", "Blue")])

    assert _run(db, tmp_db, client, monkeypatch) == 1
    assert client.removed is None
    assert "refusing to remove" in capsys.readouterr().err


def test_unmapped_track_ignores_a_same_title_different_artist(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """136 tracks share a title with a different artist; none are collisions."""
    db = Database(tmp_db)
    _seed(db)
    client = _FakeClient([_remote("t-rimes", "Blue", artist="LeAnn Rimes")])

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed is None
    assert "already absent" in capsys.readouterr().out


def test_pinned_track_never_takes_the_title_fallback(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """A pin states that version identity matters for this entry."""
    db = Database(tmp_db)
    playlist_id, track_ids = _seed(db)
    db.set_pin(playlist_id, track_ids[0], "opener")
    client = _FakeClient([_remote("t-blue", "Blue")])

    assert _run(db, tmp_db, client, monkeypatch) == 1
    assert client.removed is None
    assert "pinned" in capsys.readouterr().err


def test_pin_does_not_block_removal_by_recorded_id(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """The pin vetoes guessing, not removal itself."""
    db = Database(tmp_db)
    playlist_id, track_ids = _seed(db)
    db.set_pin(playlist_id, track_ids[0], "opener")
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue")
    client = _FakeClient([_remote("t-blue", "Blue")])

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed == [0]


def test_only_one_occurrence_is_removed_when_the_id_appears_twice(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """Mirror the single local removal; do not wipe both copies."""
    db = Database(tmp_db)
    _, track_ids = _seed(db)
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue")
    client = _FakeClient([_remote("t-blue", "Blue"), _remote("t-blue", "Blue")])

    assert _run(db, tmp_db, client, monkeypatch) == 0
    assert client.removed == [0]


def test_success_message_names_the_remote_track_removed(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """A bare "removed" is what made a wrong deletion silent."""
    db = Database(tmp_db)
    _, track_ids = _seed(db)
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue")
    client = _FakeClient(
        [_remote("t-bluemoon", "Blue Moon"), _remote("t-blue", "Blue")]
    )

    assert _run(db, tmp_db, client, monkeypatch) == 0
    out = capsys.readouterr().out
    assert f'removed "Blue - {ARTIST}"' in out


def test_a_refusal_still_leaves_the_local_removal_done(
    tmp_db: Path, capsys, monkeypatch
) -> None:
    """Documents the split: the local removal commits before the push."""
    db = Database(tmp_db)
    playlist_id, track_ids = _seed(db)
    db.set_platform_mapping(track_ids[0], PLATFORM, "t-blue-2009")
    client = _FakeClient([_remote("t-blue-2019", "Blue (2019 Remaster)")])

    assert _run(db, tmp_db, client, monkeypatch) == 1
    assert db.get_playlist_tracks(playlist_id) == []
