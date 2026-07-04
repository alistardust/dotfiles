"""Task 1.6: resolution-queue worker (spec §4.1a, §4.3, AC-D7/X2).

The worker is the resumable engine that backs non-blocking library-first add.
It is deliberately I/O-free in itself: a resolver is injected, so the same code
path serves the background drain and the foreground resolve command, and tests
never touch the network.
"""

from datetime import datetime, timezone

import pytest

from tuneshift.db import Database
from tuneshift.library.worker import (
    ResolutionRateLimited,
    ResolutionWorker,
    ResolvedCandidate,
)
from tuneshift.models import Track


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _track(db, title="Buddy", artist="De La Soul"):
    return db.insert_track(Track(title=title, artist=artist, album="3 Feet High and Rising"))


def test_enqueue_then_drain_resolves(db):
    tid = _track(db)

    def resolver(track):
        return [
            ResolvedCandidate("tidal", "111", {"audio_modes": ["DOLBY_ATMOS"]}),
            ResolvedCandidate("tidal", "222", {"audio_modes": ["STEREO"]}),
        ]

    worker = ResolutionWorker(db, resolver=resolver)
    worker.enqueue(tid)
    resolved = worker.drain()
    assert resolved == 1

    state = db.conn.execute(
        "SELECT state FROM resolution_queue WHERE track_id=?", (tid,)
    ).fetchone()["state"]
    assert state == "resolved"
    cands = db.get_track_candidates(tid, platform="tidal")
    assert {c["platform_track_id"] for c in cands} == {"111", "222"}


def test_rate_limited_stays_pending_with_backoff(db):
    tid = _track(db)

    def resolver(track):
        raise ResolutionRateLimited("429 from tidal")

    worker = ResolutionWorker(db, resolver=resolver)
    worker.enqueue(tid)
    resolved = worker.drain()
    assert resolved == 0  # nothing successfully resolved

    row = db.conn.execute(
        "SELECT state, attempts, next_attempt_at, last_error FROM resolution_queue WHERE track_id=?",
        (tid,),
    ).fetchone()
    assert row["state"] == "pending", "rate-limited work must NOT be lost"
    assert row["attempts"] == 1
    assert row["next_attempt_at"] is not None
    # backoff is in the future
    assert row["next_attempt_at"] > datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    assert "429" in row["last_error"]


def test_unresolvable_is_quarantined_with_reason(db):
    tid = _track(db)

    def resolver(track):
        return []  # no candidate found anywhere

    worker = ResolutionWorker(db, resolver=resolver)
    worker.enqueue(tid)
    worker.drain()

    row = db.conn.execute(
        "SELECT state, last_error FROM resolution_queue WHERE track_id=?", (tid,)
    ).fetchone()
    assert row["state"] == "quarantined"
    assert row["last_error"]  # machine-readable reason present

    track = db.get_track(tid)
    assert track.quarantine_state == "unresolved"
    assert track.quarantine_reason


def test_drain_is_resumable_and_respects_backoff(db):
    """A backed-off (rate-limited) track is not re-attempted in the same drain,
    and a fresh pending track added later is picked up by a second drain."""
    t1 = _track(db, title="One")

    def rate_limited(track):
        raise ResolutionRateLimited("429")

    worker = ResolutionWorker(db, resolver=rate_limited)
    worker.enqueue(t1)
    assert worker.drain() == 0  # t1 backed off, still pending

    # second drain with a working resolver: t1 is backed off (future), so it is
    # skipped; a newly enqueued t2 resolves.
    t2 = _track(db, title="Two")

    def ok(track):
        return [ResolvedCandidate("tidal", "999", {})]

    worker2 = ResolutionWorker(db, resolver=ok)
    worker2.enqueue(t2)
    assert worker2.drain() == 1
    assert db.conn.execute(
        "SELECT state FROM resolution_queue WHERE track_id=?", (t2,)
    ).fetchone()["state"] == "resolved"
    # t1 remains pending (backed off), never lost
    assert db.conn.execute(
        "SELECT state FROM resolution_queue WHERE track_id=?", (t1,)
    ).fetchone()["state"] == "pending"


def test_drain_limit_caps_work(db):
    ids = [_track(db, title=f"T{i}") for i in range(5)]

    def ok(track):
        return [ResolvedCandidate("tidal", "1", {})]

    worker = ResolutionWorker(db, resolver=ok)
    for tid in ids:
        worker.enqueue(tid)
    assert worker.drain(limit=2) == 2
    remaining = db.conn.execute(
        "SELECT COUNT(*) c FROM resolution_queue WHERE state='pending'"
    ).fetchone()["c"]
    assert remaining == 3


def test_enricher_runs_after_successful_resolve(db):
    tid = _track(db)
    calls = []

    def resolver(track):
        return [ResolvedCandidate("tidal", "1", {})]

    def enricher(database, track):
        calls.append(track.id)

    worker = ResolutionWorker(db, resolver=resolver, enricher=enricher)
    worker.enqueue(tid)
    assert worker.drain() == 1
    assert calls == [tid]


def test_enricher_failure_is_non_fatal(db):
    tid = _track(db)

    def resolver(track):
        return [ResolvedCandidate("tidal", "1", {})]

    def enricher(database, track):
        raise RuntimeError("enrichment blew up")

    worker = ResolutionWorker(db, resolver=resolver, enricher=enricher)
    worker.enqueue(tid)
    # resolve still succeeds; enrichment failure must not fail the resolve
    assert worker.drain() == 1
    assert db.conn.execute(
        "SELECT state FROM resolution_queue WHERE track_id=?", (tid,)
    ).fetchone()["state"] == "resolved"

    """After exhausting retries, a persistently failing (non-rate-limit) resolve
    is quarantined rather than looping forever."""
    tid = _track(db)

    def boom(track):
        raise RuntimeError("upstream 500")

    worker = ResolutionWorker(db, resolver=boom, max_attempts=2)
    worker.enqueue(tid)
    # drain repeatedly, clearing backoff each round to simulate elapsed time
    for _ in range(3):
        worker.drain()
        db.conn.execute(
            "UPDATE resolution_queue SET next_attempt_at=NULL WHERE state='pending'"
        )
        db.conn.commit()

    state = db.conn.execute(
        "SELECT state FROM resolution_queue WHERE track_id=?", (tid,)
    ).fetchone()["state"]
    assert state == "quarantined"
