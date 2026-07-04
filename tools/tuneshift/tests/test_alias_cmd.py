"""CLI surface for artist-alias management (``tuneshift alias ...``)."""
from types import SimpleNamespace

import pytest

from tuneshift.commands.alias_cmd import handle_alias
from tuneshift.db import Database

DEG = "\u00b0"
ORD = "\u00ba"


@pytest.fixture()
def db(tmp_path):
    database = Database(tmp_path / "alias.db")
    yield database
    database.close()


def _args(action, **kw):
    return SimpleNamespace(action=action, **kw)


class TestList:
    def test_lists_seed_classes_tagged(self, db, capsys):
        assert handle_alias(_args("list"), db) == 0
        out = capsys.readouterr().out
        assert "98 Degrees" in out and f"98{ORD}" in out
        assert "[seed]" in out

    def test_user_class_tagged_user(self, db, capsys):
        db.add_artist_alias(["Prince", "The Artist"])
        handle_alias(_args("list"), db)
        out = capsys.readouterr().out
        assert "[user] Prince, The Artist" in out

    def test_user_extension_of_seed_tagged_seed_plus_user(self, db, capsys):
        db.add_artist_alias([f"98{ORD}", "Ninety-Eight Degrees"])
        handle_alias(_args("list"), db)
        out = capsys.readouterr().out
        assert "[seed+user]" in out
        assert "Ninety-Eight Degrees" in out


class TestShow:
    def test_member_reports_class(self, db, capsys):
        assert handle_alias(_args("show", artist=f"98{ORD}"), db) == 0
        out = capsys.readouterr().out
        assert "belongs to an alias class" in out
        assert "98 Degrees" in out

    def test_non_member(self, db, capsys):
        assert handle_alias(_args("show", artist="Gorillaz"), db) == 0
        assert "not in any alias class" in capsys.readouterr().out


class TestAdd:
    def test_add_creates_class(self, db, capsys):
        assert handle_alias(_args("add", members=["Prince", "The Artist"]), db) == 0
        assert db.get_artist_alias_classes() == [frozenset({"Prince", "The Artist"})]
        assert "Added alias class" in capsys.readouterr().out

    def test_add_requires_two_distinct(self, db, capsys):
        assert handle_alias(_args("add", members=["Solo"]), db) == 1
        assert handle_alias(_args("add", members=["Dup", "Dup"]), db) == 1
        assert db.get_artist_alias_classes() == []


class TestRemove:
    def test_remove_user_member(self, db, capsys):
        db.add_artist_alias(["Prince", "The Artist"])
        assert handle_alias(_args("remove", member="The Artist"), db) == 0
        assert db.get_artist_alias_classes() == []
        assert "Removed" in capsys.readouterr().out

    def test_remove_seed_member_is_read_only(self, db, capsys):
        assert handle_alias(_args("remove", member="Kesha"), db) == 1
        assert "seed alias and cannot be removed" in capsys.readouterr().out

    def test_remove_absent_member(self, db, capsys):
        assert handle_alias(_args("remove", member="Nobody"), db) == 1
        assert "not in any user-defined alias class" in capsys.readouterr().out
