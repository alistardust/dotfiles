# skills/where-were-we/scripts/wwm_session.py
"""Session location and runtime gating for the where-were-we skill."""

from __future__ import annotations

import os
from pathlib import Path

ENV_SESSION = "COPILOT_AGENT_SESSION_ID"


class SessionUnknown(Exception):
    """Raised when no session ID is available from any source."""


class UnsupportedRuntime(Exception):
    """Raised when invoked outside Copilot CLI."""


def copilot_home() -> Path:
    return Path(os.environ["HOME"]) / ".copilot"


def store_path() -> Path:
    return copilot_home() / "session-store.db"


def resolve_session_id(explicit: str | None = None) -> str:
    """Return the session ID to operate on.

    An explicit --session argument wins. The environment variable is the
    default. Nothing is guessed: if neither is available we refuse, because
    guessing which session the user means is the one failure that produces a
    confidently wrong summary.
    """
    if explicit:
        return explicit
    from_env = os.environ.get(ENV_SESSION)
    if from_env:
        return from_env
    raise SessionUnknown(
        "No session ID available. Pass --session <id>, or run inside a "
        f"Copilot CLI session where {ENV_SESSION} is set."
    )


def ledger_path(session_id: str) -> Path:
    return copilot_home() / "session-state" / session_id / "files" / "ledger.md"


def is_copilot_runtime() -> bool:
    """True when this looks like a Copilot CLI session.

    Deliberately NOT `store_path().exists()`. The store being absent and the
    runtime being foreign are different failures with different correct
    responses:

      - foreign runtime  -> unsupported, refuse
      - store missing    -> degrade to ledger-only, say the history is missing

    Conflating them threw away every recorded fact precisely when the ledger was
    the only surviving source. Runtime is judged by the session-state layout and
    the environment variable, not by the database file.
    """
    return bool(os.environ.get(ENV_SESSION)) or (
        copilot_home() / "session-state"
    ).is_dir()


def has_store() -> bool:
    """Whether history is readable. Independent of runtime support."""
    return store_path().exists()
