"""Thematic concept-rule enforcement via an injected LLM judge (Task 5)."""

from tuneshift.composer.models import PlaylistConcept
from tuneshift.composer.reviewer import review_playlist
from tuneshift.sequencer.metadata import TrackMetadata


def _t(tid, title, artist):
    return TrackMetadata(track_id=tid, title=title, artist=artist)


def _fake_judge(verdicts):
    def judge(rule, contexts):
        return {ctx.track_id: verdicts.get(ctx.track_id, "unsure") for ctx in contexts}
    return judge


def test_thematic_violation_maps_to_hard_finding():
    tracks = [_t(1, "Need a Man", "X"), _t(2, "Independent", "Y")]
    concept = PlaylistConcept(theme="Girl Power", hard_rules=["not about wanting a man"])
    judge = _fake_judge({1: "violates", 2: "complies"})

    findings = review_playlist(tracks, concept=concept, artist_lookup={}, llm_judge=judge)
    hard = [f for f in findings if f.severity >= 0.8]
    assert len(hard) == 1
    assert "Need a Man" in hard[0].description
    assert all("Independent" not in f.description for f in findings)


def test_thematic_unsure_maps_to_unknown():
    tracks = [_t(1, "Ambiguous", "X")]
    concept = PlaylistConcept(theme="t", hard_rules=["not about wanting a man"])
    judge = _fake_judge({1: "unsure"})

    findings = review_playlist(tracks, concept=concept, artist_lookup={}, llm_judge=judge)
    assert any(f.severity <= 0.3 and "unsure" in f.description.lower() for f in findings)


def test_thematic_complies_produces_no_finding():
    tracks = [_t(1, "Clean", "X")]
    concept = PlaylistConcept(theme="t", hard_rules=["not about wanting a man"])
    judge = _fake_judge({1: "complies"})

    findings = review_playlist(tracks, concept=concept, artist_lookup={}, llm_judge=judge)
    assert findings == []


def test_thematic_without_judge_reports_needs_llm():
    tracks = [_t(1, "A", "X"), _t(2, "B", "Y")]
    concept = PlaylistConcept(theme="t", hard_rules=["not about wanting a man"])

    findings = review_playlist(tracks, concept=concept, artist_lookup={}, llm_judge=None)
    needs_llm = [f for f in findings if "llm backend" in f.description.lower()]
    assert len(needs_llm) == 1  # once per rule, degradation path (AC3)
