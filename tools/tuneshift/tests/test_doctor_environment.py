"""Doctor's environment check: is this the database you think it is?

BUG-28 left strays behind. The old resolver pointed inside the package, where
no library exists, and SQLite created an empty file on demand rather than
failing, so a collection appeared to have vanished. Resolution now refuses to
guess, but a checkout that ran the old code still has the empty file in it.

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


@pytest.fixture
def beside(tmp_path: Path) -> Path:
    """A real library beside the package, which is what makes an inner file a stray.

    It has to be a real database: an empty file beside the package proves
    nothing about the inner one, and the check now says so.
    """
    path = tmp_path / "beside.db"
    Database(path).close()
    return path


class TestStrayDetection:
    def test_reports_a_database_inside_the_package(
        self, active: Database, beside: Path, tmp_path: Path
    ) -> None:
        stray = tmp_path / "stray.db"
        stray.write_bytes(b"")

        warnings = check_database_environment(active, positions=(beside, stray))

        assert any(str(stray) in w for w in warnings), warnings

    def test_names_every_database_involved(
        self, active: Database, beside: Path, tmp_path: Path
    ) -> None:
        """The warning is useless unless the user can tell the files apart."""
        stray = tmp_path / "stray.db"
        stray.write_bytes(b"")

        joined = " ".join(check_database_environment(active, positions=(beside, stray)))

        assert str(stray) in joined
        assert str(beside) in joined
        assert str(Path(active.path).resolve()) in joined

    def test_claims_no_precedence_it_cannot_know(
        self, active: Database, beside: Path, tmp_path: Path
    ) -> None:
        """It reports what exists, not which file would win.

        Precedence depends on TUNESHIFT_DB and on the registered primary,
        neither of which this check consults, so asserting a winner here
        would be false exactly when the user had deliberately overridden it.
        """
        stray = tmp_path / "stray.db"
        stray.write_bytes(b"")

        joined = " ".join(check_database_environment(active, positions=(beside, stray)))

        assert "takes precedence" not in joined
        assert "would open" not in joined

    def test_reports_when_the_stray_is_the_active_database(
        self, active: Database, beside: Path
    ) -> None:
        """The worst case, which this check used to stay silent on.

        Warning only when the stray is *not* in use meant the one state where
        the user is actually working in the wrong database produced nothing.
        """
        warnings = check_database_environment(
            active, positions=(beside, Path(active.path))
        )

        joined = " ".join(warnings)
        assert str(active.path) in joined
        assert str(beside) in joined
        assert "primary --set" in joined

    def test_silent_when_nothing_exists_at_the_inner_path(
        self, active: Database, beside: Path, tmp_path: Path
    ) -> None:
        warnings = check_database_environment(
            active, positions=(beside, tmp_path / "absent.db")
        )

        assert not any("leftover" in w for w in warnings), warnings

    def test_silent_when_there_is_no_library_beside_the_package(
        self, active: Database, tmp_path: Path
    ) -> None:
        """In a wheel install the inner file is the library, not a stray.

        Only a checkout has a database beside the package, so its absence
        makes the inner file legitimate and warning about it wrong.
        """
        inner = tmp_path / "inner.db"
        inner.write_bytes(b"")

        warnings = check_database_environment(
            active, positions=(tmp_path / "no-such-library.db", inner)
        )

        assert not any("leftover" in w for w in warnings), warnings

    def test_silent_when_the_file_beside_the_package_is_itself_empty(
        self, active: Database, tmp_path: Path
    ) -> None:
        """An empty outer file is not a library, so it settles nothing.

        The argument for calling the inner file a stray rests entirely on a
        real library existing beside it. Without one there is no evidence.
        """
        outer = tmp_path / "outer.db"
        outer.write_bytes(b"")
        inner = tmp_path / "inner.db"
        inner.write_bytes(b"")

        warnings = check_database_environment(active, positions=(outer, inner))

        assert not any("leftover" in w for w in warnings), warnings

    def test_never_opens_the_file_it_is_warning_about(
        self, active: Database, beside: Path, tmp_path: Path
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

        warnings = check_database_environment(active, positions=(beside, stray))

        assert stray.read_bytes() == before
        assert any(str(stray) in w for w in warnings), warnings


class TestEmptyActiveDatabase:
    def test_reports_an_active_database_with_no_playlists(
        self, active: Database, beside: Path
    ) -> None:
        warnings = check_database_environment(
            active, positions=(beside, Path(active.path))
        )

        assert any("no playlists" in w for w in warnings), warnings

    def test_silent_when_the_active_database_has_playlists(
        self, active: Database, beside: Path
    ) -> None:
        active.create_playlist("Laurel Canyon Sunset")

        warnings = check_database_environment(
            active, positions=(beside, Path(active.path))
        )

        assert not any("no playlists" in w for w in warnings), warnings


class TestDefaultLayoutPositions:
    def test_defaults_to_the_positions_resolution_considers(
        self,
        active: Database,
        beside: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Called with no explicit paths, it checks the real layout.

        The substituted positions are made to produce a warning, so the test
        fails if the check calls the resolver and then ignores what it says.
        Recording the call alone would pass against a discarded result.
        """
        import tuneshift.doctor.environment as env

        stray = tmp_path / "pkg" / "tuneshift.db"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_bytes(b"")

        monkeypatch.setattr(env, "_layout_positions", lambda: (beside, stray))

        warnings = check_database_environment(active)

        assert any(str(stray) in w for w in warnings), warnings

    def test_positions_come_from_the_resolver_itself(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Shared, not copied: a second copy of this arithmetic already caused a bug.

        Proven by changing the resolver's answer and requiring doctor to follow.
        Comparing the two against the real layout would pass just as happily
        against an independent copy of the expression, which is exactly the
        thing being ruled out.
        """
        import tuneshift.doctor.environment as env
        import tuneshift.persistence.base as base

        invented = (Path("/invented/beside.db"), Path("/invented/inside.db"))
        monkeypatch.setattr(base, "derived_db_candidates", lambda: invented)

        assert env._layout_positions() == invented

    def test_env_var_override_is_not_mistaken_for_a_stray(
        self, active: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TUNESHIFT_DB pointing somewhere deliberate is not a mix-up.

        The positions must be computed from the package layout, not from the
        environment, or every deliberate override would look like the bug
        this check exists to find.
        """
        monkeypatch.setenv("TUNESHIFT_DB", str(active.path))
        import tuneshift.doctor.environment as env

        assert Path(active.path) not in env._layout_positions()


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
