"""Chunk 1 integration gate: end-to-end library-first flow (spec §4.3, §4.4).

Real database, stubbed network. Exercises the whole data-layer slice wired
together — the add path, the resolution queue, the worker, quarantine, coverage,
and selection eligibility — the way the tool actually runs it, per AC-D6
(quarantine↔active) and AC-D5/AC-X2 (resumable, rate-limited backfill).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from tuneshift.commands.add_cmd import handle_add
from tuneshift.db import Database
from tuneshift.library.worker import (
    ResolutionRateLimited,
    ResolutionWorker,
    ResolvedCandidate,
)


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "tuneshift.db")


def _add(db: Database, playlist: str, title: str, artist: str) -> int:
    args = SimpleNamespace(playlist=playlist, title=title, artist=artist, album=None)
    rc = handle_add(args, db)
    assert rc == 0
    return db.find_track(title, artist, None).id


def _queue_state(db: Database, track_id: int) -> str | None:
    row = db.conn.execute(
        "SELECT state FROM resolution_queue WHERE track_id=?", (track_id,)
    ).fetchone()
    return row["state"] if row else None


def test_add_unresolvable_then_resolve_and_approve(db: Database) -> None:
    """add → quarantine (unresolvable) → not selectable → resolve → selectable;
    and a separately-quarantined track → manual approve → selectable (AC-D6)."""
    pid = db.create_playlist("Mix")
    tid = _add(db, "Mix", "Obscure B-side", "Nobody")

    # library-first: enqueued pending, placed locally, never pushed
    assert _queue_state(db, tid) == "pending"
    assert tid in db.get_selectable_track_ids(pid)  # not yet quarantined

    # drain with a resolver that finds nothing → quarantine
    unresolvable = ResolutionWorker(db, resolver=lambda t: [])
    assert unresolvable.drain() == 0
    assert _queue_state(db, tid) == "quarantined"
    assert db.get_track(tid).quarantine_state == "unresolved"
    assert tid not in db.get_selectable_track_ids(pid)  # AC-D6 exclusion

    # it shows on the triage surface with a reason
    listed = {q["track_id"]: q for q in db.get_quarantined_tracks()}
    assert tid in listed and "no_candidate" in listed[tid]["reason"]

    # RESOLVE path: the track is later found. Reopen the queue and drain with a
    # working resolver → resolved, quarantine cleared by the worker → selectable.
    db.set_resolution_state(tid, "pending", next_attempt_at=None)
    found = ResolutionWorker(
        db, resolver=lambda t: [ResolvedCandidate("tidal", "555", {"audio_modes": ["STEREO"]})]
    )
    assert found.drain() == 1
    assert _queue_state(db, tid) == "resolved"
    assert db.get_track(tid).quarantine_state is None
    assert tid in db.get_selectable_track_ids(pid)
    assert db.get_track_candidates(tid, platform="tidal")

    # APPROVE path: a different track quarantined, released by manual approval
    tid2 = _add(db, "Mix", "Weird Edit", "Someone")
    ResolutionWorker(db, resolver=lambda t: []).drain()
    assert tid2 not in db.get_selectable_track_ids(pid)
    # manual approve = clear the quarantine (library-state mutation, AC-D6)
    db.set_track_fields(
        tid2, {"quarantine_state": None, "quarantine_reason": None}, source="approve"
    )
    assert tid2 in db.get_selectable_track_ids(pid)


def test_batch_add_under_throttle_resumes(db: Database) -> None:
    """Batch-add under a throttled resolver: the first attempt on every track is
    rate-limited (never lost), a later drain resumes and resolves all of them
    (AC-D5 resumable, AC-X2 rate-limit-safe)."""
    db.create_playlist("Batch")
    titles = [f"Song {i}" for i in range(6)]
    tids = [_add(db, "Batch", t, "Artist") for t in titles]

    # all enqueued, none pushed
    for tid in tids:
        assert _queue_state(db, tid) == "pending"

    # resolver: rate-limit the FIRST call for each track, succeed thereafter
    seen: set[int] = set()

    def throttled(track):
        if track.id not in seen:
            seen.add(track.id)
            raise ResolutionRateLimited("429 first-touch throttle")
        return [ResolvedCandidate("tidal", f"t{track.id}", {})]

    worker = ResolutionWorker(db, resolver=throttled)

    # first drain: every track rate-limited → all backed off, still pending
    assert worker.drain() == 0
    pending_after_first = db.conn.execute(
        "SELECT COUNT(*) c FROM resolution_queue WHERE state='pending'"
    ).fetchone()["c"]
    assert pending_after_first == len(tids), "rate-limited work must not be lost"

    # simulate elapsed backoff, then resume
    db.conn.execute("UPDATE resolution_queue SET next_attempt_at=NULL")
    db.conn.commit()
    assert worker.drain() == len(tids)

    # all resolved, all have candidates, none quarantined
    report = db.coverage_report()
    assert report["resolved"] == len(tids)
    assert report["quarantined"] == 0
    assert report["coverage"] == pytest.approx(1.0)
    for tid in tids:
        assert db.get_track_candidates(tid, platform="tidal")


def test_kill_mid_batch_resume_completes_rest(db: Database) -> None:
    """Killing a drain partway (limit) leaves the rest pending; a later drain
    completes them — no track is dropped (AC-D5 forced-reboot survivability)."""
    db.create_playlist("Batch")
    tids = [_add(db, "Batch", f"S{i}", "Artist") for i in range(5)]

    worker = ResolutionWorker(
        db, resolver=lambda t: [ResolvedCandidate("tidal", f"t{t.id}", {})]
    )
    # "crash" after resolving 2
    assert worker.drain(limit=2) == 2
    remaining = db.conn.execute(
        "SELECT COUNT(*) c FROM resolution_queue WHERE state='pending'"
    ).fetchone()["c"]
    assert remaining == 3

    # resume
    assert worker.drain() == 3
    assert db.coverage_report()["resolved"] == len(tids)
