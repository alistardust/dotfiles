"""No write reaches a live streaming platform without explicit authority.

BUG-28 made a bare invocation resolve the real library instead of an empty
stray. That removed the accident that had been keeping ``order`` and
``sync --apply`` inert: both push by default, and only ``rm`` ever asked
whether the active database was the primary one.

The guard is placed at the client boundary rather than at each call site, so a
new mutating call is covered the day it is written. Authority is process-level,
set once by the CLI from the path it already resolved, and unset means refuse.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import tuneshift.commands.ingest_cmd as ingest_cmd
import tuneshift.persistence.primary as primary
from tuneshift import TuneShiftError
from tuneshift.models import PlaylistInfo, TrackResult
from tuneshift.platforms.write_guard import (
    NonPrimaryPushError,
    grant_push_authority,
    push_authority_error,
    require_push_authority,
    revoke_push_authority,
)

MUTATORS = (
    ("create_playlist", ("New",)),
    ("add_tracks", ("pl-1", ["t-1"])),
    ("remove_tracks_by_positions", ("pl-1", [0])),
    ("replace_playlist_tracks", ("pl-1", ["t-1"])),
)


class _FakeClient:
    """A client that records calls instead of reaching a platform."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def platform_name(self) -> str:
        return "tidal"

    def load_session(self) -> bool:
        return True

    def search_track(self, query: str, limit: int = 10) -> list[TrackResult]:
        self.calls.append("search_track")
        return []

    def get_playlist_tracks(self, playlist_id: str) -> list[TrackResult]:
        self.calls.append("get_playlist_tracks")
        return []

    def find_playlist_by_name(self, name: str) -> PlaylistInfo | None:
        self.calls.append("find_playlist_by_name")
        return None

    def create_playlist(self, name: str, description: str = "") -> PlaylistInfo:
        self.calls.append("create_playlist")
        return PlaylistInfo(platform_id="pl-new", name=name, num_tracks=0)

    def add_tracks(self, playlist_id: str, track_ids: list[str]) -> int:
        self.calls.append("add_tracks")
        return len(track_ids)

    def remove_tracks_by_positions(self, playlist_id: str, positions: list[int]) -> int:
        self.calls.append("remove_tracks_by_positions")
        return len(positions)

    def replace_playlist_tracks(self, playlist_id: str, track_ids: list[str]) -> None:
        self.calls.append("replace_playlist_tracks")


@pytest.fixture(autouse=True)
def _isolate_authority():
    """Authority is process-level, so no test may inherit or leak it."""
    revoke_push_authority()
    yield
    revoke_push_authority()


@pytest.fixture
def guarded(tmp_path: Path):
    """A fake client wrapped exactly as the factory wraps a real one."""
    from tuneshift.platforms.factory import guard_client

    return guard_client(_FakeClient())


def _register(monkeypatch, tmp_path: Path, marker_target: Path) -> Path:
    """Register ``marker_target`` as the primary library."""
    marker = tmp_path / "primary_db"
    monkeypatch.setattr(primary, "marker_path", lambda: marker)
    marker_target.touch()
    primary.set_primary_db(marker_target)
    return marker


# --- the refusal decision ------------------------------------------------


def test_unset_authority_refuses(guarded):
    """A client built outside the CLI has no authority, so it cannot push."""
    with pytest.raises(NonPrimaryPushError):
        guarded.add_tracks("pl-1", ["t-1"])


def test_unregistered_primary_refuses(monkeypatch, tmp_path: Path):
    """With no primary registered, nothing can be told apart from a copy."""
    monkeypatch.setattr(primary, "marker_path", lambda: tmp_path / "absent")
    grant_push_authority(tmp_path / "library.db")

    with pytest.raises(NonPrimaryPushError) as excinfo:
        require_push_authority()
    assert "primary --set" in str(excinfo.value)


def test_mismatched_primary_refuses(monkeypatch, tmp_path: Path):
    """A copy carries the platform IDs, so a push from it hits the original."""
    _register(monkeypatch, tmp_path, tmp_path / "real.db")
    copy = tmp_path / "copy.db"
    copy.touch()
    grant_push_authority(copy)

    with pytest.raises(NonPrimaryPushError) as excinfo:
        require_push_authority()
    assert "--allow-nonprimary-push" in str(excinfo.value)


def test_the_two_refusals_name_different_remedies(monkeypatch, tmp_path: Path):
    """Same authority, different fix: registering versus overriding.

    Collapsing these into one message makes a fresh checkout look like a wall
    when it is a five-second registration.
    """
    monkeypatch.setattr(primary, "marker_path", lambda: tmp_path / "absent")
    grant_push_authority(tmp_path / "library.db")
    unregistered = push_authority_error()

    _register(monkeypatch, tmp_path, tmp_path / "real.db")
    copy = tmp_path / "copy.db"
    copy.touch()
    grant_push_authority(copy)
    mismatch = push_authority_error()

    assert unregistered is not None
    assert mismatch is not None
    assert unregistered != mismatch
    assert "--allow-nonprimary-push" not in unregistered
    assert "primary --set" not in mismatch


def test_primary_database_is_allowed(monkeypatch, tmp_path: Path, guarded):
    """The registered library is the one place a push is expected to work."""
    real = tmp_path / "real.db"
    _register(monkeypatch, tmp_path, real)
    grant_push_authority(real)

    guarded.add_tracks("pl-1", ["t-1"])
    assert guarded.calls == ["add_tracks"]


def test_override_allows_a_nonprimary_push(monkeypatch, tmp_path: Path, guarded):
    """``--allow-nonprimary-push`` is the deliberate way through."""
    _register(monkeypatch, tmp_path, tmp_path / "real.db")
    copy = tmp_path / "copy.db"
    copy.touch()
    grant_push_authority(copy, override=True)

    guarded.replace_playlist_tracks("pl-1", ["t-1"])
    assert guarded.calls == ["replace_playlist_tracks"]


def test_unreadable_marker_refuses_with_its_own_remedy(monkeypatch, tmp_path: Path):
    """An unreadable marker must not be read as permission.

    ``get_primary_db`` once treated every OSError as "unregistered". Under a
    fail-open guard that bug would silently authorise a live push.
    """
    marker = tmp_path / "primary_db"
    marker.mkdir()  # unreadable as a file, without depending on permissions
    monkeypatch.setattr(primary, "marker_path", lambda: marker)
    grant_push_authority(tmp_path / "library.db")

    with pytest.raises(NonPrimaryPushError) as excinfo:
        require_push_authority()
    message = str(excinfo.value)
    assert "Cannot read the primary-database marker" in message
    assert "cannot be told apart from a copy" in message


def test_revoke_returns_to_refusing(monkeypatch, tmp_path: Path, guarded):
    """Authority does not outlive the run that granted it."""
    real = tmp_path / "real.db"
    _register(monkeypatch, tmp_path, real)
    grant_push_authority(real)
    guarded.add_tracks("pl-1", ["t-1"])

    revoke_push_authority()
    with pytest.raises(NonPrimaryPushError):
        guarded.add_tracks("pl-1", ["t-1"])


def test_refusal_is_a_tuneshift_error(guarded):
    """The CLI error boundary turns it into exit 1, not a traceback."""
    assert issubclass(NonPrimaryPushError, TuneShiftError)


# --- the client boundary -------------------------------------------------


@pytest.mark.parametrize("method,call_args", MUTATORS)
def test_every_mutating_method_is_intercepted(guarded, method, call_args):
    """All four protocol mutators refuse, not just the ones commands use today."""
    with pytest.raises(NonPrimaryPushError):
        getattr(guarded, method)(*call_args)
    assert guarded.calls == []


def test_reads_are_untouched_while_refusing(guarded):
    """A library with no push authority is still fully usable for reading."""
    assert guarded.search_track("q") == []
    assert guarded.get_playlist_tracks("pl-1") == []
    assert guarded.find_playlist_by_name("Mix") is None
    assert guarded.calls == [
        "search_track",
        "get_playlist_tracks",
        "find_playlist_by_name",
    ]


def test_non_protocol_attributes_forward(guarded):
    """The proxy must be transparent, or callers break in unrelated ways."""
    assert guarded.platform_name == "tidal"
    assert guarded.load_session() is True


def test_factory_returns_none_for_an_unknown_platform():
    from tuneshift.platforms.factory import load_client

    assert load_client("myspace") is None


@pytest.mark.parametrize(
    ("platform_name", "module_path", "class_name"),
    [
        ("tidal", "tuneshift.platforms.tidal", "TidalClient"),
        ("spotify", "tuneshift.platforms.spotify", "SpotifyClient"),
        ("ytmusic", "tuneshift.platforms.ytmusic", "YTMusicClient"),
    ],
)
def test_every_platform_is_constructed_guarded(
    monkeypatch, platform_name, module_path, class_name
):
    """The whole commit rests on this: construction is what applies the guard.

    A factory that forgot to wrap one platform would pass every call-site test,
    because those patch the client in. This asserts the returned object itself
    refuses, so an unwrapped platform cannot pass unnoticed.
    """
    import importlib

    from tuneshift.platforms.factory import load_client

    module = importlib.import_module(module_path)
    monkeypatch.setattr(module, class_name, _FakeClient)

    client = load_client(platform_name)

    assert client is not None
    with pytest.raises(NonPrimaryPushError):
        client.add_tracks("pl-1", ["t-1"])


@pytest.mark.parametrize(
    "module_path",
    [
        "tuneshift.commands.resolve",
        "tuneshift.commands.ingest_cmd",
        "tuneshift.commands.map_cmd",
        "tuneshift.commands.link_cmd",
    ],
)
def test_load_client_delegates_to_the_factory(monkeypatch, module_path):
    """Every construction site funnels through one place, or the guard has holes."""
    import importlib

    module = importlib.import_module(module_path)
    sentinel = object()
    monkeypatch.setattr(
        "tuneshift.platforms.factory.load_client", lambda name: sentinel
    )
    assert module._load_client("tidal") is sentinel


# --- the commands that push ----------------------------------------------


def _playlist_with_platform(db, platform: str = "tidal") -> int:
    from tuneshift.models import Track

    playlist_id = db.create_playlist("Mix")
    track_id = db.insert_track(Track(title="Alpha", artist="A"))
    db.set_playlist_tracks(playlist_id, [track_id])
    db.link_platform_playlist(playlist_id, platform, "pl-1")
    return playlist_id


def test_order_cannot_push_without_authority(monkeypatch, tmp_db: Path, capsys):
    """The exposure BUG-28 uncovered: ``order`` pushes by default."""
    from tuneshift.commands.order_cmd import _push_order_to_platforms
    from tuneshift.db import Database

    db = Database(tmp_db)
    _playlist_with_platform(db)
    client = _FakeClient()
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda name: client)

    had_failures = _push_order_to_platforms(db, db.find_playlist_by_name("Mix"))

    assert had_failures is True
    assert client.calls == []
    assert "Refusing to push" in capsys.readouterr().err
    db.close()


def test_order_never_degrades_a_refusal_to_a_platform_failure(
    monkeypatch, tmp_db: Path, tmp_path: Path
):
    """A refusal must escape the per-platform ``except``, not be absorbed by it.

    ``order`` deliberately swallows one platform's error so the others still
    sync. A refusal is not that kind of error: absorbing it would print "sync
    failed", hiding both the reason and the one-line remedy. Authority is
    granted so the up-front check passes, leaving only the inner re-raise under
    test.
    """
    import tuneshift.commands.order_cmd as order_cmd
    from tuneshift.db import Database
    from tuneshift.platforms.factory import guard_client

    db = Database(tmp_db)
    playlist_id = _playlist_with_platform(db)
    track_id = db.get_playlist_tracks(playlist_id)[0].id
    db.set_platform_mapping(track_id, "tidal", "t-1")

    real = tmp_path / "real.db"
    _register(monkeypatch, tmp_path, real)
    grant_push_authority(real)

    def _refuse() -> None:
        raise NonPrimaryPushError("Refusing to push: test")

    monkeypatch.setattr("tuneshift.platforms.factory.require_push_authority", _refuse)
    client = guard_client(_FakeClient())
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda name: client)

    with pytest.raises(NonPrimaryPushError):
        order_cmd._push_order_to_platforms(db, db.find_playlist_by_name("Mix"))

    db.close()


def test_add_push_helper_refuses_without_authority(monkeypatch, tmp_db: Path, capsys):
    """``add``'s push helper has no production caller today, but it is live code.

    Guarding at the client boundary means it is covered the day it is re-wired,
    without anyone remembering to add a check.
    """
    from tuneshift.commands.add_cmd import _sync_add_to_platforms
    from tuneshift.db import Database

    db = Database(tmp_db)
    playlist_id = _playlist_with_platform(db)
    track_id = db.get_playlist_tracks(playlist_id)[0].id
    client = _FakeClient()
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda name: client)

    failed = _sync_add_to_platforms(db, playlist_id, track_id, "Alpha", "A")

    assert failed is True
    assert client.calls == []
    assert "Refusing to push" in capsys.readouterr().err
    db.close()


def test_sync_apply_cannot_push_without_authority(tmp_db: Path):
    """``sync --apply`` creates and replaces playlists on the platform."""
    from tuneshift.db import Database
    from tuneshift.planapply.sync import make_sync_executor

    db = Database(tmp_db)
    _playlist_with_platform(db)
    client = _FakeClient()
    execute = make_sync_executor(db, client)
    change = SimpleNamespace(
        proposed={"playlist_name": "Mix", "track_ids": ["t-1"]},
    )

    with pytest.raises(NonPrimaryPushError):
        execute(change)
    assert client.calls == []
    db.close()


@pytest.mark.parametrize(
    "handler,call_args",
    [
        ("_folders_create", ("New",)),
        ("_folders_rename", ("Old", "New")),
        ("_folders_delete", ("Old",)),
        ("_folders_sync", ()),
    ],
)
def test_folder_writes_require_authority(
    monkeypatch, tmp_db: Path, capsys, handler, call_args
):
    """Folder writes bypass the protocol by reaching through ``client._session``.

    The proxy cannot see those calls, so these sites ask for authority directly.
    """
    import tuneshift.commands.folders_cmd as folders_cmd
    from tuneshift.db import Database

    db = Database(tmp_db)
    db.cache_tidal_folder("trn:folder:1", "Old")
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda name: _FakeClient())

    assert getattr(folders_cmd, handler)(db, *call_args) == 1
    assert "Refusing to push" in capsys.readouterr().err
    db.close()


def test_folder_reads_still_work_without_authority(monkeypatch, tmp_db: Path):
    """Listing and status are reads, so refusing them would be wrong."""
    import tuneshift.commands.folders_cmd as folders_cmd
    from tuneshift.db import Database

    db = Database(tmp_db)
    monkeypatch.setattr(ingest_cmd, "_load_client", lambda name: _FakeClient())

    assert folders_cmd._folders_status(db) == 0
    db.close()


# --- the CLI grants authority -------------------------------------------


def test_cli_grants_authority_from_the_resolved_path(monkeypatch, tmp_path: Path):
    """``main`` is the only place that knows which library was opened."""
    from tuneshift import cli

    real = tmp_path / "real.db"
    _register(monkeypatch, tmp_path, real)
    seen: dict[str, object] = {}

    def _capture(active: Path, *, override: bool = False) -> None:
        seen["active"] = active
        seen["override"] = override

    monkeypatch.setattr(cli, "grant_push_authority", _capture)
    cli.main(["--db", str(real), "list"])

    assert seen["active"] == real.resolve()
    assert seen["override"] is False


def test_cli_revokes_authority_when_the_run_ends(monkeypatch, tmp_path: Path):
    """Authority must not outlive the run that granted it.

    It is process-level state, so anything sharing the process after ``main``
    returns would inherit a push grant it never asked for.
    """
    from tuneshift import cli

    real = tmp_path / "real.db"
    _register(monkeypatch, tmp_path, real)

    assert cli.main(["--db", str(real), "list"]) == 0

    assert push_authority_error() is not None


def test_cli_revokes_authority_even_when_the_command_fails(
    monkeypatch, tmp_path: Path, capsys
):
    """The revoke sits in ``finally``: a crash must not leave a grant behind."""
    from tuneshift import cli

    real = tmp_path / "real.db"
    _register(monkeypatch, tmp_path, real)

    def _explode(args, db):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "_dispatch_command", _explode)
    assert cli.main(["--db", str(real), "list"]) == 2
    capsys.readouterr()

    assert push_authority_error() is not None


def test_cli_passes_the_override_through(monkeypatch, tmp_path: Path):
    """``--allow-nonprimary-push`` reaches the guard from any command."""
    from tuneshift import cli

    real = tmp_path / "real.db"
    _register(monkeypatch, tmp_path, real)
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "grant_push_authority",
        lambda active, *, override=False: seen.update(override=override),
    )
    cli.main(["--db", str(real), "order", "Mix", "--allow-nonprimary-push"])

    assert seen["override"] is True


def test_bootstrap_commands_grant_no_authority(monkeypatch, tmp_path: Path):
    """``login``, ``config`` and ``primary`` run without a library at all.

    No library means no path to grant authority from, so the run stays in the
    refusing state rather than being granted something derived or guessed.
    """
    from tuneshift import DatabaseNotFoundError, cli

    monkeypatch.setattr(primary, "marker_path", lambda: tmp_path / "primary_db")

    def _unresolvable() -> Path:
        raise DatabaseNotFoundError("no library")

    monkeypatch.setattr(cli, "get_default_db_path", _unresolvable)
    granted: list[object] = []
    monkeypatch.setattr(
        cli,
        "grant_push_authority",
        lambda active, *, override=False: granted.append(active),
    )

    assert cli.main(["primary"]) == 0
    assert granted == []
    assert push_authority_error() is not None
