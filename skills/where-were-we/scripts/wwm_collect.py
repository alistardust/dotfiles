"""Locate, reconcile, deduplicate, and fall back within budget.

Produces the structured bundle the model judges and the renderer formats. This
module decides what is true and where it came from; it never decides how it
looks.
"""

from __future__ import annotations

import re

import wwm_history
import wwm_ledger
import wwm_session

STOPWORDS = {
    "the",
    "a",
    "an",
    "to",
    "of",
    "and",
    "or",
    "for",
    "we",
    "i",
    "it",
    "is",
    "on",
    "in",
    "that",
    "this",
    "with",
    "be",
    "as",
    "at",
    "so",
    "but",
}


def _fingerprint(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(w for w in words if w not in STOPWORDS and len(w) > 2)


def _same_event(a: str, b: str, threshold: float = 0.6) -> bool:
    """Cheap overlap test.

    Deliberately not fuzzy string matching: the goal is to catch a decision
    echoing its own turn, not to cluster unrelated topics. A false negative
    shows one extra line; a false positive hides real content, so the threshold
    errs high.
    """
    fa, fb = _fingerprint(a), _fingerprint(b)
    if not fa or not fb:
        return False
    overlap = len(fa & fb) / min(len(fa), len(fb))
    return overlap >= threshold


def _recorded_items(led: wwm_ledger.Ledger) -> list[dict]:
    """Everything the user explicitly recorded, all tagged `rec`."""
    items: list[dict] = []
    for dec in led.decisions:
        items.append(
            {
                "label": "Decided",
                "text": dec.text,
                "why": dec.why,
                "rejected": dec.rejected,
                "source": "rec",
                "date": dec.date,
            }
        )
    for thread in led.threads:
        if not thread.done:
            items.append({"label": "Thread", "text": thread.text, "source": "rec"})
    for blocker in led.blockers:
        items.append({"label": "Blocked", "text": blocker, "source": "rec"})
    if led.next:
        items.append({"label": "Next", "text": led.next, "source": "rec"})
    if led.state:
        items.append({"label": "State", "text": led.state, "source": "rec"})
    return items


def collect(session_id: str) -> dict:
    led = wwm_ledger.load(session_id)

    # The store being unreadable is a degraded mode, not a fatal error. Every
    # recorded fact in the ledger is still valid and still worth showing; we
    # just say plainly that the history half is missing.
    store_ok = wwm_session.has_store()
    store_max = wwm_history.max_turn_index(session_id) if store_ok else 0

    items = _recorded_items(led)

    # A marker at or beyond the store is stale, not current. It can only mean an
    # unflushed turn or a tampered file; either way, reconcile from what the
    # store actually confirms rather than trusting the claim.
    #
    # With no store there is nothing to compare against, so staleness is simply
    # unknowable. Claiming "newer turns folded in below" when zero turns were
    # folded in points the reader at content that is not there, which is a
    # worse failure than staying quiet.
    stale = False
    if store_ok:
        stale = bool(led.decisions or led.state) and led.last_synced_turn < store_max
        if led.last_synced_turn > store_max:
            stale = True

    # Fetch the checkpoint first so any unspent allowance can be handed to the
    # turn slices. 44% of sessions have no checkpoint; for those, reserving
    # 2500 chars for a row that does not exist would throw away the only
    # evidence the skill actually has.
    checkpoint = wwm_history.latest_checkpoint(session_id) if store_ok else None
    spare = wwm_history.BUDGET_CHECKPOINT - (checkpoint["spent"] if checkpoint else 0)
    turn_budget = wwm_history.BUDGET_RECENT + max(0, spare)

    # Branch on whether a ledger exists at all, NOT on whether `newer` came back
    # empty. `turns_after(after=0)` sorts ASC, so on a session with no ledger it
    # happily returns the OLDEST turns and is therefore always truthy. Keying
    # the fallback off `not newer` meant a 461-turn session answered "where were
    # we" with turns 1-29. Verified against the real store.
    has_ledger = bool(led.decisions or led.state or led.goal or led.next)

    if not store_ok:
        newer = []
    elif has_ledger:
        newer = wwm_history.turns_after(
            session_id,
            after=min(led.last_synced_turn, store_max),
            budget=turn_budget,
        )
    else:
        newer = wwm_history.recent_turns(session_id, budget=turn_budget)

    recorded_texts = [i["text"] for i in items]
    for turn in newer:
        if any(_same_event(turn["text"], rec) for rec in recorded_texts):
            continue
        items.append(
            {
                "label": "Discussed",
                "text": turn["text"],
                "source": "inf",
                "turn_index": turn["turn_index"],
            }
        )

    if checkpoint and not led.state:
        items.append(
            {"label": "State", "text": checkpoint["overview"], "source": "inf"}
        )
        if checkpoint["next_steps"] and not led.next:
            items.append(
                {"label": "Next", "text": checkpoint["next_steps"], "source": "inf"}
            )

    origin = wwm_history.earliest_turns(session_id) if store_ok else []

    return {
        "session_id": session_id,
        "goal": led.goal,
        "adopted_from": led.adopted_from,
        "origin": origin,
        "items": items,
        "files": wwm_history.session_files(session_id) if store_ok else [],
        "stale": stale,
        "has_ledger": has_ledger,
        "has_history": store_ok,
        "ledger_damaged": led.damaged,
        "insufficient": not items and not origin,
    }
