"""Safety contract for the remove command.

``rm`` used to delete locally and push the deletion to every linked
platform with no dry run, no confirmation, and no protection when the active
database is a copy. The trap is that pointing ``TUNESHIFT_DB`` at a copy does
NOT isolate the live playlist, because the platform IDs travel with the
database. A copied database is not a sandbox.

A numeric argument used to resolve as a title substring before it was tried
as a position, so ``rm <playlist> 3`` could silently remove a track whose
title merely contains a 3, and then push that removal live.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import tuneshift.commands.ingest_cmd as ingest_cmd
import tuneshift.commands.rm_cmd as rm_cmd
import tuneshift.persistence.primary as primary
from tuneshift.commands.rm_cmd import handle_rm
from tuneshift.db import Database
from tuneshift.models import Track

TITLES = ("Alpha", "Song 3", "Gamma")


class _FakeClient:
    def __init__(self, tracks=None):
        self._tracks = tracks or []
        self.removed = None

    def load_session(self):
        return True

    def get_playlist_tracks(self, platform_playlist_id):
        return self._tracks

    def remove_tracks_by_positions(self, platform_playlist_id, positions):
        self.removed = positions


def _remote_tracks(titles=TITLES):
    """Remote tracks as a platform reports them.

    Identity comes from the platform id, falling back to exact title AND
    artist, so a remote track has to carry both fields.
    """
    return [
        SimpleNamespace(platform_id=f"t-{i}", title=t, artist="A")
        for i, t in enumerate(titles)
    ]


def _seed(db: Database, *, titles=TITLES, platform=None) -> int:
    playlist_id = db.create_playlist("Mix")
    ids = [db.insert_track(Track(title=t, artist="A")) for t in titles]
    db.set_playlist_tracks(playlist_id, ids)
    if platform:
        db.link_platform_playlist(playlist_id, platform, "pl-1")
    return playlist_id


def _args(**overrides) -> SimpleNamespace:
    base = {
        "playlist": "Mix",
        "target": "3",
        "position": False,
        "title": False,
        "dry_run": False,
        "yes": False,
        "allow_nonprimary_push": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _titles(db: Database, playlist_id: int) -> list[str]:
    return [t.title for t in db.get_playlist_tracks(playlist_id)]


@pytest.fixture
def as_primary(monkeypatch, tmp_db: Path):
    """Treat the test database as the configured primary, so pushes proceed."""
    primary.set_primary_db(Path(tmp_db))


class TestNumericTargetDisambiguation:
    """A bare number must not silently resolve to a title."""

    def test_ambiguous_numeric_is_refused(self, tmp_db: Path, capsys) -> None:
        db = Database(tmp_db)
        playlist_id = _seed(db)
        assert handle_rm(_args(target="3"), db) == 1
        assert _titles(db, playlist_id) == list(TITLES), "nothing may be removed"
        assert "ambiguous" in capsys.readouterr().err.lower()

    def test_position_flag_forces_position(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        playlist_id = _seed(db)
        assert handle_rm(_args(target="3", position=True), db) == 0
        assert _titles(db, playlist_id) == ["Alpha", "Song 3"]

    def test_title_flag_forces_title(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        playlist_id = _seed(db)
        assert handle_rm(_args(target="3", title=True), db) == 0
        assert _titles(db, playlist_id) == ["Alpha", "Gamma"]

    def test_unambiguous_numeric_still_means_position(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        playlist_id = _seed(db, titles=("Alpha", "Beta", "Gamma"))
        assert handle_rm(_args(target="2"), db) == 0
        assert _titles(db, playlist_id) == ["Alpha", "Gamma"]


class TestRemoveIsGatedBeforePushing:
    """No silent path from a local edit to a live platform mutation."""

    def test_dry_run_changes_nothing_local_or_remote(
        self, tmp_db: Path, monkeypatch, as_primary, capsys
    ) -> None:
        db = Database(tmp_db)
        playlist_id = _seed(db, platform="tidal")
        client = _FakeClient(tracks=_remote_tracks())
        monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)

        assert handle_rm(_args(target="Alpha", dry_run=True), db) == 0
        assert _titles(db, playlist_id) == list(TITLES)
        assert client.removed is None
        assert "dry run" in capsys.readouterr().out.lower()

    def test_declining_confirmation_aborts_entirely(
        self, tmp_db: Path, monkeypatch, as_primary
    ) -> None:
        db = Database(tmp_db)
        playlist_id = _seed(db, platform="tidal")
        client = _FakeClient(tracks=_remote_tracks())
        monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)
        monkeypatch.setattr("builtins.input", lambda *_: "n")

        assert handle_rm(_args(target="Alpha"), db) == 1
        assert _titles(db, playlist_id) == list(TITLES), "local state must survive"
        assert client.removed is None

    def test_yes_flag_pushes_without_prompting(
        self, tmp_db: Path, monkeypatch, as_primary
    ) -> None:
        db = Database(tmp_db)
        playlist_id = _seed(db, platform="tidal")
        client = _FakeClient(tracks=_remote_tracks())
        monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)

        def _no_prompt(*_args, **_kwargs):
            raise AssertionError("--yes must not prompt")

        monkeypatch.setattr("builtins.input", _no_prompt)

        assert handle_rm(_args(target="Alpha", yes=True), db) == 0
        assert _titles(db, playlist_id) == ["Song 3", "Gamma"]
        assert client.removed == [0]

    def test_local_only_removal_needs_no_confirmation(self, tmp_db: Path) -> None:
        """No linked platform means no live mutation, so no prompt."""
        db = Database(tmp_db)
        playlist_id = _seed(db)
        assert handle_rm(_args(target="Alpha"), db) == 0
        assert _titles(db, playlist_id) == ["Song 3", "Gamma"]


class TestCopiedDatabaseIsNotASandbox:
    """Platform IDs travel with a copied database, so it is not a sandbox."""

    def test_push_is_refused_when_db_is_not_the_primary(
        self, tmp_db: Path, monkeypatch, capsys
    ) -> None:
        db = Database(tmp_db)
        playlist_id = _seed(db, platform="tidal")
        client = _FakeClient(tracks=_remote_tracks())
        monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)
        monkeypatch.setattr(
            primary, "get_primary_db", lambda: Path("/nowhere/primary.db")
        )

        assert handle_rm(_args(target="Alpha", yes=True), db) == 1
        assert client.removed is None, "a copy must never reach the live playlist"
        assert _titles(db, playlist_id) == list(TITLES)
        err = capsys.readouterr().err.lower()
        assert "not the primary" in err

    def test_override_flag_allows_the_push(
        self, tmp_db: Path, monkeypatch
    ) -> None:
        db = Database(tmp_db)
        _seed(db, platform="tidal")
        client = _FakeClient(tracks=_remote_tracks())
        monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)
        monkeypatch.setattr(
            primary, "get_primary_db", lambda: Path("/nowhere/primary.db")
        )

        args = _args(target="Alpha", yes=True, allow_nonprimary_push=True)
        assert handle_rm(args, db) == 0
        assert client.removed == [0]


class TestDisambiguationPromptIsBounded:
    """The multi-match prompt must only accept a position it offered.

    Found by an adversarial review of the numeric-target fix. The prompt
    indexed the full track list, so a choice outside the offered set selected
    a bystander and then pushed that removal live. Python's negative indexing
    made the worst cases silent rather than an IndexError: "0" resolved to
    tracks[-1], the LAST track, and "-1" resolved to tracks[-2].
    """

    @pytest.mark.parametrize("choice", ["0", "-1", "3"])
    def test_unoffered_choice_is_refused(
        self, tmp_db: Path, capsys, monkeypatch, choice
    ) -> None:
        db = Database(tmp_db)
        # Positions 1 and 2 match "Alpha"; position 3 does not.
        _seed(db, titles=("Alpha one", "Alpha two", "Bystander"))
        monkeypatch.setattr("builtins.input", lambda *_: choice)

        before = db.get_playlist_track_ids(
            db.find_playlist_by_name("Mix").id
        )
        assert handle_rm(_args(target="Alpha", title=True), db) == 1
        after = db.get_playlist_track_ids(db.find_playlist_by_name("Mix").id)
        assert after == before, "no track may be removed"
        assert "not one of the offered positions" in capsys.readouterr().err

    def test_offered_choice_still_works(self, tmp_db: Path, monkeypatch) -> None:
        db = Database(tmp_db)
        pid = _seed(db, titles=("Alpha one", "Alpha two", "Bystander"))
        monkeypatch.setattr("builtins.input", lambda *_: "2")

        assert handle_rm(_args(target="Alpha", title=True), db) == 0
        remaining = [t.title for t in db.get_playlist_tracks(pid)]
        assert remaining == ["Alpha one", "Bystander"]


class TestPrimaryIsComparedByIdentity:
    """The guard compares files on disk, not path strings.

    A symlink to the primary IS the primary; refusing it would push users
    toward --allow-nonprimary-push, which trains away the habit the guard
    exists to build.
    """

    def test_symlink_to_primary_is_accepted(
        self, tmp_db: Path, tmp_path: Path, monkeypatch
    ) -> None:
        db = Database(tmp_db)
        _seed(db, platform="tidal")
        client = _FakeClient(tracks=_remote_tracks())
        monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)

        link = tmp_path / "linked.db"
        link.symlink_to(tmp_db)
        primary.set_primary_db(link)

        assert handle_rm(_args(target="Alpha", title=True, yes=True), db) == 0
        assert client.removed == [0]

    def test_a_real_copy_is_still_refused(
        self, tmp_db: Path, tmp_path: Path, capsys, monkeypatch
    ) -> None:
        """Byte-identical is not good enough: a copy is a different file."""
        import shutil

        db = Database(tmp_db)
        _seed(db, platform="tidal")
        client = _FakeClient(tracks=_remote_tracks())
        monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)

        copy = tmp_path / "copy.db"
        shutil.copy(tmp_db, copy)
        primary.set_primary_db(copy)

        assert handle_rm(_args(target="Alpha", title=True, yes=True), db) == 1
        assert client.removed is None
        assert "not the primary database" in capsys.readouterr().err


class TestUnregisteredIsNotMistakenForACopy:
    """An unregistered primary must not push users toward the override.

    Ali's point when she caught the inverted guard: a check that fires on the
    only correct case teaches people to keep --allow-nonprimary-push switched
    on, and once that lives in a script beside --yes, the protection is
    gone at exactly the moment it was supposed to apply. So the remedy offered
    for "unregistered" is registration, never the override.
    """

    def test_message_points_at_registration_not_the_override(
        self, tmp_db: Path, capsys, monkeypatch
    ) -> None:
        db = Database(tmp_db)
        _seed(db, platform="tidal")
        client = _FakeClient(tracks=_remote_tracks())
        monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)
        monkeypatch.setattr(primary, "get_primary_db", lambda: None)

        assert handle_rm(_args(target="Alpha", title=True, yes=True), db) == 1
        err = capsys.readouterr().err
        assert "no primary database is registered" in err
        assert "tuneshift primary --set" in err
        assert "--allow-nonprimary-push" not in err
        assert client.removed is None

    def test_override_still_works_when_unregistered(
        self, tmp_db: Path, monkeypatch
    ) -> None:
        """The escape hatch remains available, just not advertised as the fix."""
        db = Database(tmp_db)
        _seed(db, platform="tidal")
        client = _FakeClient(tracks=_remote_tracks())
        monkeypatch.setattr(ingest_cmd, "_load_client", lambda platform: client)
        monkeypatch.setattr(primary, "get_primary_db", lambda: None)

        args = _args(
            target="Alpha", title=True, yes=True, allow_nonprimary_push=True
        )
        assert handle_rm(args, db) == 0
        assert client.removed == [0]
