# tests/where-were-we/test_ledger.py
import wwm_ledger
import wwm_session

FULL = """# where-were-we

goal: Design a session-summary skill for Copilot
started: 2026-08-04
updated: 2026-08-05
last_synced_turn: 42

## state
Design phase. Criteria agreed, approach chosen.

## next
Finish design sections, then write the spec.

## decisions
- 2026-08-05 Approach B, scripts plus skill
  why: budget and format must be deterministic
  rejected: pure prompt (drifts), full CLI (too heavy)

## threads
- [ ] Instruction wording for invocation
- [x] Confirm dotfiles is clean before branching

## blockers
(none)
"""


def test_parses_metadata():
    led = wwm_ledger.parse(FULL)
    assert led.goal.startswith("Design a session-summary")
    assert led.last_synced_turn == 42


def test_parses_decision_with_why_and_rejected():
    led = wwm_ledger.parse(FULL)
    assert len(led.decisions) == 1
    dec = led.decisions[0]
    assert dec.text == "Approach B, scripts plus skill"
    assert dec.date == "2026-08-05"
    assert "deterministic" in dec.why
    assert "pure prompt" in dec.rejected


def test_open_and_closed_threads_are_distinguished():
    led = wwm_ledger.parse(FULL)
    assert [t.text for t in led.threads if not t.done] == [
        "Instruction wording for invocation"
    ]


def test_none_blockers_is_empty_not_a_blocker():
    assert wwm_ledger.parse(FULL).blockers == []


def test_missing_sections_are_legal():
    led = wwm_ledger.parse("# where-were-we\n\ngoal: something\n")
    assert led.goal == "something"
    assert led.state is None
    assert led.decisions == []
    assert led.last_synced_turn == 0


def test_corrupt_body_keeps_what_parses():
    text = FULL.replace("## threads", "## thr@@ds")
    led = wwm_ledger.parse(text)
    assert led.last_synced_turn == 42
    assert len(led.decisions) == 1
    assert led.threads == []


def test_round_trip_is_lossless():
    led = wwm_ledger.parse(FULL)
    assert wwm_ledger.parse(wwm_ledger.serialize(led)) == led


def test_empty_file_parses_to_empty_ledger():
    led = wwm_ledger.parse("")
    assert led.goal is None
    assert led.decisions == []


def test_clean_ledger_reports_no_damage():
    """A well-formed ledger must never raise a false alarm."""
    assert wwm_ledger.parse(FULL).damaged == []


def test_malformed_decision_line_is_disclosed_not_swallowed():
    """A typo'd date must be reported, not silently dropped.

    A dropped line is a lost decision, and a lost decision is exactly the
    failure this skill exists to prevent. Losing it quietly is worse than
    losing it loudly.
    """
    text = FULL.replace("- 2026-08-05", "- 2026/08/05")
    led = wwm_ledger.parse(text)
    assert "decisions" in led.damaged


def test_malformed_thread_line_is_disclosed():
    text = FULL.replace("- [ ]", "- (]")
    led = wwm_ledger.parse(text)
    assert "threads" in led.damaged


def test_partial_damage_preserves_every_other_section():
    """One bad section must not cost the user the rest of the ledger."""
    text = FULL.replace("- 2026-08-05", "- 2026/08/05")
    led = wwm_ledger.parse(text)
    assert led.goal is not None
    assert led.state is not None
    assert led.last_synced_turn == 42
    assert "threads" not in led.damaged


def test_record_stamps_turn_from_store(fake_home, seeded):
    seeded("s1", 5)  # turn_index 0..4
    wwm_ledger.record(
        "s1", kind="decision", text="Chose Python", why="parameterized SQL"
    )
    led = wwm_ledger.load("s1")
    assert led.last_synced_turn == 4
    assert led.decisions[0].text == "Chose Python"
    assert led.decisions[0].why == "parameterized SQL"


def test_record_never_stamps_ahead_of_the_store(fake_home, seeded):
    """The calling turn is in progress and not yet flushed. Do not compensate."""
    seeded("s1", 3)  # highest committed index is 2
    wwm_ledger.record("s1", kind="decision", text="Something decided this turn")
    assert wwm_ledger.load("s1").last_synced_turn == 2


def test_record_ignores_caller_supplied_sync_value(fake_home, seeded):
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="decision", text="x", last_synced_turn=999)
    assert wwm_ledger.load("s1").last_synced_turn == 2


def test_record_blocker_and_thread(fake_home, seeded):
    seeded("s1", 1)
    wwm_ledger.record("s1", kind="blocker", text="waiting on review")
    wwm_ledger.record("s1", kind="thread", text="wire up setup verify")
    led = wwm_ledger.load("s1")
    assert led.blockers == ["waiting on review"]
    assert led.threads[0].text == "wire up setup verify"


def test_record_creates_ledger_when_absent(fake_home, seeded):
    seeded("s1", 2)
    assert not wwm_session.ledger_path("s1").exists()
    wwm_ledger.record("s1", kind="decision", text="first")
    assert wwm_session.ledger_path("s1").exists()


def test_adopt_copies_content_but_not_sync_state(fake_home, seeded):
    seeded("old", 400)
    seeded("new", 3)
    wwm_ledger.record("old", kind="decision", text="carried over", why="still true")
    assert wwm_ledger.load("old").last_synced_turn == 399

    wwm_ledger.adopt(source="old", target="new")
    led = wwm_ledger.load("new")
    assert led.decisions[0].text == "carried over"
    assert led.adopted_from == "old"
    assert led.last_synced_turn == 0


def test_adopt_does_not_mutate_the_source(fake_home, seeded):
    seeded("old", 10)
    seeded("new", 1)
    wwm_ledger.record("old", kind="decision", text="keep")
    wwm_ledger.adopt(source="old", target="new")
    assert wwm_ledger.load("old").last_synced_turn == 9


def test_write_is_atomic(fake_home, seeded, monkeypatch):
    """A crash mid-write must not leave a truncated ledger."""
    seeded("s1", 2)
    wwm_ledger.record("s1", kind="decision", text="good")
    original = wwm_session.ledger_path("s1").read_text()

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(wwm_ledger.os, "replace", boom)
    try:
        wwm_ledger.record("s1", kind="decision", text="doomed")
    except OSError:
        pass
    assert wwm_session.ledger_path("s1").read_text() == original


def test_hand_edited_heading_case_still_parses(fake_home):
    """A user editing their own ledger types `## Decisions`, not `## decisions`.

    Regression, S-F9. The heading regex was `[a-z_]+`, so a capitalised
    heading was not a heading at all: every decision under it was silently
    discarded and the lines were absorbed into whatever section came before.
    """
    led = wwm_ledger.parse(
        "# where-were-we\n\n## Decisions\n- 2026-08-05 chose sqlite\n"
    )
    assert [d.text for d in led.decisions] == ["chose sqlite"]
    assert led.damaged == []


def test_unknown_heading_is_disclosed_not_swallowed(fake_home):
    """Content under a heading we do not understand must not vanish quietly."""
    led = wwm_ledger.parse(
        "# where-were-we\n\n## decisions\n- 2026-08-05 kept\n"
        "## scratchpad\nsomething the user typed and would never see again\n"
    )
    assert [d.text for d in led.decisions] == ["kept"]
    assert "scratchpad" in led.damaged


def test_empty_unknown_heading_is_not_a_false_alarm(fake_home):
    """A stray heading with nothing under it loses nothing, so stays quiet."""
    led = wwm_ledger.parse("# where-were-we\n\n## notes\n\n## decisions\n- x\n")
    assert "notes" not in led.damaged


def test_duplicate_heading_merges_instead_of_discarding(fake_home):
    """The second `## decisions` used to reset the list and drop the first."""
    led = wwm_ledger.parse(
        "# where-were-we\n\n## decisions\n- 2026-08-05 first\n"
        "## decisions\n- 2026-08-06 second\n"
    )
    assert [d.text for d in led.decisions] == ["first", "second"]
