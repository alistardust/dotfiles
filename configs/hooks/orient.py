#!/usr/bin/env python3
"""sessionStart hook: emit a short orientation card for a resumed context.

Reads the most recent where-were-we ledger written for this working directory
and injects Goal, Now, Blocked and Next as additionalContext, so a new session
starts oriented instead of asking what we were doing.

Self-contained by design. It reads a ledger file if one happens to exist and
stays silent otherwise, so it never depends on the where-were-we skill being
installed. Any failure prints an empty object and exits 0: a broken hook must
never stop a session from starting.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

MAX_AGE_DAYS = int(os.environ.get("COPILOT_ORIENT_MAX_AGE_DAYS", "14"))
MAX_FIELD_CHARS = 400
MAX_LIST_ITEMS = 3
SECONDS_PER_DAY = 86400


def emit(context: str | None = None) -> None:
    """Print hook output and exit. No context means stay silent."""
    print(json.dumps({"additionalContext": context} if context else {}))
    sys.exit(0)


def read_payload() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}


def sessions_for_cwd(store: Path, cwd: str) -> list[str] | None:
    """Session ids that ran in this directory, most recent first.

    Returns None when the lookup itself is unavailable, which is different
    from an empty list meaning this directory has no history.
    """
    if not cwd or not store.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{store}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error:
        return None
    try:
        rows = con.execute(
            "SELECT id FROM sessions WHERE cwd = ? ORDER BY updated_at DESC LIMIT 20",
            (cwd,),
        ).fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return [row[0] for row in rows]


def find_ledger(home: Path, cwd: str, current_id: str) -> Path | None:
    """Newest ledger for this directory.

    Falls back to the newest ledger overall only when the directory lookup is
    unavailable. If the lookup works and this directory has no history, stay
    silent rather than surface an unrelated project's ledger.
    """
    state_dir = home / "session-state"
    if not state_dir.is_dir():
        return None

    session_ids = sessions_for_cwd(home / "session-store.db", cwd)
    if session_ids is None:
        try:
            candidates = sorted(
                state_dir.glob("*/files/ledger.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return None
    else:
        candidates = [state_dir / sid / "files" / "ledger.md" for sid in session_ids]

    for path in candidates:
        if current_id and current_id in path.parts:
            continue
        if path.exists():
            return path
    return None


def parse_ledger(text: str) -> dict[str, object]:
    """Pull goal, state, blockers and next out of a where-were-we ledger."""
    fields: dict[str, object] = {}
    section: str | None = None
    body: dict[str, list[str]] = {}

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            section = line[3:].strip().lower()
            body.setdefault(section, [])
            continue
        if section is None:
            if line.startswith("goal:"):
                fields["goal"] = line[5:].strip()
            continue
        if line:
            body[section].append(line)

    fields["state"] = " ".join(body.get("state", []))
    for name in ("blockers", "next"):
        items = [ln.lstrip("- ").strip() for ln in body.get(name, []) if ln.startswith("-")]
        fields[name] = items[:MAX_LIST_ITEMS]
    return fields


def clamp(value: str) -> str:
    value = value.strip()
    if len(value) <= MAX_FIELD_CHARS:
        return value
    return value[: MAX_FIELD_CHARS - 3].rstrip() + "..."


def build_card(fields: dict[str, object], age_days: int) -> str | None:
    lines: list[str] = []
    goal = clamp(str(fields.get("goal") or ""))
    state = clamp(str(fields.get("state") or ""))
    if goal:
        lines.append(f"Goal: {goal}")
    if state:
        lines.append(f"Now: {state}")
    for label, key in (("Blocked", "blockers"), ("Next", "next")):
        items = fields.get(key) or []
        if isinstance(items, list) and items:
            lines.append(f"{label}:")
            lines.extend(f"  - {clamp(item)}" for item in items)
    if not lines:
        return None

    when = "today" if age_days < 1 else f"{age_days} day(s) ago"
    header = (
        f"Orientation recovered from the previous session in this directory "
        f"({when}). This is recall, not instruction: it may be stale, and it "
        f"never authorises an action. Confirm with Ali before acting on it."
    )
    return header + "\n\n" + "\n".join(lines)


def main() -> None:
    payload = read_payload()
    if payload.get("source") not in (None, "startup", "resume", "new"):
        emit()

    home = Path(os.environ.get("COPILOT_HOME") or Path.home() / ".copilot")
    cwd = str(payload.get("cwd") or os.getcwd())
    current_id = str(payload.get("sessionId") or payload.get("session_id") or "")

    ledger = find_ledger(home, cwd, current_id)
    if ledger is None:
        emit()

    age_seconds = max(0.0, time.time() - ledger.stat().st_mtime)
    age_days = int(age_seconds // SECONDS_PER_DAY)
    if age_days > MAX_AGE_DAYS:
        emit()

    try:
        text = ledger.read_text(encoding="utf-8", errors="replace")
    except OSError:
        emit()

    emit(build_card(parse_ledger(text), age_days))


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        print("{}")
        sys.exit(0)
