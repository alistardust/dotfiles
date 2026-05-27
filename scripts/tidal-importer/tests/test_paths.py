"""Tests for paths.py."""
import os
import stat
from pathlib import Path

import pytest
from tidal_importer.paths import validate_no_symlink, validate_output_path, secure_write


class TestValidateNoSymlink:
    def test_normal_path_passes(self, tmp_path):
        target = tmp_path / "file.json"
        target.write_text("test")
        validate_no_symlink(target)

    def test_symlinked_file_rejected(self, tmp_path):
        target = tmp_path / "real.json"
        target.write_text("test")
        link = tmp_path / "link.json"
        link.symlink_to(target)
        with pytest.raises(SystemExit):
            validate_no_symlink(link)

    def test_nonexistent_path_passes(self, tmp_path):
        validate_no_symlink(tmp_path / "new_file.json")


class TestValidateOutputPath:
    def test_path_in_home_passes(self):
        path = Path.home() / "test_output"
        result = validate_output_path(path)
        assert result == path.resolve()

    def test_path_outside_home_and_cwd_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            validate_output_path(Path("/etc/evil_output"))


class TestSecureWrite:
    def test_creates_file_with_0600(self, tmp_path):
        target = tmp_path / "subdir" / "secret.json"
        secure_write(target, '{"token": "abc"}')
        assert target.exists()
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o600

    def test_parent_dir_is_0700(self, tmp_path):
        target = tmp_path / "newdir" / "secret.json"
        secure_write(target, "data")
        parent_mode = stat.S_IMODE(target.parent.stat().st_mode)
        assert parent_mode == 0o700

    def test_refuses_symlinked_target(self, tmp_path):
        real = tmp_path / "real.json"
        real.write_text("original")
        link = tmp_path / "link.json"
        link.symlink_to(real)
        with pytest.raises(SystemExit):
            secure_write(link, "overwrite attempt")

    def test_overwrites_existing_safely(self, tmp_path):
        target = tmp_path / "existing.json"
        secure_write(target, "first")
        secure_write(target, "second")
        assert target.read_text() == "second"
