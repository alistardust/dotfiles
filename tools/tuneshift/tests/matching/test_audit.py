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
