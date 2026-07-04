"""Two-phase per-playlist version selection engine (§6, ACs S1–S5).

This is the single selection engine the reconcile pipeline consolidates onto
(Chunk 3 Task 3.7), retiring the parallel integer ``score_match_with_version`` /
``classify_scores`` path. It runs two ordered phases over an in-memory candidate
list (decoupled from retrieval):

**Phase 1 — hard filter.** A candidate is eliminated before scoring when it is
explicitly unavailable (``available is False``) or fails any *active* hard
preference (``require``/``forbid``). Availability is the source-of-truth gate
behind "it said the track doesn't exist / picked a dead ID": a byte-perfect but
unplayable release must never win over an available one.

**Phase 2 — score survivors.** Each survivor is scored through the single
scoring source (:func:`~tuneshift.matching.base_scoring.score_signals` ->
:class:`~tuneshift.matching.engine.Distance`); soft preferences (``prefer`` /
``avoid``) append their signals and precedence resolves conflicts (Task 3.2).
Lowest distance wins; ties fall through to the deterministic tie-break.

An *active preference* pairs a :class:`~tuneshift.matching.criteria.Criterion`
(which knows how to extract/compare/project a metadata field) with a
:class:`~tuneshift.matching.precedence.PreferenceRef` (the strength/target/scope
the user set). Default preferences => no active prefs => Phase 1 filters only on
availability and Phase 2 reproduces today's base scoring (AC-C5 winner-parity).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from tuneshift.matching.base_scoring import score_signals
from tuneshift.matching.criteria import Criterion, CriterionValue, Verdict
from tuneshift.matching.engine import Distance
from tuneshift.matching.penalties import DEFAULT_WEIGHTS, Weights
from tuneshift.matching.precedence import PreferenceRef

if TYPE_CHECKING:
    from tuneshift.matching.aliases import AliasResolver


@dataclass(frozen=True)
class ActivePreference:
    """A criterion made active by a user preference at some scope.

    The :class:`~tuneshift.matching.precedence.PreferenceRef` carries the
    strength/target/scope; the :class:`~tuneshift.matching.criteria.Criterion`
    knows how to evaluate it against a candidate.
    """

    criterion: Criterion
    ref: PreferenceRef


@dataclass(frozen=True)
class FilteredCandidate:
    """A candidate eliminated in Phase 1, with the reason it was dropped."""

    candidate: Any
    reason: str


@dataclass
class SelectionResult:
    """Outcome of :func:`select_version`.

    ``winner`` is the selected candidate (or ``None`` when every candidate was
    filtered or the input was empty). ``ranked`` is the survivor list scored
    best-first (lowest :class:`Distance` total first). ``filtered`` records the
    Phase-1 eliminations for the plan/explain surfaces.
    """

    winner: Any | None
    winner_distance: Distance | None
    ranked: list[tuple[Any, Distance]] = field(default_factory=list)
    filtered: list[FilteredCandidate] = field(default_factory=list)


def _extract(criterion: Criterion, meta: object) -> CriterionValue | None:
    try:
        return criterion.extract(meta)
    except Exception:
        # A criterion that cannot read a field yields no verdict, never a crash
        # that would abort selection for the whole playlist.
        return None


_EMPTY_VALUE = CriterionValue(raw=None)


def _phase1_filter(
    source: object,
    candidates: list[Any],
    active: list[ActivePreference],
) -> tuple[list[Any], list[FilteredCandidate]]:
    """Eliminate unavailable candidates and any that fail an active hard filter.

    A hard preference (``require``/``forbid``) only eliminates when the criterion
    can extract a value from the candidate (unextractable => no verdict, never a
    silent elimination) and its confidence-gated verdict is ``HARD_REJECT``.
    """

    hard = [ap for ap in active if ap.ref.strength.is_hard]
    survivors: list[Any] = []
    filtered: list[FilteredCandidate] = []

    for cand in candidates:
        if getattr(cand, "available", None) is False:
            filtered.append(FilteredCandidate(cand, "unavailable"))
            continue

        reject: ActivePreference | None = None
        for ap in hard:
            cand_val = _extract(ap.criterion, cand)
            if cand_val is None:
                continue  # unextractable -> no verdict -> cannot eliminate
            src_val = _extract(ap.criterion, source) or _EMPTY_VALUE
            verdict = ap.criterion.compare(src_val, cand_val, ap.ref.strength)
            if verdict is Verdict.HARD_REJECT:
                reject = ap
                break
        if reject is not None:
            filtered.append(
                FilteredCandidate(cand, f"hard:{reject.ref.criterion}={reject.ref.target}")
            )
            continue
        survivors.append(cand)

    return survivors, filtered


def _phase2_score(
    source: object,
    survivors: list[Any],
    *,
    weights: Weights,
    all_durations: list[int] | None,
    prefer: frozenset[str],
    avoid: frozenset[str],
    alias_resolver: "AliasResolver | None",
) -> list[tuple[Any, Distance]]:
    """Score each survivor via the single scoring source, best (lowest) first."""

    scored: list[tuple[Any, Distance]] = []
    for cand in survivors:
        signals = score_signals(
            source,
            cand,
            weights=weights,
            all_durations=all_durations,
            prefer=prefer,
            avoid=avoid,
            alias_resolver=alias_resolver,
        )
        scored.append((cand, Distance(signals)))
    # Stable sort by ascending distance keeps input order for genuine ties, so
    # the deterministic tie-break (Task 3.4) is the only thing that reorders them.
    scored.sort(key=lambda cd: cd[1].total)
    return scored


def select_version(
    source: object,
    candidates: list[Any],
    *,
    active: list[ActivePreference] | tuple[ActivePreference, ...] = (),
    weights: Weights = DEFAULT_WEIGHTS,
    all_durations: list[int] | None = None,
    prefer: frozenset[str] = frozenset(),
    avoid: frozenset[str] = frozenset(),
    alias_resolver: "AliasResolver | None" = None,
) -> SelectionResult:
    """Select the best available release of ``source`` from ``candidates``.

    See the module docstring for the two-phase contract. ``all_durations`` is the
    duration cluster the duration signal calibrates against; when ``None`` it is
    derived from the surviving candidates (unavailable releases, already dropped,
    should not skew the cluster).
    """

    active_list = list(active)
    survivors, filtered = _phase1_filter(source, candidates, active_list)

    if all_durations is None:
        all_durations = [
            d for d in (getattr(c, "duration_seconds", None) for c in survivors) if d
        ]

    ranked = _phase2_score(
        source,
        survivors,
        weights=weights,
        all_durations=all_durations,
        prefer=prefer,
        avoid=avoid,
        alias_resolver=alias_resolver,
    )

    if ranked:
        winner, winner_distance = ranked[0]
    else:
        winner, winner_distance = None, None

    return SelectionResult(
        winner=winner,
        winner_distance=winner_distance,
        ranked=ranked,
        filtered=filtered,
    )


__all__ = [
    "ActivePreference",
    "FilteredCandidate",
    "SelectionResult",
    "select_version",
]
