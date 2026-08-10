# tests/where-were-we/test_history.py
import sqlite3

import pytest
import wwm_history
import wwm_session


def test_store_is_opened_read_only(fake_home, store):
    conn = wwm_history.connect()
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO turns (session_id, turn_index) VALUES ('x', 1)")
    conn.close()


def test_queries_do_not_leak_connections(fake_home, seeded, monkeypatch):
    """Regression: `with sqlite3.connect(...) as c` commits, it does NOT close.

    Every query function opens its own connection, so the naive form leaked one
    handle per call.
    """
    opened = []
    real = sqlite3.connect

    def spy(*args, **kwargs):
        conn = real(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", spy)
    seeded("s1", 5)
    wwm_history.max_turn_index("s1")
    wwm_history.earliest_turns("s1")
    wwm_history.recent_turns("s1")
    wwm_history.latest_checkpoint("s1")
    wwm_history.session_files("s1")
    wwm_history.recent_sessions()

    assert opened, "spy never fired; the test is not exercising connect()"
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")


def test_max_turn_index_of_empty_session_is_zero(fake_home, store):
    assert wwm_history.max_turn_index("nobody") == 0


def test_max_turn_index(fake_home, seeded):
    seeded("s1", 5)
    assert wwm_history.max_turn_index("s1") == 4


def test_single_turn_session_is_not_mistaken_for_absent(fake_home, seeded):
    """turn_index is 0-based in the real store (verified MIN(turn_index) = 0).

    A one-turn session has max index 0, exactly like an empty one. Existence
    must be its own query or real sessions get rejected as unknown.
    """
    seeded("s1", 1)
    assert wwm_history.max_turn_index("s1") == 0
    assert wwm_history.session_exists("s1") is True
    assert wwm_history.session_exists("nobody") is False


def test_turn_text_keeps_both_halves_of_the_exchange(fake_home, store):
    conn = sqlite3.connect(store)
    conn.execute(
        "INSERT INTO turns (session_id, turn_index, user_message, assistant_response)"
        " VALUES (?, ?, ?, ?)",
        ("s1", 0, "should we use rust", "no, python stdlib only"),
    )
    conn.commit()
    conn.close()
    text = wwm_history.recent_turns("s1")[0]["text"]
    assert "should we use rust" in text
    # Keeping only the user half made the fallback blind to every conclusion
    # the assistant actually reached.
    assert "python stdlib only" in text


def test_earliest_turns_respects_its_slice(fake_home, seeded):
    seeded("s1", 40, user="x" * 4000)
    slice_ = wwm_history.earliest_turns("s1", budget=1500)
    assert sum(len(t["text"]) for t in slice_) <= 1500
    assert slice_[0]["turn_index"] == 0


def test_recent_turns_capped_per_turn_and_in_total(fake_home, seeded):
    seeded("s1", 50, user="y" * 4000)
    slice_ = wwm_history.recent_turns("s1", budget=3000, count=12, per_turn=250)
    assert len(slice_) <= 12
    assert all(len(t["text"]) <= 250 for t in slice_)
    assert sum(len(t["text"]) for t in slice_) <= 3000


def test_recent_turns_are_the_newest(fake_home, seeded):
    seeded("s1", 30)
    slice_ = wwm_history.recent_turns("s1", budget=3000, count=12, per_turn=250)
    assert slice_[-1]["turn_index"] == 29


def test_one_huge_turn_cannot_eat_another_slice(fake_home, seeded):
    """The starvation finding: slices are reserved, not first-come."""
    seeded("s1", 30, user="z" * 50000)
    earliest = wwm_history.earliest_turns("s1", budget=1500)
    recent = wwm_history.recent_turns("s1", budget=3000, count=12, per_turn=250)
    assert earliest, "earliest slice must survive a huge recent turn"
    assert recent, "recent slice must survive a huge earliest turn"


def test_turns_after_returns_only_newer(fake_home, seeded):
    seeded("s1", 10)
    newer = wwm_history.turns_after("s1", after=6, budget=3000, per_turn=250)
    assert [t["turn_index"] for t in newer] == [7, 8, 9]


def test_latest_checkpoint_prefers_the_newest(fake_home, store):
    conn = sqlite3.connect(store)
    conn.executemany(
        "INSERT INTO checkpoints (session_id, checkpoint_number, title, overview,"
        " next_steps, important_files, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("s1", 1, "old", "old overview", "old next", "a.py", "2026-08-01"),
            ("s1", 2, "new", "new overview", "new next", "b.py", "2026-08-02"),
        ],
    )
    conn.commit()
    conn.close()
    cp = wwm_history.latest_checkpoint("s1", budget=2500)
    assert cp["title"] == "new"


def test_checkpoint_budget_is_joint_across_both_fields(fake_home, store):
    """Regression: the budget was once applied to each field independently.

    That let this slice spend double its reservation. Measured against the real
    store, 462 of 581 checkpoints exceed 1500 chars combined and the largest
    reaches 5256.
    """
    conn = sqlite3.connect(store)
    conn.execute(
        "INSERT INTO checkpoints (session_id, checkpoint_number, title, overview,"
        " next_steps, important_files, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("s1", 1, "t", "o" * 4000, "n" * 4000, "", "2026-08-01"),
    )
    conn.commit()
    conn.close()
    cp = wwm_history.latest_checkpoint("s1", budget=2500)
    assert len(cp["overview"]) + len(cp["next_steps"]) <= 2500
    assert cp["spent"] == len(cp["overview"]) + len(cp["next_steps"])
    # Both fields must survive; next_steps is the most useful single field and
    # must not be starved to zero by an oversized overview.
    assert cp["next_steps"]


def test_checkpoint_reports_unspent_allowance(fake_home, store):
    conn = sqlite3.connect(store)
    conn.execute(
        "INSERT INTO checkpoints (session_id, checkpoint_number, title, overview,"
        " next_steps, important_files, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("s1", 1, "t", "short", "brief", "", "2026-08-01"),
    )
    conn.commit()
    conn.close()
    cp = wwm_history.latest_checkpoint("s1", budget=2500)
    assert cp["spent"] == len("short") + len("brief")


def test_no_checkpoint_returns_none(fake_home, store):
    assert wwm_history.latest_checkpoint("s1", budget=2500) is None


def test_session_files_come_from_the_store(fake_home, store):
    conn = sqlite3.connect(store)
    conn.execute(
        "INSERT INTO session_files (session_id, file_path, tool_name, turn_index,"
        " first_seen_at) VALUES ('s1', 'src/a.py', 'edit', 3, '2026-08-05')"
    )
    conn.commit()
    conn.close()
    assert wwm_history.session_files("s1") == ["src/a.py"]


def test_recent_sessions_windowed_and_limited(fake_home, store):
    conn = sqlite3.connect(store)
    conn.executemany(
        "INSERT INTO sessions (id, cwd, repository, branch, summary, created_at,"
        " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                f"s{i}",
                "/tmp",
                "repo",
                "master",
                f"summary {i}",
                "2026-01-01",
                f"2026-08-{5 - (i % 3):02d}",
            )
            for i in range(20)
        ]
        + [("ancient", "/tmp", "repo", "master", "old", "2020-01-01", "2020-01-01")],
    )
    conn.commit()
    conn.close()
    rows = wwm_history.recent_sessions(days=14, limit=10, now="2026-08-05")
    assert len(rows) == 10
    assert all(r["id"] != "ancient" for r in rows)


def test_missing_store_raises_rather_than_inventing(fake_home):
    with pytest.raises(wwm_history.StoreUnavailable):
        wwm_history.max_turn_index("s1")


def test_a_turn_with_no_reply_yet_still_carries_its_user_message(fake_home, store):
    """The newest turn is routinely mid-flight: the user has spoken and the
    assistant has not answered. That turn is the single most relevant one for
    'where were we', so it must not be formatted as an empty exchange."""
    conn = sqlite3.connect(store)
    conn.execute(
        "INSERT INTO turns (session_id, turn_index, user_message,"
        " assistant_response, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("s1", 1, "what about the parser", None, "2026-08-05T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    turns = wwm_history.recent_turns("s1", budget=2500)
    assert turns and "what about the parser" in turns[0]["text"]
    assert "->" not in turns[0]["text"], "empty reply rendered as an exchange"


def test_a_turn_with_neither_side_is_skipped_rather_than_shown_blank(fake_home, store):
    conn = sqlite3.connect(store)
    conn.executemany(
        "INSERT INTO turns (session_id, turn_index, user_message,"
        " assistant_response, timestamp) VALUES (?, ?, ?, ?, ?)",
        [
            ("s1", 1, "", "", "2026-08-05T00:00:00Z"),
            ("s1", 2, "a real question", "a real answer", "2026-08-05T00:01:00Z"),
        ],
    )
    conn.commit()
    conn.close()
    turns = wwm_history.recent_turns("s1", budget=2500)
    assert [t["turn_index"] for t in turns] == [2]


def test_cap_never_emits_more_than_it_was_given(fake_home):
    """A budget can legitimately arrive at zero once earlier slices have spent
    it; capping must return nothing rather than an ellipsis that costs three
    characters nobody allocated."""
    assert wwm_history._cap("some text", 0) == ""
    assert wwm_history._cap("some text", -5) == ""
    for limit in (1, 2, 3):
        assert len(wwm_history._cap("some text", limit)) <= limit
    assert wwm_history._cap("some text", 6) == "som..."


def test_an_unopenable_store_is_reported_as_unavailable(fake_home):
    """sqlite refuses to open a directory; the caller must get the typed
    StoreUnavailable it knows how to degrade on, not a raw sqlite error."""
    store = wwm_session.store_path()
    store.parent.mkdir(parents=True, exist_ok=True)
    store.mkdir()
    with pytest.raises(wwm_history.StoreUnavailable):
        wwm_history.recent_turns("s1", budget=100)
