# skills/where-were-we/scripts/wwm_render.py
"""Exact 72-character rendering.

Every visual guarantee lives here and nowhere else. The model contributes prose
but never formatting, because format consistency is what lets the eye find
`Next` without re-reading.
"""

from __future__ import annotations

import re
import textwrap

TOTAL = 72
INDENT = 2
LABEL_W = 9
TEXT_COL = INDENT + LABEL_W + 1
TEXT_W = TOTAL - TEXT_COL
TAG_W = 5
TIGHT_W = TEXT_W - TAG_W - 1
MENU = "more? [decisions] [threads] [timeline] [files] [full]"


def _wrap(text: str, width: int) -> list[str]:
    wrapped = textwrap.wrap(
        text,
        width=width,
        break_long_words=True,
        break_on_hyphens=False,
    )
    return wrapped or [""]


def _clean(text: str) -> str:
    """Strip markdown noise before wrapping.

    Checkpoint and turn text is written for a markdown renderer, so it arrives
    full of `**`, backticks, and bullet leaders. Inside a fixed-width label
    block none of that renders; it just costs characters and adds visual noise
    to something whose entire purpose is being easy to scan.
    """
    text = re.sub(r"`+", "", str(text))
    text = re.sub(r"\*{1,3}", "", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    return " ".join(text.split())


def row(label: str, text: str, tag: str) -> list[str]:
    """Render one labeled row with its source tag right-aligned to column 72.

    Args:
        label: Short row label, truncated to the label column width.
        text: Body text. Markdown noise is stripped before wrapping.
        tag: Provenance marker, rendered as `[tag]` at the far right.

    Returns:
        Lines that are each at most TOTAL characters wide.
    """
    marker = f"[{tag}]"
    text = _clean(text)

    lines = _wrap(text, TEXT_W)
    if len(lines[-1]) + 1 + TAG_W > TEXT_W:
        lines = _wrap(text, TIGHT_W)

    out: list[str] = []
    head = f"{' ' * INDENT}{label[:LABEL_W].ljust(LABEL_W)} "
    for index, line in enumerate(lines):
        prefix = head if index == 0 else " " * TEXT_COL
        out.append(prefix + line)

    last = out[-1]
    if len(last) + 1 + TAG_W <= TOTAL:
        out[-1] = last.ljust(TOTAL - TAG_W) + marker
    else:
        out.append(" " * (TOTAL - TAG_W) + marker)
    return out


LEVELS = ("tldr", "summary", "full")
SECTIONS = {
    "decisions": ("Decided",),
    "threads": ("Thread",),
    "timeline": ("Discussed", "Direction"),
    "files": ("Files",),
    "blockers": ("Blocked",),
}
TLDR_PRIORITY = (
    "Decided",
    "Next",
    "State",
    "Blocked",
    "Thread",
    # Recorded labels win, but history-only labels MUST remain eligible.
    # Omitting them rendered an empty tldr (prose plus menu, zero facts) for
    # every session with no ledger and no checkpoint, which is precisely the
    # case the history fallback exists to serve.
    "Discussed",
    "Direction",
)
TLDR_MAX_LINES = 8
PROSE_MAX_LINES = 2
ITEM_MAX_LINES = 2


class UnknownSection(Exception):
    """Raised when a section name does not exist. Never guessed."""


def _prose_lines(prose: str, cap: int = PROSE_MAX_LINES) -> list[str]:
    """Wrap the prose opening and cap it.

    The cap exists because prose competes with the label block for the same 8
    lines, and the label block is the part that carries sourced facts. A
    runaway sentence must lose, not the evidence.
    """
    prose = " ".join(str(prose).split())
    if not prose:
        return []
    wrapped = textwrap.wrap(prose, width=TOTAL)
    if len(wrapped) > cap:
        wrapped = wrapped[:cap]
        wrapped[-1] = wrapped[-1][: TOTAL - 3].rstrip() + "..."
    return wrapped + [""]


def _fit(item: dict, budget: int) -> list[str]:
    """Render one item shortened to fit `budget` lines. Never returns empty."""
    text = item["text"]
    while text:
        rendered = row(item["label"], text, item["source"])
        if len(rendered) <= budget:
            return rendered
        text = text[: max(0, len(text) - max(8, len(text) // 8))].rstrip()
        if len(text) > 3:
            text = text[:-3].rstrip() + "..."
    return row(item["label"], "...", item["source"])[:budget]


def _select(items: list[dict], level: str, section: str | None) -> list[dict]:
    if section is not None:
        if section not in SECTIONS:
            raise UnknownSection(
                f"No section named '{section}'. Known: {', '.join(sorted(SECTIONS))}"
            )
        wanted = SECTIONS[section]
        return [i for i in items if i["label"] in wanted]
    if level == "full":
        return items
    if level == "summary":
        return items[:12]
    ordered: list[dict] = []
    for label in TLDR_PRIORITY:
        ordered += [i for i in items if i["label"] == label]
    return ordered


def render(
    bundle: dict,
    level: str = "tldr",
    section: str | None = None,
    prose: str = "",
) -> str:
    """Assemble the final fixed-width output.

    Args:
        bundle: Collected session facts.
        level: One of LEVELS.
        section: Optional single section to render alone.
        prose: Optional opening sentence, bounded by PROSE_MAX_LINES.

    Returns:
        The rendered block, every line at most TOTAL characters.

    Raises:
        ValueError: If `level` is not a known level.
        UnknownSection: If `section` is not a known section.
    """
    if level not in LEVELS:
        raise ValueError(f"unknown level: {level}")

    if bundle.get("insufficient"):
        return (
            "Not enough here to tell you where we were. No ledger entries and\n"
            "no usable history for this session."
        )

    lines = _prose_lines(prose)

    notes: list[str] = []
    if bundle.get("adopted_from"):
        notes.append(f"  (ledger adopted from session {bundle['adopted_from'][:8]})")
    if bundle.get("stale"):
        notes.append("  (ledger was behind; newer turns folded in below)")
    if bundle.get("has_history") is False:
        notes.append("  (session history unreadable; recorded notes only)")
    if bundle.get("ledger_damaged"):
        damaged = ", ".join(bundle["ledger_damaged"])
        notes.append(f"  (unreadable in ledger: {damaged})")
    if notes:
        lines += notes
        lines.append("")

    selected = _select(bundle["items"], level, section)

    # Subtract two, not one: the blank line before the menu counts. Verified by
    # running it; the naive arithmetic yields 9 lines, not 8.
    budget = (
        TLDR_MAX_LINES - len(lines) - 2 if level == "tldr" and section is None else None
    )
    body: list[str] = []
    omitted = 0
    # In the tldr, cap how tall any single item may be. Without this, one long
    # checkpoint `next_steps` consumes the entire budget and the summary becomes
    # a single truncated paragraph, which is the wall-of-text failure this skill
    # exists to prevent. Verified against the live session: uncapped, one item
    # took all four available lines and hid twelve others.
    per_item = ITEM_MAX_LINES if (level == "tldr" and section is None) else None
    for item in selected:
        rendered = row(item["label"], item["text"], item["source"])
        if per_item is not None and len(rendered) > per_item:
            rendered = _fit(item, per_item)
        if budget is not None and len(body) + len(rendered) > budget:
            # Never return a tldr with zero facts. An empty body looks like a
            # confident answer and carries nothing, which is the worst possible
            # failure for a memory aid. If the very first item cannot fit, cut
            # the item's text down until it does rather than dropping it.
            if not body and budget > 0:
                rendered = _fit(item, budget)
                body += rendered
                omitted = max(0, len(selected) - 1)
                break
            omitted = len(selected) - selected.index(item)
            break
        body += rendered
        if level == "full" and item.get("why"):
            body += row("why", item["why"], item["source"])
        if level == "full" and item.get("rejected"):
            body += row("rejected", item["rejected"], item["source"])

    lines += body

    if section == "files" or level == "full":
        for path in bundle.get("files", []):
            lines += row("Files", path, "inf")

    lines.append("")
    # Say what was left out. Silent truncation makes an incomplete answer look
    # complete, which the spec forbids.
    lines.append(f"+{omitted} more. {MENU}" if omitted else MENU)
    return "\n".join(line.rstrip() for line in lines).strip("\n")
