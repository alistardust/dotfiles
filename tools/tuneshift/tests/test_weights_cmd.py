from pathlib import Path
from types import SimpleNamespace
import pytest
from tuneshift.db import Database
from tuneshift.commands.weights_cmd import handle_weights


@pytest.fixture
def db(tmp_path: Path) -> Database:
    d = Database(tmp_path / "test.db")
    d.create_playlist("Trans Wrath")
    return d


class TestHandleWeights:
    def test_set_preset(self, db: Database) -> None:
        args = SimpleNamespace(
            playlist="Trans Wrath", preset="narrative-queen",
            values=None, action="set",
        )
        result = handle_weights(args, db)
        assert result == 0
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        w = db.get_weights(pid)
        assert w["narrative_arc"] == 0.9

    def test_set_granular(self, db: Database) -> None:
        args = SimpleNamespace(
            playlist="Trans Wrath", preset=None,
            values=["narrative_arc=0.8", "mood_continuity=0.6"],
            action="set",
        )
        handle_weights(args, db)
        pid = [p for p in db.list_playlists() if p.name == "Trans Wrath"][0].id
        w = db.get_weights(pid)
        assert w["narrative_arc"] == 0.8
        assert w["mood_continuity"] == 0.6

    def test_list_presets(self, db: Database, capsys) -> None:
        args = SimpleNamespace(playlist=None, preset=None, values=None, action="list")
        handle_weights(args, db)
        out = capsys.readouterr().out
        assert "narrative-queen" in out
        assert "energy-wave" in out
