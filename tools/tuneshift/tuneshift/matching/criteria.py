"""Typed criterion registry — the general metadata-driven matching model (§5).

This module replaces the ad-hoc two-string-list (`prefer`/`avoid`) mechanism
with a registry of typed criteria. Each criterion is a self-contained unit:

* ``extract(meta)``   — pull a typed :class:`CriterionValue` from a track-like
  metadata object (or ``None`` when the field is absent).
* ``compare(source, candidate, strength)`` — given the active preference
  strength (or ``None`` when no preference references this criterion), return a
  :class:`Verdict`.
* ``to_signal(verdict)`` — project a *soft* verdict into the existing
  :class:`~tuneshift.matching.penalties.SignalPenalty` consumed by
  :class:`~tuneshift.matching.engine.Distance`, or ``None``.
* ``hard_cap``        — how a *hard* verdict caps the recommendation.

**Parity-critical contract (AC-C1 / AC-C5 winner-parity):** a criterion that is
NOT referenced by an active preference returns :attr:`Verdict.NO_VERDICT`, and
``to_signal`` returns ``None`` for it — it contributes NOTHING to the
``Distance`` (not a zero-weight signal, literally no signal object). Only
criteria referenced by an active preference (at any scope) may emit a signal.
Adding a new criterion is therefore registration + config, never bespoke
scoring code, and cannot perturb today's scores until a preference opts in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Iterator, Protocol, runtime_checkable

from tuneshift.matching.penalties import SignalPenalty


class Strength(str, Enum):
    """The four preference strengths a user may attach to any criterion.

    ``require``/``forbid`` are *hard* (phase-1 candidate elimination);
    ``prefer``/``avoid`` are *soft* (phase-2 weighted score adjustment).
    """

    REQUIRE = "require"
    PREFER = "prefer"
    AVOID = "avoid"
    FORBID = "forbid"

    @property
    def is_hard(self) -> bool:
        return self in (Strength.REQUIRE, Strength.FORBID)

    @property
    def is_soft(self) -> bool:
        return self in (Strength.PREFER, Strength.AVOID)


class Verdict(Enum):
    """The outcome of comparing a candidate against the source for a criterion."""

    NO_VERDICT = auto()   # not referenced by an active preference, or unextractable
    NEUTRAL = auto()      # referenced, but the candidate neither helped nor hurt
    SOFT_BONUS = auto()   # soft preference satisfied -> reward
    SOFT_PENALTY = auto() # soft preference violated -> penalize
    HARD_PASS = auto()    # hard filter satisfied (require met / forbid absent)
    HARD_REJECT = auto()  # hard filter failed -> eliminate the candidate

    @property
    def is_hard(self) -> bool:
        return self in (Verdict.HARD_PASS, Verdict.HARD_REJECT)

    @property
    def is_soft(self) -> bool:
        return self in (Verdict.SOFT_BONUS, Verdict.SOFT_PENALTY)


class HardCapPolicy(str, Enum):
    """How a criterion's HARD verdict caps the recommendation for a candidate.

    Mirrors the existing recommendation caps in
    :class:`~tuneshift.matching.engine.Distance`: a hard rejection forces
    ``REJECT``; a soft-substitute cap limits to ``SUGGEST``; ``NONE`` applies no
    cap (the criterion only ever contributes soft signals).
    """

    REJECT = "reject"
    SUGGEST = "suggest"
    NONE = "none"


@dataclass(frozen=True)
class CriterionValue:
    """A typed value extracted from a track's metadata for one criterion.

    ``raw`` is the underlying value (str, int, list, ...). ``tokens`` is an
    optional normalized token set for token-based criteria (audio-mode,
    recording-class, edition ...). ``structured`` marks the value as coming from
    a structured metadata field rather than a parsed title token — this drives
    the AC-C3 confidence gate (only structured or whitelisted-token values may
    drive a *hard* filter).
    """

    raw: Any
    tokens: frozenset[str] = field(default_factory=frozenset)
    structured: bool = False


@runtime_checkable
class Criterion(Protocol):
    """A registered typed matching/preference criterion (AC-C1)."""

    name: str
    hard_cap: HardCapPolicy

    def extract(self, meta: object) -> CriterionValue | None: ...

    def compare(
        self,
        source: CriterionValue,
        candidate: CriterionValue,
        strength: Strength | None,
    ) -> Verdict: ...

    def to_signal(self, verdict: Verdict) -> SignalPenalty | None: ...


def resolve_strength_verdict(
    strength: Strength | None, *, satisfied: bool
) -> Verdict:
    """Map an active preference strength + candidate satisfaction to a verdict.

    ``satisfied`` means "the candidate has the property the preference is about"
    (e.g. it carries the atmos token for a ``spatial=atmos`` preference). This is
    the single routing table every criterion shares, so a new criterion needs
    only supply extraction + a satisfaction test — never bespoke verdict logic.
    """

    if strength is None:
        return Verdict.NO_VERDICT
    if strength is Strength.REQUIRE:
        return Verdict.HARD_PASS if satisfied else Verdict.HARD_REJECT
    if strength is Strength.FORBID:
        return Verdict.HARD_REJECT if satisfied else Verdict.HARD_PASS
    if strength is Strength.PREFER:
        return Verdict.SOFT_BONUS if satisfied else Verdict.SOFT_PENALTY
    # AVOID
    return Verdict.SOFT_PENALTY if satisfied else Verdict.SOFT_BONUS


@dataclass
class TokenCriterion:
    """A reusable token-membership criterion (audio-mode, edition, class, ...).

    Extraction reads a token list off ``field_name`` on the metadata object; the
    candidate is *satisfied* when it carries ``target`` (case-insensitive,
    non-alphanumerics folded so ``DOLBY_ATMOS`` matches ``dolby_atmos``). Verdict
    routing is delegated to :func:`resolve_strength_verdict`; soft verdicts
    project to a :class:`SignalPenalty` with the criterion's ``weight`` while
    hard verdicts carry no soft signal (they cap via ``hard_cap``).

    ``structured`` marks values as coming from a structured field so they may
    drive a hard filter under the AC-C3 confidence gate.
    """

    name: str
    field_name: str
    target: str
    weight: int = 10
    hard_cap: HardCapPolicy = HardCapPolicy.NONE
    structured: bool = True

    def _norm(self, token: object) -> str:
        return "".join(ch for ch in str(token).lower() if ch.isalnum())

    def extract(self, meta: object) -> CriterionValue | None:
        raw = getattr(meta, self.field_name, None)
        if not raw:
            return None
        if isinstance(raw, (list, tuple, set, frozenset)):
            tokens = frozenset(self._norm(t) for t in raw if t)
        else:
            tokens = frozenset({self._norm(raw)})
        if not tokens:
            return None
        return CriterionValue(raw=raw, tokens=tokens, structured=self.structured)

    def compare(
        self,
        source: CriterionValue,
        candidate: CriterionValue,
        strength: Strength | None,
    ) -> Verdict:
        satisfied = self._norm(self.target) in candidate.tokens
        return resolve_strength_verdict(strength, satisfied=satisfied)

    def to_signal(self, verdict: Verdict) -> SignalPenalty | None:
        if verdict is Verdict.SOFT_PENALTY:
            return SignalPenalty(self.name, -self.weight, 1.0, self.weight)
        if verdict is Verdict.SOFT_BONUS:
            return SignalPenalty(self.name, self.weight, 0.0, self.weight)
        return None


class CriterionRegistry:
    """An ordered, name-unique collection of registered criteria.

    Order is registration order, which fixes a stable default precedence; the
    per-playlist precedence override is applied by the selection engine (AC-C4),
    not here.
    """

    def __init__(self) -> None:
        self._by_name: dict[str, Criterion] = {}

    def register(self, criterion: Criterion) -> None:
        name = criterion.name
        if name in self._by_name:
            raise ValueError(f"criterion {name!r} is already registered")
        self._by_name[name] = criterion

    def get(self, name: str) -> Criterion:
        return self._by_name[name]

    def all(self) -> tuple[Criterion, ...]:
        return tuple(self._by_name.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._by_name.keys())

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def __iter__(self) -> Iterator[Criterion]:
        return iter(self._by_name.values())

    def __len__(self) -> int:
        return len(self._by_name)
