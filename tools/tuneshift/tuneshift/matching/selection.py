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
from tuneshift.matching.engine import Distance, Recommendation
from tuneshift.matching.penalties import DEFAULT_WEIGHTS, Weights
from tuneshift.matching.precedence import (
    PreferenceRef,
    derive_precedence,
    resolve_conflict,
)

if TYPE_CHECKING:
    from tuneshift.matching.aliases import AliasResolver

#: Distance band (fraction of the [0,1] scale) within which the weighted score
#: cannot confidently separate two survivors. Inside this band the outcome is
#: decided by per-playlist preference PRECEDENCE (AC-C7), never by a razor-thin
#: weighted difference or a candidate no preference wanted. Also the AC-S3
#: ambiguity threshold surfaced for review (Task 3.4).
AMBIGUITY_DELTA = 0.05


@dataclass(frozen=True)
class IdentityLock:
    """A pinned composite identity (AC-L1): the specific release this track must
    resolve to. Matches a candidate by ``platform_id`` OR ``isrc`` (composite key,
    not ISRC alone), so a lock survives a platform re-ID as long as the ISRC still
    lines up. This is the engine-level view of a lock; DB-backed storage,
    fingerprint matching, and full self-heal land in Chunk 5 (AC-L2..L5).
    """

    platform_id: str | None = None
    isrc: str | None = None

    def matches(self, candidate: object) -> bool:
        if self.platform_id and getattr(candidate, "platform_id", None) == self.platform_id:
            return True
        cand_isrc = getattr(candidate, "isrc", None)
        if self.isrc and cand_isrc and cand_isrc.upper() == self.isrc.upper():
            return True
        return False


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
    Phase-1 eliminations for the plan/explain surfaces. ``decided_by`` names the
    preference criterion that broke a within-delta conflict by precedence (AC-C7),
    or ``None`` when the weighted score alone chose the winner.

    ``lock_applied`` is set when an :class:`IdentityLock` short-circuited normal
    selection. ``needs_review`` + ``review_reason`` flag an outcome the engine
    refuses to guess (a locked release that is unavailable or absent — AC-S2/AC-L3
    — surfaced instead of silently substituted).
    """

    winner: Any | None
    winner_distance: Distance | None
    ranked: list[tuple[Any, Distance]] = field(default_factory=list)
    filtered: list[FilteredCandidate] = field(default_factory=list)
    decided_by: str | None = None
    lock_applied: bool = False
    needs_review: bool = False
    review_reason: str | None = None


def _extract(criterion: Criterion, meta: object) -> CriterionValue | None:
    try:
        return criterion.extract(meta)
    except Exception:
        # A criterion that cannot read a field yields no verdict, never a crash
        # that would abort selection for the whole playlist.
        return None


_EMPTY_VALUE = CriterionValue(raw=None)


def _hard_capped(distance: Distance) -> bool:
    """True when a candidate carries a hard version-reject cap (AC-S4).

    A source-aware version mismatch (live/cover/karaoke/instrumental vs the
    source's studio-original intent) caps the recommendation to REJECT; such a
    candidate must never be recorded as a confident winner.
    """

    return distance.capped_recommendation() is Recommendation.REJECT


def _is_unplayable(candidate: object) -> bool:
    """Whether a candidate is known to be unplayable and must not be selected.

    Covers both a platform's explicit unavailability (``available is False``:
    Spotify ``is_playable``/Tidal ``allowStreaming``) and a premium/tier gate
    (``tier_restricted``). Either state means the release cannot be committed as
    a live match, so it is eliminated in Phase 1 (and excluded from a lock's
    available set) rather than being allowed to win over a playable release.
    ``available is None`` (unknown) is NOT unplayable — never a guess.
    """
    return (
        getattr(candidate, "available", None) is False
        or bool(getattr(candidate, "tier_restricted", False))
    )


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
        if _is_unplayable(cand):
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


def _soft_prefs(active: list[ActivePreference]) -> list[ActivePreference]:
    return [ap for ap in active if ap.ref.strength.is_soft]


def _precedence_of(soft: list[ActivePreference]) -> list[PreferenceRef]:
    """Derive the inspectable per-playlist precedence order from soft prefs.

    Refs are bucketed by their own scope and passed to :func:`derive_precedence`
    under that scope, so the ref objects are preserved by identity (the verdict
    maps key on the same objects)."""

    buckets: dict[str, list[PreferenceRef]] = {"track": [], "playlist": [], "global": []}
    for ap in soft:
        buckets.get(ap.ref.scope, buckets["global"]).append(ap.ref)
    return derive_precedence(
        global_refs=buckets["global"],
        playlist_refs=buckets["playlist"],
        track_refs=buckets["track"],
    )


def _phase2_score(
    source: object,
    survivors: list[Any],
    soft: list[ActivePreference],
    *,
    weights: Weights,
    all_durations: list[int] | None,
    prefer: frozenset[str],
    avoid: frozenset[str],
    alias_resolver: "AliasResolver | None",
) -> list[tuple[Any, Distance, dict[PreferenceRef, Verdict]]]:
    """Score each survivor by base identity distance and record soft verdicts.

    Returns ``(candidate, distance, verdict_map)`` triples sorted best (lowest
    distance) first. The :class:`Distance` is the base identity/similarity match
    quality ONLY — soft preferences are deliberately NOT folded into it, so a
    preference-neutral candidate cannot win merely by dodging every penalty
    (the AC-C7 "candidate neither preference wanted" failure). Instead each soft
    preference's verdict on the candidate is recorded in ``verdict_map`` and used
    to resolve WITHIN the identity cluster by precedence (see
    :func:`_resolve_winner`).
    """

    scored: list[tuple[Any, Distance, dict[PreferenceRef, Verdict]]] = []
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
        vmap: dict[PreferenceRef, Verdict] = {}
        for ap in soft:
            cand_val = _extract(ap.criterion, cand)
            if cand_val is None:
                vmap[ap.ref] = Verdict.NO_VERDICT
                continue
            src_val = _extract(ap.criterion, source) or _EMPTY_VALUE
            vmap[ap.ref] = ap.criterion.compare(src_val, cand_val, ap.ref.strength)
        scored.append((cand, Distance(signals), vmap))
    # Stable sort by ascending distance keeps input order for genuine ties, so
    # the deterministic tie-break (Task 3.4) is the only thing that reorders them.
    scored.sort(key=lambda row: row[1].total)
    return scored


def _resolve_winner(
    scored: list[tuple[Any, Distance, dict[PreferenceRef, Verdict]]],
    soft: list[ActivePreference],
) -> tuple[int, str | None, bool]:
    """Pick the winning index.

    Candidates whose BASE identity distance is within :data:`AMBIGUITY_DELTA` of
    the best form the same-song contention set; within it soft preferences decide
    by precedence (AC-C7, lexicographic favor — a neutral candidate has favor 0
    and loses to one a higher-precedence preference wants). Outside the band the
    better identity match wins outright: a preference selects among comparable
    versions, it never rescues a poor match. Returns ``(winner_index,
    decided_by, ambiguous)`` where ``ambiguous`` is set when 2+ survivors are
    within the band and nothing (preference or lock) resolved the contention —
    the near-tie is surfaced for review rather than guessed (AC-S3).
    """

    if not scored:
        return -1, None, False
    best_total = scored[0][1].total
    cluster = [i for i, row in enumerate(scored) if row[1].total - best_total <= AMBIGUITY_DELTA]
    contested = len(cluster) >= 2
    if not contested or not soft:
        # A lone best is unambiguous; a contested band with no preference to break
        # it is a guess -> flag for review (AC-S3), still surfacing a provisional pick.
        return 0, None, contested

    precedence = _precedence_of(soft)
    candidate_verdicts = {i: scored[i][2] for i in cluster}
    decision = resolve_conflict(candidate_verdicts, precedence)
    if decision.winner is not None:
        return decision.winner, decision.decided_by, False
    # Precedence could not distinguish -> provisional lowest-distance survivor,
    # flagged ambiguous for review.
    return 0, None, True


def _resolve_lock(
    source: object,
    candidates: list[Any],
    lock: IdentityLock,
    *,
    weights: Weights,
    all_durations: list[int] | None,
    prefer: frozenset[str],
    avoid: frozenset[str],
    alias_resolver: "AliasResolver | None",
) -> SelectionResult:
    """Short-circuit selection for a locked composite identity (AC-S2 / AC-L1).

    The locked release wins outright if it is present and available. If the
    locked release is present but unavailable, or absent entirely, the engine
    refuses to substitute another release and surfaces the mapping for review
    (self-heal with same-identity candidates is Chunk 5, AC-L3).
    """

    matched = [c for c in candidates if lock.matches(c)]
    if not matched:
        return SelectionResult(
            winner=None,
            winner_distance=None,
            lock_applied=True,
            needs_review=True,
            review_reason="locked_missing",
        )

    available = [c for c in matched if not _is_unplayable(c)]
    if not available:
        return SelectionResult(
            winner=None,
            winner_distance=None,
            filtered=[FilteredCandidate(c, "unavailable") for c in matched],
            lock_applied=True,
            needs_review=True,
            review_reason="locked_unavailable",
        )

    # Prefer an exact platform-id match among available locked releases, else the
    # first (composite identity should resolve to a single recording).
    winner = next(
        (c for c in available if lock.platform_id and getattr(c, "platform_id", None) == lock.platform_id),
        available[0],
    )
    if all_durations is None:
        all_durations = [d for d in (getattr(c, "duration_seconds", None) for c in matched) if d]
    distance = Distance(
        score_signals(
            source,
            winner,
            weights=weights,
            all_durations=all_durations,
            prefer=prefer,
            avoid=avoid,
            alias_resolver=alias_resolver,
        )
    )
    return SelectionResult(
        winner=winner,
        winner_distance=distance,
        ranked=[(winner, distance)],
        lock_applied=True,
        decided_by="lock",
    )


def select_version(
    source: object,
    candidates: list[Any],
    *,
    active: list[ActivePreference] | tuple[ActivePreference, ...] = (),
    lock: IdentityLock | None = None,
    weights: Weights = DEFAULT_WEIGHTS,
    all_durations: list[int] | None = None,
    prefer: frozenset[str] = frozenset(),
    avoid: frozenset[str] = frozenset(),
    alias_resolver: "AliasResolver | None" = None,
) -> SelectionResult:
    """Select the best available release of ``source`` from ``candidates``.

    See the module docstring for the two-phase contract. When a ``lock`` is
    supplied the locked composite identity short-circuits scoring (AC-S2).
    ``all_durations`` is the duration cluster the duration signal calibrates
    against; when ``None`` it is derived from the surviving candidates
    (unavailable releases, already dropped, should not skew the cluster).
    """

    if lock is not None:
        return _resolve_lock(
            source,
            candidates,
            lock,
            weights=weights,
            all_durations=all_durations,
            prefer=prefer,
            avoid=avoid,
            alias_resolver=alias_resolver,
        )

    active_list = list(active)
    survivors, filtered = _phase1_filter(source, candidates, active_list)

    if all_durations is None:
        all_durations = [
            d for d in (getattr(c, "duration_seconds", None) for c in survivors) if d
        ]

    soft = _soft_prefs(active_list)
    scored = _phase2_score(
        source,
        survivors,
        soft,
        weights=weights,
        all_durations=all_durations,
        prefer=prefer,
        avoid=avoid,
        alias_resolver=alias_resolver,
    )

    # AC-S4: a source-aware version mismatch (live/cover/karaoke/instrumental vs
    # studio-original intent) carries a hard REJECT cap. Such a candidate must
    # never win confidently over a clean survivor — down-rank all capped rows
    # below the clean ones. Only when NO clean survivor exists is a capped row a
    # provisional winner, and then the result is flagged for review, never
    # recorded as a confident match.
    clean = [row for row in scored if not _hard_capped(row[1])]
    capped = [row for row in scored if _hard_capped(row[1])]

    version_mismatch = False
    if clean:
        winner_index, decided_by, ambiguous = _resolve_winner(clean, soft)
        chosen = clean[winner_index] if winner_index >= 0 else None
        ordered = [chosen, *[r for r in clean if r is not chosen], *capped] if chosen else [*clean, *capped]
    elif capped:
        winner_index, decided_by, ambiguous = 0, None, False
        version_mismatch = True
        chosen = capped[0]
        ordered = capped
    else:
        winner_index, decided_by, ambiguous = -1, None, False
        chosen = None
        ordered = []

    ranked = [(cand, dist) for cand, dist, _ in ordered]
    if chosen is not None:
        winner, winner_distance = chosen[0], chosen[1]
    else:
        winner, winner_distance = None, None

    if version_mismatch:
        needs_review, review_reason = True, "version_mismatch"
    elif ambiguous:
        needs_review, review_reason = True, "ambiguous"
    else:
        needs_review, review_reason = False, None

    return SelectionResult(
        winner=winner,
        winner_distance=winner_distance,
        ranked=ranked,
        filtered=filtered,
        decided_by=decided_by,
        needs_review=needs_review,
        review_reason=review_reason,
    )


__all__ = [
    "ActivePreference",
    "FilteredCandidate",
    "IdentityLock",
    "SelectionResult",
    "select_version",
]
