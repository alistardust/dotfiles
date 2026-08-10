# skills/where-were-we/scripts/wwm_ledger.py
"""Ledger schema, parsing, and serialization.

The model never writes this file. All writes go through record() and adopt(),
which own every metadata field including last_synced_turn.
"""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

import wwm_session

META_KEYS = ("goal", "started", "updated", "last_synced_turn", "adopted_from")
KNOWN_SECTIONS = ("state", "next", "decisions", "threads", "blockers")
HEADING = re.compile(r"^##\s+(.+?)\s*$")
DECISION = re.compile(r"^-\s+(\d{4}-\d{2}-\d{2})\s+(.*)$")
THREAD = re.compile(r"^-\s+\[( |x)\]\s+(.*)$")
CONTINUATION = re.compile(r"^\s+(why|rejected):\s*(.*)$")


@dataclass(frozen=True)
class Decision:
    date: str
    text: str
    why: str = ""
    rejected: str = ""


@dataclass(frozen=True)
class Thread:
    done: bool
    text: str


@dataclass(frozen=True)
class Ledger:
    goal: str | None = None
    started: str | None = None
    updated: str | None = None
    last_synced_turn: int = 0
    adopted_from: str | None = None
    state: str | None = None
    next: str | None = None
    decisions: list[Decision] = field(default_factory=list)
    threads: list[Thread] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    # Names of sections that failed to parse. The spec requires that a damaged
    # ledger be used for what survives AND that the loss be stated. Dropping
    # sections silently turns corruption into an answer that looks whole.
    damaged: list[str] = field(default_factory=list)


def _split_sections(text: str) -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Return preamble lines, known sections, and unreadable heading names.

    Headings are matched loosely and compared case-insensitively, so a
    hand-edited `## Decisions` still lands in the decisions section. A heading
    that is genuinely not understood does not silently swallow the lines under
    it: those lines are discarded and the heading name is returned so the
    caller can disclose the loss.
    """
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    unknown: list[str] = []
    current: str | None = None
    orphan: str | None = None
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            name = match.group(1).strip().lower()
            if name in KNOWN_SECTIONS:
                current = name
                # Merge rather than reset. A duplicated heading used to drop
                # everything above it without a word.
                sections.setdefault(current, [])
                orphan = None
            else:
                current = None
                orphan = name
            continue
        if orphan is not None:
            if line.strip() and orphan not in unknown:
                unknown.append(orphan)
            continue
        if current is None:
            preamble.append(line)
        else:
            sections[current].append(line)
    return preamble, sections, unknown


def parse(text: str) -> Ledger:
    preamble, sections, unknown = _split_sections(text)

    meta: dict[str, str] = {}
    # A key: value line the parser does not recognise is almost always a typo
    # for one that it does ("gola:" for "goal:"). Skipping it quietly loses
    # whatever the user wrote, so an unrecognised key is disclosed by name and
    # they can see what to correct. Same rule as decisions, threads and
    # headings: nothing readable is discarded without saying so.
    bad_keys: list[str] = []
    for line in preamble:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in META_KEYS:
            meta[key] = value.strip()
        elif key and " " not in key and not key.startswith("#"):
            bad_keys.append(key)

    try:
        synced = int(meta.get("last_synced_turn", "0"))
    except ValueError:
        synced = 0
        damaged = ["last_synced_turn"]
    else:
        damaged = []
    damaged += bad_keys

    parsed: dict[str, object] = {}
    for name, parser in (
        ("decisions", _decisions),
        ("threads", _threads),
        ("blockers", _blockers),
    ):
        try:
            result, dropped = parser(sections.get(name, []))
        except Exception:  # noqa: BLE001 - see below
            # Deliberately blind. The ledger is the last surviving record of
            # intent when the store is gone, so no parse failure may take the
            # whole file down with it. This is not a silent swallow: the
            # section name lands in `damaged` and the renderer tells the user
            # what it could not read.
            parsed[name] = []
            damaged.append(name)
        else:
            # A section can parse and still lose individual lines to a typo.
            # Dropping those silently is the same data loss wearing a
            # friendlier face, so a partial read is disclosed as damaged too.
            parsed[name] = result
            if dropped:
                damaged.append(name)

    damaged.extend(unknown)

    return Ledger(
        goal=meta.get("goal"),
        started=meta.get("started"),
        updated=meta.get("updated"),
        last_synced_turn=max(0, synced),
        adopted_from=meta.get("adopted_from"),
        state=_block(sections.get("state")),
        next=_block(sections.get("next")),
        decisions=parsed["decisions"],
        threads=parsed["threads"],
        blockers=parsed["blockers"],
        damaged=damaged,
    )


def _block(lines: list[str] | None) -> str | None:
    if lines is None:
        return None
    text = "\n".join(lines).strip()
    return text or None


def _decisions(lines: list[str]) -> tuple[list[Decision], bool]:
    out: list[Decision] = []
    dropped = False
    for line in lines:
        if not line.strip():
            continue
        match = DECISION.match(line)
        if match:
            out.append(Decision(date=match.group(1), text=match.group(2).strip()))
            continue
        cont = CONTINUATION.match(line)
        if cont and out:
            key, value = cont.group(1), cont.group(2).strip()
            out[-1] = replace(out[-1], **{key: value})
            continue
        dropped = True
    return out, dropped


def _threads(lines: list[str]) -> tuple[list[Thread], bool]:
    out: list[Thread] = []
    dropped = False
    for line in lines:
        if not line.strip():
            continue
        match = THREAD.match(line)
        if match:
            out.append(Thread(done=match.group(1) == "x", text=match.group(2).strip()))
            continue
        dropped = True
    return out, dropped


def _blockers(lines: list[str]) -> tuple[list[str], bool]:
    out: list[str] = []
    dropped = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped == "(none)":
            continue
        if stripped.startswith("- "):
            out.append(stripped[2:].strip())
            continue
        dropped = True
    return out, dropped


def serialize(led: Ledger) -> str:
    parts = ["# where-were-we", ""]
    for key in META_KEYS:
        value = getattr(led, key)
        if value is None:
            continue
        if key == "last_synced_turn" and not value:
            value = 0
        parts.append(f"{key}: {value}")
    parts.append("")

    if led.state:
        parts += ["## state", led.state, ""]
    if led.next:
        parts += ["## next", led.next, ""]

    parts.append("## decisions")
    for dec in led.decisions:
        parts.append(f"- {dec.date} {dec.text}")
        if dec.why:
            parts.append(f"  why: {dec.why}")
        if dec.rejected:
            parts.append(f"  rejected: {dec.rejected}")
    parts.append("")

    parts.append("## threads")
    for thread in led.threads:
        box = "x" if thread.done else " "
        parts.append(f"- [{box}] {thread.text}")
    parts.append("")

    parts.append("## blockers")
    parts += [f"- {b}" for b in led.blockers] if led.blockers else ["(none)"]
    parts.append("")
    return "\n".join(parts)


def load(session_id: str) -> Ledger:
    """Read and parse a session ledger, tolerating a missing or unreadable file.

    Args:
        session_id: The session whose ledger to read.

    Returns:
        The parsed ledger, or an empty Ledger when no readable ledger exists.
    """
    path = wwm_session.ledger_path(session_id)
    if not path.exists():
        return Ledger()
    try:
        return parse(path.read_text(encoding="utf-8"))
    except OSError:
        return Ledger()


def _max_turn_index(session_id: str) -> int:
    """Return the highest committed turn index, or 0 when none is readable.

    Read straight from the store so record() stamps last_synced_turn from
    reality rather than from any caller-supplied value. The connection is
    read-only by URI so a bug here cannot corrupt session history, and it is
    wrapped in contextlib.closing because a bare sqlite3.connect context manager
    commits without closing and would leak the handle.
    """
    path = wwm_session.store_path()
    if not path.exists():
        return 0
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
            row = conn.execute(
                "SELECT MAX(turn_index) AS m FROM turns WHERE session_id = ?",
                (session_id,),
            ).fetchone()
    except sqlite3.Error:
        return 0
    return row[0] or 0


def _today() -> str:
    """Return today's date as an ISO (YYYY-MM-DD) string.

    Uses a timezone-aware UTC clock so the stamp is deterministic and
    unambiguous across machines and timezones.
    """
    return datetime.now(tz=timezone.utc).date().isoformat()


def _atomic_write(path: Path, text: str) -> None:
    """Write text to path atomically, never truncating an existing file.

    The content lands in a sibling temp file first and is moved into place with
    a single os.replace, so a crash mid-write leaves the previous ledger intact.

    The temp name is unique per call. A fixed `.tmp` suffix races when two
    processes record against the same session at once, which is routine here:
    a subagent and its parent both hold the same session id, so the first
    rename pulls the file out from under the second and it dies with
    FileNotFoundError.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def record(
    session_id: str,
    kind: str,
    text: str,
    why: str = "",
    rejected: str = "",
    **ignored: object,
) -> Ledger:
    """Append one milestone to the ledger and re-stamp sync metadata.

    Args:
        session_id: The session whose ledger to update.
        kind: One of decision, thread, blocker, state, next, or goal.
        text: The milestone content.
        why: Rationale, recorded only for decisions.
        rejected: Rejected alternatives, recorded only for decisions.
        **ignored: Absorbs any extra keyword arguments so a caller passing
            last_synced_turn cannot set it. The value is read from the store,
            never accepted, because the model has no reliable way to know its
            own turn index and a value that runs ahead of reality would suppress
            real turns.

    Returns:
        The updated ledger that was written to disk.

    Raises:
        ValueError: If kind is not a recognized milestone type.
    """
    led = load(session_id)
    today = _today()

    if kind == "decision":
        led = replace(
            led,
            decisions=[*led.decisions, Decision(today, text, why, rejected)],
        )
    elif kind == "thread":
        led = replace(led, threads=[*led.threads, Thread(False, text)])
    elif kind == "blocker":
        led = replace(led, blockers=[*led.blockers, text])
    elif kind == "state":
        led = replace(led, state=text)
    elif kind == "next":
        led = replace(led, next=text)
    elif kind == "goal":
        led = replace(led, goal=text)
    else:
        raise ValueError(f"unknown kind: {kind}")

    led = replace(
        led,
        started=led.started or today,
        updated=today,
        last_synced_turn=_max_turn_index(session_id),
    )
    _atomic_write(wwm_session.ledger_path(session_id), serialize(led))
    return led


def adopt(source: str, target: str) -> Ledger:
    """Carry a stranded ledger into the current session.

    Content transfers. Sync state does not: turn_index is per-session, so an
    inherited last_synced_turn is meaningless here and, if it ran high, would
    mark the new ledger current and hide every real turn in it.

    Args:
        source: The session whose ledger content is being carried over.
        target: The current session that adopts the content.

    Returns:
        The adopted ledger that was written to the target session.
    """
    src = load(source)
    adopted = replace(
        src,
        adopted_from=source,
        last_synced_turn=0,
        updated=_today(),
    )
    _atomic_write(wwm_session.ledger_path(target), serialize(adopted))
    return adopted
