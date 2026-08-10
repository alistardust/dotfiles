# tests/where-were-we/conftest.py
import sqlite3
import sys
from pathlib import Path

import pytest

# Importing the skill scripts would otherwise leave __pycache__ inside
# skills/where-were-we/scripts/, which the installer copies verbatim onto the
# user's machine. Suppress bytecode before the path is ever importable.
sys.dont_write_bytecode = True

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "where-were-we" / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Isolate HOME so no test can touch the real session store or ledgers."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("COPILOT_AGENT_SESSION_ID", raising=False)
    return tmp_path


@pytest.fixture
def store(fake_home):
    """A minimal session store with the columns the skill actually reads."""
    path = fake_home / ".copilot" / "session-store.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    # A real ~/.copilot that has a store always has the session-state layout
    # beside it. Creating only the database made the runtime gate report a
    # foreign runtime, which no real Copilot install can be.
    (fake_home / ".copilot" / "session-state").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sessions (id TEXT PRIMARY KEY, cwd TEXT, repository TEXT,
                               branch TEXT, summary TEXT, created_at TEXT,
                               updated_at TEXT);
        CREATE TABLE turns (session_id TEXT, turn_index INTEGER,
                            user_message TEXT, assistant_response TEXT,
                            timestamp TEXT);
        CREATE TABLE checkpoints (session_id TEXT, checkpoint_number INTEGER,
                                  title TEXT, overview TEXT, next_steps TEXT,
                                  important_files TEXT, created_at TEXT);
        CREATE TABLE session_files (session_id TEXT, file_path TEXT,
                                    tool_name TEXT, turn_index INTEGER,
                                    first_seen_at TEXT);
        """
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def seeded(store):
    """Return a helper that inserts turns for a session."""

    def _seed(session_id, count, user="hello", start=0):
        conn = sqlite3.connect(store)
        conn.executemany(
            "INSERT INTO turns (session_id, turn_index, user_message,"
            " assistant_response, timestamp) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    session_id,
                    i,
                    f"{user} {i}",
                    f"reply {i}",
                    f"2026-08-05T00:{i:02d}:00Z",
                )
                for i in range(start, start + count)
            ],
        )
        conn.commit()
        conn.close()

    return _seed


@pytest.fixture
def checkpointed(store):
    """Return a helper that inserts a checkpoint for a session."""

    def _checkpoint(session_id, overview="mid-refactor", next_steps="run migration"):
        conn = sqlite3.connect(store)
        conn.execute(
            "INSERT INTO checkpoints (session_id, checkpoint_number, title,"
            " overview, next_steps, important_files, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, 1, "cp", overview, next_steps, "", "2026-08-05T00:00:00Z"),
        )
        conn.commit()
        conn.close()

    return _checkpoint
