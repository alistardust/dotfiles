"""The CLI must stay recoverable when no database can be resolved (BUG-28).

Two obligations pull against each other. Every command needs a database, so an
unresolvable one has to stop the command. But ``primary --set`` is the remedy
for exactly that condition, so if it were also stopped the user would be locked
out of the fix with no way back in.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tuneshift.persistence.base as base
import tuneshift.persistence.primary as primary
from tuneshift.cli import main


@pytest.fixture
def no_resolvable_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An environment where nothing points at a database."""
    monkeypatch.delenv("TUNESHIFT_DB", raising=False)
    marker = tmp_path / "marker" / "primary_db"
    marker.parent.mkdir()
    monkeypatch.setattr(primary, "marker_path", lambda: marker)
    fake_base = tmp_path / "pkgroot" / "tuneshift" / "persistence" / "base.py"
    fake_base.parent.mkdir(parents=True)
    fake_base.touch()
    monkeypatch.setattr(base, "__file__", str(fake_base))
    return tmp_path


def test_a_command_refuses_instead_of_creating_a_database(
    no_resolvable_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``list`` stops with a non-zero status rather than opening an empty library."""
    code = main(["list"])

    assert code == 1
    assert "Error:" in capsys.readouterr().err


def test_the_refusal_is_not_a_traceback(
    no_resolvable_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A traceback reads as a crash; this is an expected, actionable condition."""
    main(["list"])

    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "Unexpected error" not in err


def test_the_refusal_tells_the_user_what_to_do(
    no_resolvable_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["list"])

    err = capsys.readouterr().err
    assert "--db" in err
    assert "primary --set" in err


def test_the_refusal_creates_nothing(no_resolvable_database: Path) -> None:
    before = sorted(p for p in no_resolvable_database.rglob("*") if p.is_file())

    main(["list"])

    after = sorted(p for p in no_resolvable_database.rglob("*") if p.is_file())
    assert after == before


def test_primary_set_still_works_with_no_database_resolved(
    no_resolvable_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The way out of the lockout. This is the test that makes the refusal safe."""
    library = no_resolvable_database / "my-library.db"
    main(["--db", str(library), "list"])
    capsys.readouterr()

    code = main(["primary", "--set", str(library)])

    assert code == 0
    assert primary.get_primary_db() == library.resolve()
    assert "my-library.db" in capsys.readouterr().out


def test_registering_a_primary_makes_later_commands_resolve(
    no_resolvable_database: Path,
) -> None:
    """Proves the remedy actually remedies, rather than merely exiting zero."""
    library = no_resolvable_database / "my-library.db"
    main(["--db", str(library), "list"])
    main(["primary", "--set", str(library)])

    assert base.get_default_db_path() == library.resolve()


def test_a_later_command_really_runs_against_the_registered_primary(
    no_resolvable_database: Path,
) -> None:
    """Resolution agreeing is not the same as a command actually working."""
    library = no_resolvable_database / "my-library.db"
    main(["--db", str(library), "list"])
    main(["primary", "--set", str(library)])

    assert main(["list"]) == 0


def test_primary_without_set_reports_the_absence(
    no_resolvable_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Asking which database is primary must answer, not fail, when none is."""
    code = main(["primary"])

    assert code == 0
    assert "No primary database registered" in capsys.readouterr().out


def test_an_explicit_db_flag_is_still_honoured(
    no_resolvable_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path the user typed is intent: it may be created even now."""
    chosen = no_resolvable_database / "typed-by-hand.db"

    code = main(["--db", str(chosen), "list"])

    assert code == 0
    assert chosen.exists()


# --- commands that manage the environment must not need a library ---------


def test_login_runs_without_a_resolvable_database(
    no_resolvable_database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``login`` stores credentials and never reads the library.

    Gating it behind a database makes a fresh machine unrecoverable in the
    ordinary order of operations: authenticate, then ingest.
    """
    called: list[str] = []

    def fake_login(args: object, db: object) -> int:  # noqa: ARG001
        called.append("ran")
        return 0

    monkeypatch.setattr("tuneshift.commands.login_cmd.handle_login", fake_login)

    assert main(["login", "tidal"]) == 0
    assert called == ["ran"]


def test_config_runs_without_a_resolvable_database(
    no_resolvable_database: Path,
) -> None:
    """``config`` edits settings on disk and takes its database argument unused."""
    assert main(["config", "--show"]) == 0


# --- a corrupt database must not lock out its own remedy ------------------


@pytest.fixture
def corrupt_database(
    no_resolvable_database: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point TUNESHIFT_DB at a file that is not a database."""
    corrupt = no_resolvable_database / "corrupt.db"
    corrupt.write_bytes(b"this is not a sqlite file")
    monkeypatch.setenv("TUNESHIFT_DB", str(corrupt))
    return corrupt


def test_a_corrupt_database_reports_instead_of_tracing(
    corrupt_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Opening happens before the error boundary, so this used to escape raw."""
    code = main(["list"])

    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err
    assert str(corrupt_database) in err


def test_a_corrupt_database_does_not_block_primary_set(
    corrupt_database: Path, no_resolvable_database: Path
) -> None:
    """The remedy has to work in the state that needs it.

    A corrupt database is one of the ways a user arrives at "nothing opens",
    and registering a good one is the fix. Refusing it here was a dead end.
    """
    library = no_resolvable_database / "my-library.db"
    main(["--db", str(library), "list"])

    assert main(["primary", "--set", str(library)]) == 0
    assert primary.get_primary_db() == library.resolve()


def test_an_unwritable_parent_directory_reports_instead_of_tracing(
    no_resolvable_database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``Database.__init__`` creates the parent directory, and that can fail.

    Opening still happens before the dispatch error boundary, so an OSError
    raised while making the directory escaped as a traceback even though the
    surrounding failures had already been given clean messages.
    """
    target = no_resolvable_database / "nowhere" / "library.db"
    real_mkdir = Path.mkdir

    def deny(self: Path, *args: object, **kwargs: object) -> None:
        if self.name == "nowhere":
            raise PermissionError(13, "Permission denied")
        real_mkdir(self, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(Path, "mkdir", deny)

    code = main(["--db", str(target), "list"])

    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err
    assert str(target) in err


def test_a_marker_write_failure_reports_instead_of_tracing(
    no_resolvable_database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``primary --set`` ran outside the error boundary and traced on failure."""
    library = no_resolvable_database / "my-library.db"
    main(["--db", str(library), "list"])
    capsys.readouterr()

    def deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(primary, "set_primary_db", deny)

    code = main(["primary", "--set", str(library)])

    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err
    assert "Unexpected error" not in err
    assert "Permission denied" in err


def test_a_symlinked_database_reports_instead_of_tracing(
    no_resolvable_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``Database.__init__`` raises ValueError for a symlink, outside the boundary.

    Refusing a symlink is deliberate, but it was refusing with a traceback
    because the refusal happened before dispatch could catch anything.
    """
    library = no_resolvable_database / "my-library.db"
    main(["--db", str(library), "list"])
    capsys.readouterr()
    link = no_resolvable_database / "link-to-library.db"
    link.symlink_to(library)

    code = main(["--db", str(link), "list"])

    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err
    assert "Unexpected error" not in err
    assert str(link) in err


# --- registration must name a library, not just a path --------------------


def test_primary_set_refuses_a_directory(
    no_resolvable_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory exists, which was the whole test, and is not a library."""
    folder = no_resolvable_database / "not-a-file"
    folder.mkdir()

    code = main(["primary", "--set", str(folder)])

    assert code == 1
    assert primary.get_primary_db() is None
    assert str(folder) in capsys.readouterr().err


def test_primary_set_refuses_a_file_that_is_not_a_database(
    no_resolvable_database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Registering a stray would hand it the authority to push to a platform."""
    stray = no_resolvable_database / "empty.db"
    stray.touch()

    code = main(["primary", "--set", str(stray)])

    assert code == 1
    assert primary.get_primary_db() is None
    assert "not a database" in capsys.readouterr().err.lower()
