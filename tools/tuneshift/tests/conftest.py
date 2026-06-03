"""Shared test fixtures for tuneshift."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Provide a temporary DB path for tests."""
    return tmp_path / "test.db"
