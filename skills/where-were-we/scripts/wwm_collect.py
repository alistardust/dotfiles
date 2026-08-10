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
    items = _recorded_items(led)

    # Branch on whether a ledger exists at all, NOT on whether `newer` came back
    # empty. `turns_after(after=0)` sorts ASC, so on a session with no ledger it
    # happily returns the OLDEST turns and is therefore always truthy. Keying
    # the fallback off `not newer` meant a 461-turn session answered "where were
    # we" with turns 1-29. Verified against the real store.
    #
    # Threads and blockers count. Omitting them meant a ledger holding only an
    # open thread was treated as no ledger at all, which threw away its own
    # last_synced_turn boundary and replayed history the user had already seen.
    has_ledger = bool(
        led.decisions
        or led.state
        or led.goal
        or led.next
        or led.threads
        or led.blockers
    )

    # A file being present is not the same as a readable database: sqlite only
    # reports a truncated, empty or foreign file once a statement actually runs.
    # So every store read sits inside one degradation boundary, and the store is
    # only trusted after it has answered. Losing history is a degraded mode, not
    # a fatal error. Every recorded fact in the ledger is still valid and still
    # worth showing; we just say plainly that the history half is missing.
    store_ok = wwm_session.has_store()
    store_max = 0
    checkpoint = None
    newer: list[dict] = []
    origin: list[dict] = []
    files: list[str] = []
    if store_ok:
        try:
            store_max = wwm_history.max_turn_index(session_id)

            # Fetch the checkpoint first so any unspent allowance can be handed
            # to the turn slices. 44% of sessions have no checkpoint; for those,
            # reserving 2500 chars for a row that does not exist would throw
            # away the only evidence the skill actually has.
            checkpoint = wwm_history.latest_checkpoint(session_id)
            spent = checkpoint["spent"] if checkpoint else 0
            turn_budget = wwm_history.BUDGET_RECENT + max(
                0, wwm_history.BUDGET_CHECKPOINT - spent
            )

            if has_ledger:
                newer = wwm_history.turns_after(
                    session_id,
                    after=min(led.last_synced_turn, store_max),
                    budget=turn_budget,
                )
            else:
                newer = wwm_history.recent_turns(session_id, budget=turn_budget)

            origin = wwm_history.earliest_turns(session_id)
            files = wwm_history.session_files(session_id)
        except wwm_history.StoreUnavailable:
            store_ok = False
            store_max = 0
            checkpoint = None
            newer = []
            origin = []
            files = []

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

    return {
        "session_id": session_id,
        "goal": led.goal,
        "adopted_from": led.adopted_from,
        "origin": origin,
        "items": items,
        "files": files,
        "stale": stale,
        "has_ledger": has_ledger,
        "has_history": store_ok,
        "ledger_damaged": led.damaged,
        "insufficient": not items and not origin,
    }
