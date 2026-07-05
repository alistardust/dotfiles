"""Tests for the MatchAudit + availability model."""
from __future__ import annotations

import pytest

from tuneshift.matching.audit import (
    Availability,
    MatchAudit,
    ReasonCode,
    RejectedCandidate,
)


def test_availability_states_are_unique_and_registered():
    states = [
        Availability.EXACT_AVAILABLE,
        Availability.EXACT_UNAVAILABLE,
        Availability.SUBSTITUTE_AVAILABLE,
        Availability.AMBIGUOUS,
        Availability.NOT_FOUND,
    ]
    assert len(set(states)) == len(states)
    assert set(states) == Availability.ALL


def test_audit_rejects_unknown_availability():
    with pytest.raises(ValueError):
        MatchAudit(availability="teleported", reason_code=ReasonCode.MATCHED)


def test_audit_minimal_construction():
    a = MatchAudit(
        availability=Availability.NOT_FOUND,
        reason_code=ReasonCode.NO_CANDIDATES,
    )
    assert a.chosen_platform_id is None
    assert a.rejected == []
    assert a.locked is False


def test_audit_round_trips_through_json():
    audit = MatchAudit(
        availability=Availability.EXACT_AVAILABLE,
        reason_code=ReasonCode.MATCHED,
        chosen_platform_id="tid-123",
        chosen_score=97,
        decisive_signal="isrc",
        distance=0.03,
        rejected=[
            RejectedCandidate("tid-999", "Song (Live)", "Artist", "Live Album", 0, "version:reject"),
            RejectedCandidate("tid-888", "Song", "Artist", "Compilation", 60, "album"),
        ],
        locked=False,
        note="clear winner",
    )
    restored = MatchAudit.from_json(audit.to_json())
    assert restored == audit


def test_rejected_candidate_round_trips():
    rc = RejectedCandidate("p1", "T", "A", "Al", 42, "duration")
    assert RejectedCandidate.from_dict(rc.as_dict()) == rc


def test_locked_audit_serializes_flag():
    audit = MatchAudit(
        availability=Availability.EXACT_UNAVAILABLE,
        reason_code=ReasonCode.LOCKED,
        chosen_platform_id="tid-1",
        locked=True,
    )
    assert MatchAudit.from_json(audit.to_json()).locked is True


def test_as_dict_expands_rejected_candidates():
    audit = MatchAudit(
        availability=Availability.AMBIGUOUS,
        reason_code=ReasonCode.AMBIGUOUS_TOP,
        rejected=[RejectedCandidate("p1", "T", "A", "Al", 80, "title")],
    )
    d = audit.as_dict()
    assert isinstance(d["rejected"][0], dict)
    assert d["rejected"][0]["platform_id"] == "p1"


# --- Chunk 6: enriched explain fields (AC-CLI3 / AC-CLI5) ---
from tuneshift.matching.audit import CriterionOutcome, SignalContribution  # noqa: E402


def test_criterion_outcome_round_trips():
    c = CriterionOutcome(
        criterion="spatial", strength="prefer", kind="soft", target="atmos", fired=True
    )
    assert CriterionOutcome.from_dict(c.as_dict()) == c


def test_signal_contribution_round_trips():
    s = SignalContribution(name="duration", contribution=0.1234, weight=2.0)
    assert SignalContribution.from_dict(s.as_dict()) == s


def test_enriched_audit_round_trips_through_json():
    audit = MatchAudit(
        availability=Availability.EXACT_AVAILABLE,
        reason_code=ReasonCode.MATCHED,
        chosen_platform_id="tid-1",
        chosen_score=95,
        criteria=[
            CriterionOutcome("spatial", "require", "hard", "atmos", fired=True),
            CriterionOutcome("recording", "prefer", "soft", "studio", fired=False),
        ],
        signal_breakdown=[
            SignalContribution("title", 0.0, 3.0),
            SignalContribution("duration", 0.05, 2.0),
        ],
        tie_break="spatial",
        rejected=[
            RejectedCandidate(
                "tid-9", "S", "A", "Al", 0, "hard:spatial=atmos",
                rejection="hard_filter", rejection_detail="spatial=atmos",
            ),
        ],
    )
    restored = MatchAudit.from_json(audit.to_json())
    assert restored == audit


def test_as_dict_expands_criteria_and_breakdown():
    audit = MatchAudit(
        availability=Availability.EXACT_AVAILABLE,
        reason_code=ReasonCode.MATCHED,
        criteria=[CriterionOutcome("spatial", "prefer", "soft", "atmos", fired=True)],
        signal_breakdown=[SignalContribution("title", 0.0, 3.0)],
    )
    d = audit.as_dict()
    assert isinstance(d["criteria"][0], dict)
    assert d["criteria"][0]["criterion"] == "spatial"
    assert isinstance(d["signal_breakdown"][0], dict)
    assert d["signal_breakdown"][0]["name"] == "title"


def test_backward_compatible_from_dict_without_new_fields():
    # Audits persisted before Chunk 6 have no criteria/signal_breakdown/tie_break.
    legacy = {
        "availability": Availability.EXACT_AVAILABLE,
        "reason_code": ReasonCode.MATCHED,
        "chosen_platform_id": "tid-1",
        "chosen_score": 90,
        "rejected": [{"platform_id": "tid-2", "title": "T", "artist": "A",
                      "album": "Al", "score": 70, "decisive_signal": "title"}],
    }
    audit = MatchAudit.from_dict(legacy)
    assert audit.criteria == []
    assert audit.signal_breakdown == []
    assert audit.tie_break is None
    # Legacy rejected candidate deserializes with no rejection class.
    assert audit.rejected[0].rejection is None
