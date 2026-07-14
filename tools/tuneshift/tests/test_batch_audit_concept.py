"""Concept enforcement wired into batch/audit/compose (parity extension)."""

from __future__ import annotations

from pathlib import Path

from tuneshift.db import Database
from tuneshift.models import Track


def _playlist_with_era_rule(tmp_path: Path, year: int):
    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("Girl Power")
    tid = db.add_track(Track(title="Old Song", artist="Artist", album="Album"))
    db.add_track_to_playlist(pid, tid, 0)
    db.upsert_track_platform_metadata(tid, "tidal", "1", release_year=year)
    db.set_preferences(pid, {
        "concept": {
            "theme": "t", "hard_rules": ["released 1993-2003"], "soft_rules": [],
        }
    })
    return db, pid, tid


def test_batch_review_fixes_removes_out_of_era_track(tmp_path: Path):
    from tuneshift.commands.batch_cmd import plan_review_fixes

    db, pid, tid = _playlist_with_era_rule(tmp_path, year=1975)
    ops = plan_review_fixes(db, pid)  # no llm_judge: era is deterministic
    rm = [o for o in ops if o.action == "rm" and o.track_id == tid]
    assert len(rm) == 1
    assert "outside" in rm[0].reason


def test_batch_review_fixes_respects_acceptance(tmp_path: Path):
    from tuneshift.commands.batch_cmd import plan_review_fixes

    db, pid, tid = _playlist_with_era_rule(tmp_path, year=1975)
    db.add_concept_acceptance(pid, tid, "released 1993-2003")
    ops = plan_review_fixes(db, pid)
    assert not [o for o in ops if o.action == "rm" and o.track_id == tid]


def test_batch_review_fixes_keeps_in_era_track(tmp_path: Path):
    from tuneshift.commands.batch_cmd import plan_review_fixes

    db, pid, tid = _playlist_with_era_rule(tmp_path, year=1998)
    assert not [o for o in plan_review_fixes(db, pid) if o.action == "rm"]


def test_rebuild_removes_out_of_era_track(tmp_path: Path):
    from tuneshift.commands.batch_cmd import plan_rebuild

    db, pid, tid = _playlist_with_era_rule(tmp_path, year=1975)
    ops = plan_rebuild(db, pid, count=1, fresh=False)
    assert any(o.action == "rm" and o.track_id == tid for o in ops)


def test_audit_concept_reports_era_violation(tmp_path: Path):
    from tuneshift.commands.audit_cmd import _audit_concept

    db, pid, tid = _playlist_with_era_rule(tmp_path, year=1975)
    playlist = db.find_playlist_by_name("Girl Power")
    findings = _audit_concept(db, playlist)
    assert any("VIOLATION" in f and "outside" in f for f in findings)


def test_compose_playlist_threads_year_lookup(tmp_path: Path):
    from tuneshift.composer import compose_playlist
    from tuneshift.composer.models import PlaylistConcept
    from tuneshift.sequencer.metadata import TrackMetadata

    tracks = [TrackMetadata(track_id=1, title="Old Song", artist="Artist")]
    concept = PlaylistConcept(theme="t", hard_rules=["released 1993-2003"])
    result = compose_playlist(
        tracks, narrative="intro", concept=concept, artist_lookup={},
        year_lookup={1: 1975},
    )
    descs = " ".join(f.description for f in result.review_findings)
    assert "outside" in descs  # era rule enforced during composition
