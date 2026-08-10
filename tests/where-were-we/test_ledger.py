# tests/where-were-we/test_ledger.py
import pytest
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
    # Not 0. Reconciliation selects turn_index > last_synced_turn, so 0 would
    # claim the new session's own first turn was already folded in.
    assert led.last_synced_turn == -1


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


def test_a_hand_edited_sync_marker_is_reported_not_crashed_on(fake_home, tmp_path):
    path = wwm_session.ledger_path("s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# where-were-we\n\nlast_synced_turn: yesterday\n\n"
        "## decisions\n- 2026-08-05 chose python\n"
    )
    led = wwm_ledger.parse(path.read_text())
    assert led.last_synced_turn == 0
    assert "last_synced_turn" in led.damaged
    # The rest of the file must still survive a bad marker.
    assert [d.text for d in led.decisions] == ["chose python"]


def test_a_parser_blowing_up_costs_one_section_not_the_whole_file(
    fake_home, monkeypatch
):
    """The blind `except Exception` around each section parser is a last-resort
    guard: the ledger is the only surviving record of intent when the store is
    gone, so no single malformed section may take the file down. It had never
    been exercised, which is the worst state for a safety net to be in."""

    def explode(_lines):
        raise RuntimeError("parser bug")

    monkeypatch.setattr(wwm_ledger, "_decisions", explode)
    led = wwm_ledger.parse(
        "## decisions\n- chose python\n\n## blockers\n- waiting on vendor\n"
    )
    assert led.decisions == []
    assert "decisions" in led.damaged
    assert led.blockers == ["waiting on vendor"], "one bad section took out another"


def test_an_unreadable_ledger_file_yields_an_empty_ledger_not_an_error(fake_home):
    path = wwm_session.ledger_path("s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()  # a directory where a file belongs: read_text raises OSError
    led = wwm_ledger.load("s1")
    assert led.decisions == [] and led.threads == []


def test_recording_an_unknown_kind_is_refused(fake_home, tmp_path):
    with pytest.raises(ValueError, match="unknown kind"):
        wwm_ledger.record("s1", kind="vibe", text="something")


def test_goal_is_recordable_and_round_trips(fake_home):
    wwm_ledger.record("s1", kind="goal", text="ship the skill")
    assert wwm_ledger.load("s1").goal == "ship the skill"


def test_store_max_turn_reports_nothing_synced_when_the_store_is_absent(fake_home):
    assert wwm_ledger._max_turn_index("s1") == -1


def test_store_max_turn_reports_nothing_synced_when_the_store_is_not_a_database(
    fake_home,
):
    store = wwm_session.store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_bytes(b"this is not sqlite")
    assert wwm_ledger._max_turn_index("s1") == -1


def test_a_hand_typed_blocker_without_a_bullet_is_disclosed_not_dropped():
    """Same disclosure rule as decisions and threads: a line the parser cannot
    read is reported through `damaged`, never discarded in silence."""
    led = wwm_ledger.parse(
        "# where-were-we\n\n## blockers\n"
        "- waiting on vendor\nstill blocked on the cert\n"
    )
    assert led.blockers == ["waiting on vendor"]
    assert "blockers" in led.damaged


def test_a_typo_in_a_metadata_key_is_disclosed_not_swallowed():
    """Third instance of the same class as dropped decisions and unreadable
    headings: a `key: value` line the parser does not recognise is almost
    always a typo for one it does, and dropping it loses what the user wrote."""
    led = wwm_ledger.parse("# where-were-we\n\ngola: ship the thing\n\n## decisions\n")
    assert led.goal is None
    assert "gola" in led.damaged


def test_a_clean_ledger_reports_no_damage():
    """Guards the disclosure above from becoming a false alarm on every file:
    prose, headings and bullets must not be mistaken for metadata keys."""
    led = wwm_ledger.parse(
        "# where-were-we\n\ngoal: ship it\nlast_synced_turn: 4\n\n"
        "## decisions\n- 2026-08-05 chose python\n  why: it fits\n\n"
        "## threads\n- [ ] retry logic\n"
    )
    assert led.damaged == []
    assert led.goal == "ship it" and led.last_synced_turn == 4


def test_concurrent_writers_do_not_destroy_each_others_ledger(fake_home):
    """A fixed .tmp name races when two processes record against the same
    session, which is routine here: a subagent and its parent share a session
    id. The first rename pulls the temp file out from under the second."""
    import threading

    path = wwm_session.ledger_path("s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def writer(n: int) -> None:
        try:
            barrier.wait()
            for _ in range(20):
                wwm_ledger._atomic_write(path, f"# where-were-we\n\ngoal: {n}\n")
        except BaseException as err:  # noqa: BLE001 - recorded and asserted on
            errors.append(err)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors, f"concurrent writes failed: {errors[:3]}"
    # Whoever won, the file must be one complete ledger and never a fragment.
    assert wwm_ledger.parse(path.read_text()).goal in {str(n) for n in range(8)}
    leftovers = list(path.parent.glob("*.tmp"))
    assert not leftovers, f"temp files left behind: {leftovers}"


# --- Preserve-verbatim policy -------------------------------------------
# The ledger is the user's own written record. Everywhere the parser cannot
# read something, the text must still survive the next write. Disclosure
# without preservation is data loss with a warning label on it.

DAMAGED = """# where-were-we

started: 2026-01-01
gola: typo for goal
a bare prose note with no colon

## decisions
- 2026-01-01 a decision that parses
this line does not parse but is mine

## scratchpad
hand written note I care about

## blockers
- db is down
"""


def _write_ledger(session_id: str, text: str) -> None:
    path = wwm_session.ledger_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_record_preserves_every_line_it_could_not_parse(fake_home, seeded):
    seeded("s1", 3)
    _write_ledger("s1", DAMAGED)

    wwm_ledger.record("s1", kind="thread", text="new thread")

    after = wwm_session.ledger_path("s1").read_text()
    for line in (
        "gola: typo for goal",
        "a bare prose note with no colon",
        "this line does not parse but is mine",
        "## scratchpad",
        "hand written note I care about",
    ):
        assert line in after, f"record() destroyed: {line!r}"
    assert "- [ ] new thread" in after


def test_damaged_sections_are_still_disclosed_while_preserved(fake_home, seeded):
    seeded("s1", 3)
    _write_ledger("s1", DAMAGED)
    led = wwm_ledger.load("s1")
    # Preserving the text must not quietly downgrade the warning.
    assert "decisions" in led.damaged
    assert "gola" in led.damaged
    assert led.unknown_sections["scratchpad"] == ["hand written note I care about"]


def test_preserved_content_is_stable_across_repeated_records(fake_home, seeded):
    seeded("s1", 3)
    _write_ledger("s1", DAMAGED)
    wwm_ledger.record("s1", kind="blocker", text="b1")
    once = wwm_session.ledger_path("s1").read_text()
    wwm_ledger.record("s1", kind="blocker", text="b2")
    twice = wwm_session.ledger_path("s1").read_text()
    # Only the new blocker may differ. Content that is re-parsed and re-written
    # on every save must not drift, duplicate, or accumulate.
    assert twice == once.replace("- b1\n", "- b1\n- b2\n")


def test_record_refuses_to_overwrite_a_ledger_it_cannot_read(fake_home, seeded):
    seeded("s1", 3)
    path = wwm_session.ledger_path("s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe\x00not utf-8 at all")
    before = path.read_bytes()

    with pytest.raises(wwm_ledger.LedgerRefused):
        wwm_ledger.record("s1", kind="decision", text="should not be written")

    assert path.read_bytes() == before, "refused write still modified the file"


def test_unreadable_ledger_is_distinguishable_from_no_ledger(fake_home, seeded):
    seeded("s1", 3)
    path = wwm_session.ledger_path("s1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe\x00")
    assert wwm_ledger.load("s1").unreadable is True
    assert wwm_ledger.load("absent-session").unreadable is False


def test_adopt_refuses_a_source_with_no_content(fake_home, seeded):
    seeded("mine", 3)
    wwm_ledger.record("mine", kind="decision", text="MY OWN WORK")

    with pytest.raises(wwm_ledger.LedgerRefused, match="typoed"):
        wwm_ledger.adopt(source="typoed", target="mine")

    assert "MY OWN WORK" in wwm_session.ledger_path("mine").read_text()


def test_adopt_refuses_to_replace_a_target_that_has_content(fake_home, seeded):
    seeded("old", 3)
    seeded("mine", 3)
    wwm_ledger.record("old", kind="decision", text="theirs")
    wwm_ledger.record("mine", kind="decision", text="MY OWN WORK")

    with pytest.raises(wwm_ledger.LedgerRefused):
        wwm_ledger.adopt(source="old", target="mine")

    assert "MY OWN WORK" in wwm_session.ledger_path("mine").read_text()


def test_adopt_leaves_turn_zero_unsynced(fake_home, seeded):
    seeded("old", 3)
    seeded("fresh", 3)
    wwm_ledger.record("old", kind="decision", text="carried")
    wwm_ledger.adopt(source="old", target="fresh")
    # 0 would mean "turn 0 already folded in" and hide the first turn.
    assert wwm_ledger.load("fresh").last_synced_turn == -1


def test_store_max_turn_reports_nothing_synced_for_a_session_with_no_turns(
    fake_home, seeded
):
    seeded("other", 5)
    # 'ghost' is a real id with no turns yet. Returning 0 here would stamp
    # last_synced_turn: 0 on its first record and hide its opening turn.
    assert wwm_ledger._max_turn_index("ghost") == -1


def test_adopt_refuses_a_source_it_cannot_read(fake_home, seeded):
    seeded("old", 3)
    seeded("fresh", 3)
    path = wwm_session.ledger_path("old")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(wwm_ledger.LedgerRefused):
        wwm_ledger.adopt(source="old", target="fresh")

    assert not wwm_session.ledger_path("fresh").exists()


def test_recording_a_new_goal_keeps_the_old_one(fake_home, seeded):
    """Regression, HIGH. Goals change over a long session, so overwriting is
    correct, but the goal that was replaced is the only record of how the work
    got here. It used to be dropped on the floor."""
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="goal", text="Design the skill")
    led = wwm_ledger.record("s1", kind="goal", text="Ship the skill")
    assert led.goal == "Ship the skill"
    assert [p.text for p in led.goal_history] == ["Design the skill"]


def test_goal_history_is_ordered_oldest_first(fake_home, seeded):
    seeded("s1", 3)
    for text in ("first", "second", "third"):
        wwm_ledger.record("s1", kind="goal", text=text)
    led = wwm_ledger.load("s1")
    assert led.goal == "third"
    assert [p.text for p in led.goal_history] == ["first", "second"]


def test_recording_the_same_goal_twice_does_not_grow_history(fake_home, seeded):
    """Re-affirming the goal is not a pivot and must not pad the history."""
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="goal", text="Ship the skill")
    led = wwm_ledger.record("s1", kind="goal", text="Ship the skill")
    assert led.goal_history == []


def test_goal_history_survives_a_round_trip(fake_home, seeded):
    """A superseded goal that parses but does not serialize is destroyed by
    the next unrelated record()."""
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="goal", text="Design the skill")
    wwm_ledger.record("s1", kind="goal", text="Ship the skill")
    wwm_ledger.record("s1", kind="decision", text="Chose option A")
    led = wwm_ledger.load("s1")
    assert [p.text for p in led.goal_history] == ["Design the skill"]
    assert led.damaged == [], "the history section must parse cleanly"


def test_a_ledger_with_no_history_gains_no_empty_section(fake_home, seeded):
    """An empty heading written into every ledger would rewrite every existing
    file for no content. Paired with the positive case so this cannot pass
    merely by the section never being written at all."""
    seeded("s1", 3)
    wwm_ledger.record("s1", kind="goal", text="Ship the skill")
    assert "## goal history" not in wwm_session.ledger_path("s1").read_text()
    wwm_ledger.record("s1", kind="goal", text="Ship it differently")
    assert "## goal history" in wwm_session.ledger_path("s1").read_text()
