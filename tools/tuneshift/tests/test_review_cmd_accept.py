"""Acceptance suppression across reviews, incl. LLM non-determinism (Task 7)."""

from __future__ import annotations

from pathlib import Path

from tuneshift.composer.models import PlaylistConcept
from tuneshift.composer.reviewer import review_playlist
from tuneshift.sequencer.metadata import TrackMetadata


def _t(tid, title, artist):
    return TrackMetadata(track_id=tid, title=title, artist=artist)


def test_era_finding_suppressed_after_acceptance():
    tracks = [_t(1, "Old", "X")]
    concept = PlaylistConcept(theme="t", hard_rules=["released 1993-2003"])
    year_lookup = {1: 1975}

    before = review_playlist(
        tracks, concept=concept, artist_lookup={}, year_lookup=year_lookup
    )
    assert any(f.severity >= 0.8 for f in before)  # violation present

    accepted = {(1, "released 1993-2003")}
    after = review_playlist(
        tracks, concept=concept, artist_lookup={},
        year_lookup=year_lookup, accepted=accepted,
    )
    assert all(f.severity < 0.8 for f in after)  # suppressed


def test_acceptance_survives_flipping_llm_verdict():
    """AC5: an accepted (track, rule) stays suppressed even if the LLM flips."""
    tracks = [_t(1, "Ambiguous", "X")]
    concept = PlaylistConcept(theme="t", hard_rules=["not about wanting a man"])
    accepted = {(1, "not about wanting a man")}

    state = {"n": 0}

    def flipping_judge(rule, contexts):
        state["n"] += 1
        verdict = "violates" if state["n"] % 2 else "complies"
        return {ctx.track_id: verdict for ctx in contexts}

    for _ in range(4):
        findings = review_playlist(
            tracks, concept=concept, artist_lookup={},
            llm_judge=flipping_judge, accepted=accepted,
        )
        assert findings == []  # accepted -> never flagged regardless of verdict


def test_acceptance_scoped_to_its_rule_only():
    tracks = [_t(1, "Old", "X")]
    concept = PlaylistConcept(
        theme="t",
        hard_rules=["released 1993-2003", "not about wanting a man"],
    )
    year_lookup = {1: 1975}
    # Accept only the era rule; the thematic rule should still surface.
    accepted = {(1, "released 1993-2003")}

    def judge(rule, contexts):
        return {ctx.track_id: "violates" for ctx in contexts}

    findings = review_playlist(
        tracks, concept=concept, artist_lookup={},
        year_lookup=year_lookup, llm_judge=judge, accepted=accepted,
    )
    descs = " ".join(f.description for f in findings)
    assert "outside" not in descs  # era finding suppressed
    assert "violates it" in descs  # thematic finding still present


def test_review_cmd_accept_persists_across_calls(tmp_path: Path):
    """End-to-end through handle_review + the DB acceptance store."""
    from types import SimpleNamespace

    from tuneshift.commands.compose_cmd import handle_review
    from tuneshift.db import Database
    from tuneshift.models import Track

    db = Database(tmp_path / "t.db")
    pid = db.create_playlist("Girl Power")
    tid = db.add_track(Track(title="Old Song", artist="Artist", album="Album"))
    db.add_track_to_playlist(pid, tid, 0)
    db.upsert_track_platform_metadata(tid, "tidal", "1", release_year=1975)
    db.set_preferences(pid, {
        "concept": {
            "theme": "Girl Power",
            "hard_rules": ["released 1993-2003"],
            "soft_rules": [],
        }
    })

    base = dict(playlist="Girl Power", fix=False, list_accepted=False, rule=None)

    # 1) initial review: era violation present
    rc = handle_review(SimpleNamespace(accept_track=None, **base), db)
    assert rc == 0

    # 2) accept the era rule for the track
    rc = handle_review(
        SimpleNamespace(accept_track=tid, **{**base, "rule": "released 1993-2003"}),
        db,
    )
    assert rc == 0
    assert (tid, "released 1993-2003") in db.get_concept_acceptances(pid)

    # 3) acceptance persists (survives a fresh Database handle on the same file)
    db2 = Database(tmp_path / "t.db")
    assert (tid, "released 1993-2003") in db2.get_concept_acceptances(pid)
