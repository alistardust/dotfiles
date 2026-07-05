"""Chunk 2 Task 2.5: deterministic tie-break (AC-C6).

When candidates survive filtering and conflict resolution still tied, the
winner is chosen by a documented, deterministic order — never a silent
arbitrary pick:

    earliest original release-year  ->  highest availability  ->  stable ID

Each tier only breaks ties the previous tier left. The result names the tier
that decided so ``explain`` can show *why* this release won a tie.
"""

from __future__ import annotations

import pytest

from tuneshift.matching.tiebreak import TieCandidate, tie_break


def test_earliest_release_year_wins():
    result = tie_break([
        TieCandidate(id="remaster", release_year=2015, availability_rank=9),
        TieCandidate(id="original", release_year=1966, availability_rank=1),
    ])
    assert result.winner == "original"
    assert result.decided_by == "release-year"


def test_availability_breaks_year_tie():
    result = tie_break([
        TieCandidate(id="rare", release_year=1999, availability_rank=1),
        TieCandidate(id="common", release_year=1999, availability_rank=5),
    ])
    assert result.winner == "common"
    assert result.decided_by == "availability"


def test_stable_id_is_final_deterministic_tiebreak():
    result = tie_break([
        TieCandidate(id="zzz", release_year=2000, availability_rank=3),
        TieCandidate(id="aaa", release_year=2000, availability_rank=3),
    ])
    assert result.winner == "aaa"
    assert result.decided_by == "stable-id"


def test_missing_year_sorts_after_known_year():
    result = tie_break([
        TieCandidate(id="unknown", release_year=None, availability_rank=9),
        TieCandidate(id="dated", release_year=2010, availability_rank=0),
    ])
    assert result.winner == "dated"
    assert result.decided_by == "release-year"


def test_result_is_order_independent():
    a = TieCandidate(id="a", release_year=1980, availability_rank=2)
    b = TieCandidate(id="b", release_year=1980, availability_rank=5)
    c = TieCandidate(id="c", release_year=1975, availability_rank=1)
    assert tie_break([a, b, c]).winner == "c"
    assert tie_break([b, c, a]).winner == "c"
    assert tie_break([c, b, a]).winner == "c"


def test_single_candidate_is_sole_winner():
    result = tie_break([TieCandidate(id="only", release_year=1990)])
    assert result.winner == "only"
    assert result.decided_by == "sole-candidate"


def test_empty_raises():
    with pytest.raises(ValueError):
        tie_break([])
