"""Doctor's environment check: is this the database you think it is?

BUG-28. ``get_default_db_path()`` derives its path from
``persistence/base.py``, which sits one directory below the package root, so
in a source checkout it resolves beside the package rather than above it. No
library exists there, SQLite creates an empty file on demand rather than
failing, and the collection appears to have vanished.

These tests are hermetic: every path is synthetic, so the result does not
depend on the state of the machine running them. That coupling is the defect
that put this check here in the first place.
"""

from pathlib import Path

import pytest

from tuneshift.db import Database
from tuneshift.doctor.environment import check_database_environment


@pytest.fixture
def active(tmp_path: Path) -> Database:
    """A real, open database standing in for the one the user is using."""
    return Database(tmp_path / "active.db")


class TestStrayDetection:
    def test_reports_a_database_at_the_derived_path(
        self, active: Database, tmp_path: Path
    ) -> None:
        stray = tmp_path / "stray.db"
        stray.write_bytes(b"")

        warnings = check_database_environment(active, derived=stray)

        assert any(str(stray) in w for w in warnings), warnings

    def test_says_which_file_a_bare_invocation_would_open(
        self, active: Database, tmp_path: Path
    ) -> None:
        """The warning is useless unless it names both sides of the mix-up."""
        stray = tmp_path / "stray.db"
        stray.write_bytes(b"")

        joined = " ".join(check_database_environment(active, derived=stray))

        assert str(stray) in joined
        assert str(Path(active.path).resolve()) in joined

    def test_silent_when_the_derived_path_is_the_active_database(
        self, active: Database
    ) -> None:
        """The normal case: no warning when they are the same file."""
        warnings = check_database_environment(active, derived=Path(active.path))

        assert not any("bare" in w for w in warnings), warnings

    def test_silent_when_nothing_exists_at_the_derived_path(
        self, active: Database, tmp_path: Path
    ) -> None:
        warnings = check_database_environment(active, derived=tmp_path / "absent.db")

        assert not any("bare" in w for w in warnings), warnings

    def test_never_opens_the_file_it_is_warning_about(
        self, active: Database, tmp_path: Path
    ) -> None:
        """The check must not open, migrate or otherwise touch the stray.

        Opening a database runs migrations against it, so a check that probed
        the stray by opening it would modify the very file it is reporting as
        suspect. The stray here is deliberately not a valid database: if the
        check tried to open it, that would raise rather than warn.
        """
        stray = tmp_path / "stray.db"
        stray.write_bytes(b"not a database at all")
        before = stray.read_bytes()

        warnings = check_database_environment(active, derived=stray)

        assert stray.read_bytes() == before
        assert any(str(stray) in w for w in warnings), warnings


class TestEmptyActiveDatabase:
    def test_reports_an_active_database_with_no_playlists(
        self, active: Database
    ) -> None:
        warnings = check_database_environment(active, derived=Path(active.path))

        assert any("no playlists" in w for w in warnings), warnings

    def test_silent_when_the_active_database_has_playlists(
        self, active: Database
    ) -> None:
        active.create_playlist("Laurel Canyon Sunset")

        warnings = check_database_environment(active, derived=Path(active.path))

        assert not any("no playlists" in w for w in warnings), warnings


class TestDefaultDerivedPath:
    def test_defaults_to_the_path_a_bare_invocation_would_use(
        self, active: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Called with no explicit path, it checks the real derived default.

        Pinned so the check cannot silently start inspecting something else.
        """
        import tuneshift.doctor.environment as env

        seen: list[Path] = []

        def _record() -> Path:
            probe = Path("/nonexistent/probe.db")
            seen.append(probe)
            return probe

        monkeypatch.setattr(env, "_derived_default", _record)

        check_database_environment(active)

        assert seen, "expected the derived default to be consulted"

    def test_env_var_override_is_not_mistaken_for_a_stray(
        self, active: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TUNESHIFT_DB pointing somewhere deliberate is not a mix-up.

        The derived default must be computed from the package layout, not
        from the environment, or every deliberate override would look like
        the bug this check exists to find.
        """
        monkeypatch.setenv("TUNESHIFT_DB", str(active.path))
        import tuneshift.doctor.environment as env

        derived = env._derived_default()

        assert derived != Path(active.path)


class TestDoctorWiring:
    """The check is worthless unless doctor actually runs it, and runs it
    before the parts that need a platform login."""

    def test_doctor_prints_the_warning_to_stderr(
        self, active: Database, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from types import SimpleNamespace

        from tuneshift.commands.doctor_cmd import handle_doctor

        # --orphans is the one mode that needs no network, so this exercises
        # the wiring without reaching a platform.
        handle_doctor(SimpleNamespace(orphans=True, enqueue_orphans=False), active)

        assert "no playlists" in capsys.readouterr().err

    def test_doctor_exit_code_is_unaffected_by_warnings(
        self, active: Database, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Advisory means advisory. A warning must not turn a clean run red."""
        from types import SimpleNamespace

        from tuneshift.commands.doctor_cmd import handle_doctor

        code = handle_doctor(
            SimpleNamespace(orphans=True, enqueue_orphans=False), active
        )

        assert code == 0
        assert "no playlists" in capsys.readouterr().err
