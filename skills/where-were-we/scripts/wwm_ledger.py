# skills/where-were-we/scripts/wwm_ledger.py
"""Ledger schema, parsing, and serialization.

The model never writes this file. All writes go through record() and adopt(),
which own every metadata field including last_synced_turn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

META_KEYS = ("goal", "started", "updated", "last_synced_turn", "adopted_from")
KNOWN_SECTIONS = ("state", "next", "decisions", "threads", "blockers")
HEADING = re.compile(r"^##\s+([a-z_]+)\s*$")
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


def _split_sections(text: str) -> tuple[list[str], dict[str, list[str]]]:
    """Return preamble lines and a map of known section name to its lines.

    Unknown or malformed headings are dropped rather than raising, so a corrupt
    section costs only that section.
    """
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            name = match.group(1)
            current = name if name in KNOWN_SECTIONS else None
            if current:
                sections[current] = []
            continue
        if current is None:
            preamble.append(line)
        else:
            sections[current].append(line)
    return preamble, sections


def parse(text: str) -> Ledger:
    preamble, sections = _split_sections(text)

    meta: dict[str, str] = {}
    for line in preamble:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in META_KEYS:
            meta[key] = value.strip()

    try:
        synced = int(meta.get("last_synced_turn", "0"))
    except ValueError:
        synced = 0
        damaged = ["last_synced_turn"]
    else:
        damaged = []

    parsed: dict[str, object] = {}
    for name, parser in (
        ("decisions", _decisions),
        ("threads", _threads),
        ("blockers", _blockers),
    ):
        try:
            parsed[name] = parser(sections.get(name, []))
        except Exception:
            # Keep every section that parses, record every section that does
            # not. The caller discloses the loss; it is never swallowed.
            parsed[name] = []
            damaged.append(name)

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


def _decisions(lines: list[str]) -> list[Decision]:
    out: list[Decision] = []
    for line in lines:
        match = DECISION.match(line)
        if match:
            out.append(Decision(date=match.group(1), text=match.group(2).strip()))
            continue
        cont = CONTINUATION.match(line)
        if cont and out:
            key, value = cont.group(1), cont.group(2).strip()
            out[-1] = replace(out[-1], **{key: value})
    return out


def _threads(lines: list[str]) -> list[Thread]:
    out: list[Thread] = []
    for line in lines:
        match = THREAD.match(line)
        if match:
            out.append(Thread(done=match.group(1) == "x", text=match.group(2).strip()))
    return out


def _blockers(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped == "(none)":
            continue
        if stripped.startswith("- "):
            out.append(stripped[2:].strip())
    return out


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
