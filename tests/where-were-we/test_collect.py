# tests/where-were-we/test_collect.py
import wwm_collect
import wwm_ledger
import wwm_render


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
    used = [i["turn_index"] for i in bundle["items"] if "turn_index" in i]
    assert used, "fallback produced no turns at all"
    assert max(used) == 59, "fallback must reach the end of the session"
    assert min(used) > 30, f"fallback returned early turns: {min(used)}"


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
    seeded("s1", 1, user="set up CI for the repo")
    seeded("s1", 12, user="rewrite the search indexer", start=1)
    bundle = wwm_collect.collect("s1")
    assert bundle["origin"], "origin turns must survive the budget"


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
