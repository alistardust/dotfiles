from pathlib import Path
from types import SimpleNamespace
import pytest
from tuneshift.db import Database
from tuneshift.commands.goal_cmd import handle_goal


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "test.db")
    d.create_playlist("Trans Wrath")
    return d


class TestHandleGoal:
    def test_set_goal(self, db: Database) -> None:
        args = SimpleNamespace(playlist="Trans Wrath", text="Celebrate trans fury", clear=False)
        result = handle_goal(args, db)
        assert result == 0
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        assert db.get_goal(pid) == "Celebrate trans fury"

    def test_show_goal(self, db: Database, capsys) -> None:
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        db.set_goal(pid, "Existing goal")
        args = SimpleNamespace(playlist="Trans Wrath", text=None, clear=False)
        handle_goal(args, db)
        out = capsys.readouterr().out
        assert "Existing goal" in out

    def test_clear_goal(self, db: Database) -> None:
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        db.set_goal(pid, "Something")
        args = SimpleNamespace(playlist="Trans Wrath", text=None, clear=True)
        handle_goal(args, db)
        assert db.get_goal(pid) is None
