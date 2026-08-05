# tests/where-were-we/test_ledger.py
import wwm_ledger

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
