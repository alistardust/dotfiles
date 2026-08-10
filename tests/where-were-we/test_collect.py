# tests/where-were-we/test_collect.py
import wwm_collect
import wwm_ledger
import wwm_render
import wwm_session


def test_ledger_content_is_labeled_recorded(fake_home, seeded):
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="decision", text="Chose Python")
    bundle = wwm_collect.collect("s1")
    decided = [i for i in bundle["items"] if i["label"] == "Decided"]
    assert decided and all(i["source"] == "rec" for i in decided)


def test_history_never_produces_decided(fake_home, seeded):
    seeded("s1", 8, user="maybe we should switch to Rust, or maybe not")
    bundle = wwm_collect.collect("s1")
    assert all(i["label"] != "Decided" for i in bundle["items"])
    assert all(i["source"] == "inf" for i in bundle["items"])


def test_no_ledger_falls_back_to_the_NEWEST_turns(fake_home, seeded):
    """Regression, CRITICAL. The fallback used to key off `not newer`, but
    `turns_after(after=0)` sorts ASC and therefore always returns the OLDEST
    turns, making `newer` truthy and skipping the recent-turns path entirely.
    Verified against the real store: a 461-turn session answered "where were
    we" with turns 1-29."""
    seeded("s1", 60)
    bundle = wwm_collect.collect("s1")
    assert bundle["has_ledger"] is False
    # Scoped to the fallback slice. `Started` is turn 0 by design, promoted
    # deliberately as an orienting row, so including it here would mask the
    # very regression this test exists to catch.
    used = [
        i["turn_index"]
        for i in bundle["items"]
        if "turn_index" in i and i["label"] != "Started"
    ]
    assert used, "fallback produced no turns at all"
    assert max(used) == 59, "fallback must reach the end of the session"
    assert min(used) > 30, f"fallback returned early turns: {min(used)}"
    started = [i for i in bundle["items"] if i["label"] == "Started"]
    assert len(started) == 1 and started[0]["turn_index"] == 0


def test_missing_store_degrades_to_ledger_and_says_so(fake_home, seeded):
    seeded("s1", 4)
    wwm_ledger.record("s1", kind="decision", text="Chose Python")
    (fake_home / ".copilot" / "session-store.db").unlink()
    bundle = wwm_collect.collect("s1")
    assert bundle["has_history"] is False
    # The recorded fact survives; only the history half is gone.
    assert any(i["label"] == "Decided" for i in bundle["items"])
    out = wwm_render.render(bundle, level="tldr", prose="")
    assert "history unreadable" in out


def test_stale_ledger_does_not_hide_newer_turns(fake_home, seeded):
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="decision", text="early call")
    seeded("s1", 5, user="much later work", start=3)
    bundle = wwm_collect.collect("s1")
    assert bundle["stale"] is True
    assert any("much later work" in i["text"] for i in bundle["items"])


def test_recorded_and_inferred_same_event_render_once(fake_home, seeded):
    """The flush-lag finding: the turn that recorded a decision reappears."""
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="decision", text="use reserved budget slices")
    seeded("s1", 1, user="use reserved budget slices", start=3)
    bundle = wwm_collect.collect("s1")
    matches = [i for i in bundle["items"] if "reserved budget slices" in i["text"]]
    assert len(matches) == 1
    assert matches[0]["source"] == "rec"


def test_sync_marker_ahead_of_store_is_treated_as_stale(fake_home, seeded):
    seeded("s1", 4)
    path = __import__("wwm_session").ledger_path("s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# where-were-we\n\nlast_synced_turn: 999\n")
    bundle = wwm_collect.collect("s1")
    assert bundle["stale"] is True
    assert bundle["items"], "must reconcile from what the store confirms"


def test_empty_session_says_so_rather_than_inventing(fake_home, store):
    bundle = wwm_collect.collect("s1")
    assert bundle["items"] == []
    assert bundle["insufficient"] is True


def test_pivot_is_surfaced_when_origin_and_now_diverge(fake_home, seeded):
    """The name promised a surfaced pivot but the assertion only checked that
    the origin slice was fetched. `origin` was collected and then dropped by
    every renderer, so this passed while the pivot was invisible."""
    seeded("s1", 1, user="set up CI for the repo")
    seeded("s1", 12, user="rewrite the search indexer", start=1)
    bundle = wwm_collect.collect("s1")
    started = [i for i in bundle["items"] if i["label"] == "Started"]
    assert len(started) == 1, "the session's opening must be surfaced"
    assert "CI" in started[0]["text"]


def test_total_budget_is_never_exceeded(fake_home, seeded):
    seeded("s1", 200, user="q" * 5000)
    bundle = wwm_collect.collect("s1")
    spent = sum(len(i["text"]) for i in bundle["items"])
    spent += sum(len(t["text"]) for t in bundle["origin"])
    assert spent <= wwm_collect.wwm_history.BUDGET_TOTAL


def test_checkpoint_spare_is_donated_when_no_checkpoint_exists(fake_home, seeded):
    """A session with no checkpoint must not lose 2500 chars of turn budget."""
    seeded("s1", 40, user="x" * 400)
    bundle = wwm_collect.collect("s1")
    turn_chars = sum(len(i["text"]) for i in bundle["items"] if "turn_index" in i)
    assert turn_chars > wwm_history_budget_recent(), (
        "unspent checkpoint allowance was not donated to the turn slice"
    )


def wwm_history_budget_recent():
    import wwm_history

    return wwm_history.BUDGET_RECENT


def test_damaged_ledger_section_is_reported_in_the_bundle(fake_home, seeded):
    seeded("s1", 2)
    path = __import__("wwm_session").ledger_path("s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# where-were-we\n\nlast_synced_turn: 1\n\n"
        "## Decisions\nthis line has no leading dash so it is dropped\n"
    )
    bundle = wwm_collect.collect("s1")
    assert bundle["ledger_damaged"], "silent loss must be disclosed, not hidden"


def test_files_are_omitted_rather_than_faked_when_store_is_gone(fake_home, seeded):
    seeded("s1", 2)
    wwm_ledger.record("s1", kind="state", text="mid-refactor")
    (fake_home / ".copilot" / "session-store.db").unlink()
    bundle = wwm_collect.collect("s1")
    assert bundle["files"] == []
    assert bundle["origin"] == []


def test_no_store_does_not_claim_the_ledger_is_stale(fake_home, seeded):
    """Regression, found end-to-end. With no store, store_max fell back to 0,
    so any ledger looked "behind" and the render told the reader that newer
    turns had been folded in below when nothing had. Pointing someone at
    content that is not there is worse than saying nothing."""
    seeded("s1", 40)
    wwm_ledger.record("s1", kind="decision", text="chose python")
    (fake_home / ".copilot" / "session-store.db").unlink()
    bundle = wwm_collect.collect("s1")
    assert bundle["stale"] is False
    out = wwm_render.render(bundle, level="tldr", prose="")
    assert "folded in below" not in out
    assert "history unreadable" in out


def test_every_recordable_kind_reaches_the_bundle_as_recorded(fake_home, seeded):
    """Coverage gap found at the quality gate. Every collect test recorded a
    decision, so four of the six documented kinds had never been exercised
    through collect at all: a `record --kind thread` that silently failed to
    surface would have shipped."""
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="decision", text="chose python")
    wwm_ledger.record("s1", kind="thread", text="retry logic still open")
    wwm_ledger.record("s1", kind="blocker", text="waiting on vendor")
    wwm_ledger.record("s1", kind="next", text="wire up the parser")
    wwm_ledger.record("s1", kind="state", text="halfway through the rewrite")

    bundle = wwm_collect.collect("s1")
    by_label = {i["label"]: i for i in bundle["items"]}
    for label in ("Decided", "Thread", "Blocked", "Next", "State"):
        assert label in by_label, f"{label} never reached the bundle"
        assert by_label[label]["source"] == "rec", f"{label} lost its rec tag"
    assert "retry logic still open" in by_label["Thread"]["text"]
    assert "waiting on vendor" in by_label["Blocked"]["text"]


def test_a_finished_thread_is_not_shown_as_open(fake_home, seeded):
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="thread", text="done and dusted")
    path = __import__("wwm_session").ledger_path("s1")
    path.write_text(path.read_text().replace("- [ ] done", "- [x] done"))
    bundle = wwm_collect.collect("s1")
    assert all(i["label"] != "Thread" for i in bundle["items"])


def test_checkpoint_supplies_state_and_next_when_the_ledger_has_none(
    fake_home, seeded, checkpointed
):
    """The checkpoint is the main source of State and Next on real sessions,
    and the unit tests never created one."""
    seeded("s1", 5)
    checkpointed("s1", overview="rewriting the indexer", next_steps="benchmark it")
    bundle = wwm_collect.collect("s1")
    by_label = {i["label"]: i for i in bundle["items"]}
    assert "rewriting the indexer" in by_label["State"]["text"]
    assert "benchmark it" in by_label["Next"]["text"]
    # Inferred content must never be dressed up as a recorded decision.
    assert by_label["State"]["source"] == "inf"
    assert by_label["Next"]["source"] == "inf"
    assert all(i["label"] != "Decided" for i in bundle["items"])


def test_recorded_state_wins_over_the_checkpoint(fake_home, seeded, checkpointed):
    """What the user said about where they are outranks what we guessed."""
    seeded("s1", 5)
    checkpointed("s1", overview="guessed state", next_steps="guessed next")
    wwm_ledger.record("s1", kind="state", text="the real state")
    wwm_ledger.record("s1", kind="next", text="the real next")
    bundle = wwm_collect.collect("s1")
    states = [i for i in bundle["items"] if i["label"] == "State"]
    nexts = [i for i in bundle["items"] if i["label"] == "Next"]
    assert len(states) == 1 and states[0]["text"] == "the real state"
    assert len(nexts) == 1 and nexts[0]["text"] == "the real next"


def test_checkpoint_spend_is_deducted_from_the_turn_budget(
    fake_home, seeded, checkpointed
):
    """The donation only applies to what the checkpoint did NOT use."""
    seeded("s1", 40, user="x" * 400)
    checkpointed("s1", overview="o" * 900, next_steps="n" * 1400)
    bundle = wwm_collect.collect("s1")
    spent = sum(len(i["text"]) for i in bundle["items"])
    spent += sum(len(t["text"]) for t in bundle["origin"])
    assert spent <= wwm_collect.wwm_history.BUDGET_TOTAL


def test_dedup_ignores_items_with_no_meaningful_words(fake_home, seeded):
    """All-stopword text has an empty fingerprint. Two *identical* such strings
    are the case that matters: without the guard the overlap calculation
    divides by min(0, 0) and raises, so this must be False and not a crash."""
    assert wwm_collect._fingerprint("the it is we") == frozenset()
    assert wwm_collect._same_event("the it is we", "the it is we") is False
    assert wwm_collect._same_event("", "") is False


def test_a_corrupt_store_degrades_to_the_ledger_instead_of_crashing(fake_home, seeded):
    """A file being present is not a readable database. sqlite only reports a
    truncated or foreign file once a statement runs, so guarding on existence
    alone let `no such table: turns` escape as a traceback, discarding every
    recorded decision at the moment the ledger was the only surviving record."""
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="decision", text="chose python")
    wwm_session.store_path().write_bytes(b"not a database at all")

    bundle = wwm_collect.collect("s1")
    assert bundle["has_history"] is False
    assert [i["text"] for i in bundle["items"]] == ["chose python"]
    assert bundle["insufficient"] is False
    # Staleness is unknowable without a store; claiming it points the reader at
    # content that is not there.
    assert bundle["stale"] is False
    assert bundle["origin"] == [] and bundle["files"] == []


def test_a_ledger_holding_only_a_thread_still_counts_as_a_ledger(fake_home, seeded):
    """has_ledger drives whether the sync boundary is honoured. Omitting
    threads and blockers meant a ledger with an open thread was treated as no
    ledger at all, replaying turns the user had already accounted for."""
    seeded("s1", 12)
    wwm_ledger.record("s1", kind="thread", text="retry logic still open")
    bundle = wwm_collect.collect("s1")
    assert bundle["has_ledger"] is True
    assert all(i["label"] != "Discussed" for i in bundle["items"]), (
        "sync boundary ignored: already-synced turns were replayed"
    )


def test_a_ledger_holding_only_a_blocker_still_counts_as_a_ledger(fake_home, seeded):
    seeded("s1", 12)
    wwm_ledger.record("s1", kind="blocker", text="waiting on vendor")
    assert wwm_collect.collect("s1")["has_ledger"] is True


def test_a_recorded_goal_becomes_a_visible_item(fake_home, seeded):
    """Regression, CRITICAL. `goal` was collected into the bundle and then
    read by nothing, so a ledger holding only a goal produced an item list of
    [] and rendered a completely blank answer. The user told the skill what
    they were doing and it showed them nothing."""
    seeded("s1", 1)
    wwm_ledger.record("s1", kind="goal", text="Ship the where-were-we skill")
    bundle = wwm_collect.collect("s1")
    goals = [i for i in bundle["items"] if i["label"] == "Goal"]
    assert len(goals) == 1
    assert goals[0]["text"] == "Ship the where-were-we skill"
    assert goals[0]["source"] == "rec"
    assert bundle["insufficient"] is False


def test_superseded_goals_are_collected_with_their_dates(fake_home, seeded):
    seeded("s1", 1)
    wwm_ledger.record("s1", kind="goal", text="Design the skill")
    wwm_ledger.record("s1", kind="goal", text="Ship the skill")
    bundle = wwm_collect.collect("s1")
    was = [i for i in bundle["items"] if i["label"] == "was"]
    assert len(was) == 1
    assert was[0]["text"].startswith("Design the skill (")
    assert was[0]["date"] in was[0]["text"]


def test_origin_is_promoted_not_duplicated(fake_home, seeded):
    """The Started row is the rendered form of the opening turn. Leaving that
    turn in `origin` too put the same string in the bundle twice and pushed
    the payload past BUDGET_TOTAL by exactly its own length."""
    seeded("s1", 1, user="set up CI for the repo")
    seeded("s1", 12, user="rewrite the search indexer", start=1)
    bundle = wwm_collect.collect("s1")
    started = next(i for i in bundle["items"] if i["label"] == "Started")
    assert all(t["turn_index"] != started["turn_index"] for t in bundle["origin"])


def test_origin_is_not_repeated_when_it_merely_restates_the_goal(fake_home, seeded):
    """A session that never pivoted gains nothing from being told twice where
    it started. Paired with the diverging case so this cannot pass merely by
    `Started` not existing at all."""
    seeded("s1", 1, user="rewrite the search indexer")
    wwm_ledger.record("s1", kind="goal", text="rewrite the search indexer")
    same = wwm_collect.collect("s1")
    assert not [i for i in same["items"] if i["label"] == "Started"]

    seeded("s2", 1, user="set up CI for the repo")
    wwm_ledger.record("s2", kind="goal", text="rewrite the search indexer")
    pivoted = wwm_collect.collect("s2")
    assert [i for i in pivoted["items"] if i["label"] == "Started"]
