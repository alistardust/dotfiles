# tests/where-were-we/conftest.py
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "where-were-we" / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Isolate HOME so no test can touch the real session store or ledgers."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("COPILOT_AGENT_SESSION_ID", raising=False)
    return tmp_path
