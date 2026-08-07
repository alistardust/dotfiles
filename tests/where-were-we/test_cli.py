# tests/where-were-we/test_cli.py
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "where-were-we" / "scripts"
CLI = SCRIPTS / "wwm.py"


def run(args, home, session=None):
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
    if session:
        env["COPILOT_AGENT_SESSION_ID"] = session
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_collect_emits_json(fake_home, seeded):
    seeded("s1", 3)
    result = run(["collect"], fake_home, session="s1")
    assert result.returncode == 0
    assert json.loads(result.stdout)["session_id"] == "s1"


def test_explicit_session_overrides_env(fake_home, seeded):
    seeded("other", 2)
    result = run(["collect", "--session", "other"], fake_home, session="s1")
    assert json.loads(result.stdout)["session_id"] == "other"


def test_missing_session_refuses(fake_home, store):
    result = run(["collect"], fake_home)
    assert result.returncode != 0
    assert "--session" in result.stderr


def test_explicit_session_works_without_env(fake_home, seeded):
    """Cross-session handoff must succeed with no env var set."""
    seeded("target", 3)
    result = run(["collect", "--session", "target"], fake_home)
    assert result.returncode == 0


def test_unknown_session_refuses_without_falling_back(fake_home, seeded):
    seeded("s1", 3)
    result = run(["collect", "--session", "ghost"], fake_home, session="s1")
    assert result.returncode != 0
    assert "not in the store" in result.stderr
    assert "s1" not in result.stdout


def test_non_copilot_runtime_reports_unsupported(fake_home):
    result = run(["collect", "--session", "s1"], fake_home)
    assert result.returncode != 0
    assert (
        "unsupported" in result.stderr.lower() or "not found" in result.stderr.lower()
    )


def test_render_collects_in_process_and_touches_no_temp_file(fake_home, seeded):
    """The bundle carries raw session text. Routing it through a file put that
    text on disk outside ~/.copilot/session-state under the default umask,
    contradicting this skill's own PHI posture."""
    seeded("s1", 3)
    before = set(fake_home.iterdir())
    result = run(["render", "--level", "tldr"], fake_home, session="s1")
    assert result.returncode == 0
    assert all(len(line) <= 72 for line in result.stdout.splitlines())
    assert set(fake_home.iterdir()) == before


def test_render_is_gated_like_every_other_subcommand(fake_home, seeded):
    """Regression. render resolved the session directly instead of going
    through the shared gate, so `render --session ghost` skipped both the
    runtime check and the unknown-session refusal that `collect` enforces."""
    seeded("s1", 3)
    result = run(["render", "--session", "ghost"], fake_home, session="s1")
    assert result.returncode != 0
    assert "not in the store" in result.stderr
    assert result.stdout == ""


def test_record_writes_through_the_script(fake_home, seeded):
    seeded("s1", 4)
    result = run(
        ["record", "--kind", "decision", "--text", "chose python"],
        fake_home,
        session="s1",
    )
    assert result.returncode == 0
    ledger = fake_home / ".copilot" / "session-state" / "s1" / "files" / "ledger.md"
    assert "chose python" in ledger.read_text()
    assert "last_synced_turn: 3" in ledger.read_text()


def test_adopt_carries_a_ledger_across_sessions(fake_home, seeded):
    seeded("old", 3)
    seeded("new", 2, start=3)
    run(
        ["record", "--kind", "decision", "--text", "carried over"],
        fake_home,
        session="old",
    )
    result = run(["adopt", "--source", "old"], fake_home, session="new")
    assert result.returncode == 0
    ledger = fake_home / ".copilot" / "session-state" / "new" / "files" / "ledger.md"
    text = ledger.read_text()
    assert "carried over" in text
    assert "adopted_from: old" in text


def test_sessions_lists_and_counts_the_remainder(fake_home, store):
    result = run(["sessions"], fake_home, session="s1")
    assert result.returncode == 0


def test_sessions_works_without_a_current_session(fake_home, store):
    """Listing sessions is how a user finds one; it cannot require knowing one."""
    result = run(["sessions"], fake_home)
    assert result.returncode == 0


def test_script_failure_produces_no_partial_render(fake_home, seeded):
    """A failure must print nothing at all, not half a block."""
    seeded("s1", 3)
    result = run(["render", "--section", "nonsense"], fake_home, session="s1")
    assert result.returncode != 0
    assert "[rec]" not in result.stdout
    assert result.stdout == ""


def test_empty_session_is_answered_gracefully_not_as_an_error(fake_home, store):
    """An empty session is a real answer ("nothing here"), not a crash."""
    result = run(["render"], fake_home, session="s1")
    assert result.returncode == 0
    assert "Not enough here" in result.stdout


def test_bad_level_is_refused_by_the_parser(fake_home, seeded):
    seeded("s1", 3)
    result = run(["render", "--level", "everything"], fake_home, session="s1")
    assert result.returncode != 0
    assert result.stdout == ""
