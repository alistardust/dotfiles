from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from tuneshift.commands.prefs_cmd import handle_prefs, load_global_preferences


class TestLoadGlobalPreferences:
    def test_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        prefs = load_global_preferences(tmp_path / "nonexistent.toml")
        assert prefs["version_preferences"]["prefer"] == ["studio", "original", "explicit"]

    def test_loads_from_toml(self, tmp_path: Path) -> None:
        config = tmp_path / "prefs.toml"
        config.write_text('[version_preferences]\nprefer = ["live", "explicit"]\n')
        prefs = load_global_preferences(config)
        assert prefs["version_preferences"]["prefer"] == ["live", "explicit"]


class TestHandlePrefs:
    def test_show_displays_current(self, capsys, tmp_path: Path) -> None:
        config = tmp_path / "prefs.toml"
        config.write_text('[version_preferences]\nprefer = ["studio"]\n')
        args = SimpleNamespace(action="show", config_path=str(config))
        handle_prefs(args)
        out = capsys.readouterr().out
        assert "studio" in out

    def test_set_writes_preference(self, tmp_path: Path) -> None:
        config = tmp_path / "prefs.toml"
        args = SimpleNamespace(action="set", key="version_preferences.prefer", value='["live", "explicit"]', config_path=str(config))
        handle_prefs(args)
        prefs = load_global_preferences(config)
        assert prefs["version_preferences"]["prefer"] == ["live", "explicit"]
