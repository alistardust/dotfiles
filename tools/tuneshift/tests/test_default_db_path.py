"""Default database resolution refuses to guess a library into existence (BUG-28).

A path the user named is intent and may be created. A path derived here is a
guess, and creating a guess produces an empty database that is indistinguishable
from a lost collection. So the derived path is used only when a database is
really there, and otherwise the command stops.

The arithmetic tests build a throwaway package tree and point ``base.__file__``
at it, so they exercise the real expression rather than a stub of it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import tuneshift.persistence.base as base
import tuneshift.persistence.primary as primary
from tuneshift import DatabaseNotFoundError
from tuneshift.persistence.base import get_default_db_path

SOURCE_LAYOUT = "database beside the package, as in a source or editable checkout"
WHEEL_LAYOUT = "database inside the package, as an installed wheel would place it"


def _fake_package(root: Path) -> Path:
    """Build a package tree under ``root``, returning a stand-in for base.__file__."""
    base_file = root / "pkgroot" / "tuneshift" / "persistence" / "base.py"
    base_file.parent.mkdir(parents=True)
    base_file.touch()
    return base_file


def _make_db(path: Path) -> Path:
    """Create a real SQLite file at ``path``.

    Tests that mean "a library is here" must produce something that is actually
    a database. An empty file is what BUG-28 left behind, so using ``touch()``
    to stand in for a library would assert the opposite of the intent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS marker (id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    return path


def _source_layout_db(root: Path) -> Path:
    return root / "pkgroot" / "tuneshift.db"


def _wheel_layout_db(root: Path) -> Path:
    return root / "pkgroot" / "tuneshift" / "tuneshift.db"


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Detach resolution from the real environment and the real registration."""
    monkeypatch.delenv("TUNESHIFT_DB", raising=False)
    marker = tmp_path / "marker" / "primary_db"
    marker.parent.mkdir()
    monkeypatch.setattr(primary, "marker_path", lambda: marker)
    monkeypatch.setattr(base, "__file__", str(_fake_package(tmp_path)))
    return tmp_path


# --- precedence -----------------------------------------------------------


def test_env_var_outranks_a_registered_primary(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit TUNESHIFT_DB beats a registration: the nearer intent wins."""
    registered = isolated / "registered.db"
    registered.touch()
    primary.set_primary_db(registered)
    chosen = isolated / "from-env.db"
    monkeypatch.setenv("TUNESHIFT_DB", str(chosen))

    assert get_default_db_path() == chosen


def test_env_var_path_need_not_exist(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path the user typed may be created; that is how a library is bootstrapped."""
    chosen = isolated / "brand-new.db"
    monkeypatch.setenv("TUNESHIFT_DB", str(chosen))

    assert get_default_db_path() == chosen
    assert not chosen.exists(), "resolution must not create the file itself"


def test_registered_primary_outranks_the_derived_path(isolated: Path) -> None:
    """Registration is an assertion by the user and beats any arithmetic."""
    registered = isolated / "the-real-library.db"
    _make_db(registered)
    derived = _make_db(_source_layout_db(isolated))
    resolved_registration = primary.set_primary_db(registered)

    assert get_default_db_path() == resolved_registration
    assert get_default_db_path() != derived


def test_derived_path_is_used_when_nothing_is_registered(isolated: Path) -> None:
    """With no env and no registration, a database that is really there is used."""
    derived = _make_db(_source_layout_db(isolated))

    assert get_default_db_path() == derived


# --- the arithmetic itself ------------------------------------------------


def test_source_layout_is_found(isolated: Path) -> None:
    """The checkout layout puts the database beside the package, not inside it."""
    expected = _make_db(_source_layout_db(isolated))

    assert get_default_db_path() == expected


def test_wheel_layout_is_found(isolated: Path) -> None:
    """An installed wheel puts it inside the package; both layouts must resolve."""
    expected = _make_db(_wheel_layout_db(isolated))

    assert get_default_db_path() == expected


def test_source_layout_wins_when_both_exist(isolated: Path) -> None:
    """A stray inside the package must not shadow the real library beside it.

    This is the exact shape BUG-28 produced: an empty file at the inner path
    while the real collection sat at the outer one. Both files here are valid
    databases on purpose, so what is proven is the ordering rule and not merely
    that the inner file was rejected for being empty.
    """
    real = _make_db(_source_layout_db(isolated))
    _make_db(_wheel_layout_db(isolated))

    assert get_default_db_path() == real


# --- refusal --------------------------------------------------------------


def test_refuses_when_nothing_resolves(isolated: Path) -> None:
    """No env, no registration, no database on disk: stop rather than invent one."""
    with pytest.raises(DatabaseNotFoundError):
        get_default_db_path()


def test_refusal_names_both_remedies(isolated: Path) -> None:
    """An error a user cannot act on is only a slower failure."""
    with pytest.raises(DatabaseNotFoundError) as caught:
        get_default_db_path()

    message = str(caught.value)
    assert "--db" in message
    assert "primary --set" in message


def test_refusal_reports_where_it_looked(isolated: Path) -> None:
    """Naming the candidates turns a dead end into a diagnosis."""
    with pytest.raises(DatabaseNotFoundError) as caught:
        get_default_db_path()

    message = str(caught.value)
    assert str(_source_layout_db(isolated)) in message
    assert str(_wheel_layout_db(isolated)) in message


def test_refusal_creates_nothing(isolated: Path) -> None:
    """The failure path must leave the filesystem exactly as it found it."""
    before = sorted(p for p in isolated.rglob("*") if p.is_file())

    with pytest.raises(DatabaseNotFoundError):
        get_default_db_path()

    after = sorted(p for p in isolated.rglob("*") if p.is_file())
    assert after == before


def test_a_registered_primary_that_has_gone_missing_refuses(isolated: Path) -> None:
    """Recreating a moved or deleted library as an empty file is the BUG-28 harm.

    Registration proved the path once. If it is gone now, that is a fact worth
    reporting, not a reason to manufacture a replacement.
    """
    registered = isolated / "was-here.db"
    _make_db(registered)
    primary.set_primary_db(registered)
    registered.unlink()

    with pytest.raises(DatabaseNotFoundError) as caught:
        get_default_db_path()

    assert str(registered) in str(caught.value)


def test_missing_primary_is_not_masked_by_a_derived_database(isolated: Path) -> None:
    """Falling through to a different library would silently swap collections."""
    registered = isolated / "was-here.db"
    _make_db(registered)
    primary.set_primary_db(registered)
    registered.unlink()
    _make_db(_source_layout_db(isolated))

    with pytest.raises(DatabaseNotFoundError):
        get_default_db_path()


def test_the_error_is_a_tuneshift_error(isolated: Path) -> None:
    """The CLI's handler prints TuneShiftError cleanly; a bare exception traces."""
    from tuneshift import TuneShiftError

    assert issubclass(DatabaseNotFoundError, TuneShiftError)


# --- existence is not evidence --------------------------------------------


def test_a_zero_byte_derived_file_is_not_accepted(isolated: Path) -> None:
    """The BUG-28 stray was exactly this, so accepting it would reselect it.

    Existence proves only that something made a file. A library has a SQLite
    header; a stray left by the old resolution has nothing in it at all.
    """
    _source_layout_db(isolated).touch()

    with pytest.raises(DatabaseNotFoundError):
        get_default_db_path()


def test_a_derived_file_that_is_not_a_database_is_not_accepted(
    isolated: Path,
) -> None:
    """Non-empty is not the test either; the file has to be what it claims."""
    _source_layout_db(isolated).write_bytes(b"x" * 4096)

    with pytest.raises(DatabaseNotFoundError):
        get_default_db_path()


def test_a_real_database_is_still_found_past_a_stray(isolated: Path) -> None:
    """Rejecting the stray must not abandon the search while a library remains."""
    _source_layout_db(isolated).touch()
    expected = _make_db(_wheel_layout_db(isolated))

    assert get_default_db_path() == expected


def test_the_refusal_names_files_that_were_present_but_not_databases(
    isolated: Path,
) -> None:
    """A refusal that says "nothing found" beside a file that plainly exists
    reads as a lie.

    Naming it is also the only in-product report of the leftover stray, which
    is the artifact this whole fix exists because of.
    """
    stray = _source_layout_db(isolated)
    stray.touch()

    with pytest.raises(DatabaseNotFoundError) as caught:
        get_default_db_path()

    message = str(caught.value)
    assert str(stray) in message
    assert "not a database" in message


def test_a_registered_primary_that_is_not_a_database_refuses(isolated: Path) -> None:
    """A registration can rot: the path survives while the file is replaced."""
    registered = isolated / "the-real-library.db"
    _make_db(registered)
    primary.set_primary_db(registered)
    registered.write_bytes(b"")

    with pytest.raises(DatabaseNotFoundError) as caught:
        get_default_db_path()

    assert str(registered) in str(caught.value)


def test_an_invalid_primary_is_not_masked_by_a_derived_database(
    isolated: Path,
) -> None:
    """Falling through would swap collections without saying so."""
    registered = isolated / "the-real-library.db"
    _make_db(registered)
    primary.set_primary_db(registered)
    registered.write_bytes(b"")
    _make_db(_source_layout_db(isolated))

    with pytest.raises(DatabaseNotFoundError):
        get_default_db_path()


def test_checking_a_candidate_does_not_create_or_alter_it(isolated: Path) -> None:
    """Probing must not open the file: opening a database migrates it."""
    stray = _source_layout_db(isolated)
    stray.touch()
    before = stray.stat().st_size

    with pytest.raises(DatabaseNotFoundError):
        get_default_db_path()

    assert stray.stat().st_size == before
    assert not _wheel_layout_db(isolated).exists()


# --- an unreadable registration is not an absent one ----------------------


def test_an_unreadable_marker_is_not_read_as_unregistered(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failing to learn the answer must not be mistaken for the answer.

    Treating a permissions failure as "no primary registered" would make the
    push guard fall open on a transient filesystem problem, which is the one
    state it exists to refuse.
    """
    from tuneshift import PrimaryMarkerError

    marker = primary.marker_path()
    marker.write_text("/somewhere/library.db\n", encoding="utf-8")

    def deny(*_args: object, **_kwargs: object) -> str:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", deny)

    with pytest.raises(PrimaryMarkerError):
        primary.get_primary_db()


def test_an_absent_marker_is_read_as_unregistered(isolated: Path) -> None:
    """The ordinary case stays ordinary: never registered means None."""
    assert primary.get_primary_db() is None


def test_an_unreadable_primary_is_not_reported_as_a_replaced_one(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two states need different remedies, so they need different messages.

    A file that cannot be read is still the library. Calling it replaced sends
    the reader to re-register a path that was already correct, and leaves the
    permissions problem that actually blocked them untouched.
    """
    registered = isolated / "the-real-library.db"
    _make_db(registered)
    primary.set_primary_db(registered)

    real_open = Path.open

    def deny(self: Path, *args: object, **kwargs: object) -> object:
        if self.name == registered.name:
            raise PermissionError(13, "Permission denied")
        return real_open(self, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "open", deny)

    with pytest.raises(DatabaseNotFoundError) as caught:
        get_default_db_path()

    message = str(caught.value)
    assert str(registered) in message
    assert "cannot be read" in message
    assert "replaced" not in message
