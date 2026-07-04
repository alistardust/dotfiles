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

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

import yaml

from tuneshift.matching.penalties import SignalPenalty

_WHITELIST_PATH = Path(__file__).with_name("token_whitelist.yaml")


def _fold(token: object) -> str:
    """Lowercase and strip to alphanumerics (``Dolby Atmos`` -> ``dolbyatmos``)."""

    return "".join(ch for ch in str(token).lower() if ch.isalnum())


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


def _soft_signal(name: str, weight: int, verdict: Verdict) -> SignalPenalty | None:
    """Project a *soft* verdict onto a SignalPenalty (None for hard/no-verdict)."""

    if verdict is Verdict.SOFT_PENALTY:
        return SignalPenalty(name, -weight, 1.0, weight)
    if verdict is Verdict.SOFT_BONUS:
        return SignalPenalty(name, weight, 0.0, weight)
    return None


class TokenWhitelist:
    """Committed, axis-grouped set of tokens trusted to drive hard filters.

    Membership and axis lookups fold surface variants onto canonical tokens via
    the alias table, so ``"Dolby Atmos"``, ``"dolby_atmos"`` and ``"atmos"`` all
    resolve to the same whitelisted token on the ``spatial`` axis.
    """

    def __init__(
        self, axes: dict[str, list[str]], aliases: dict[str, str]
    ) -> None:
        self._axis_of: dict[str, str] = {}
        for axis, tokens in axes.items():
            for tok in tokens or ():
                self._axis_of[_fold(tok)] = axis
        self._aliases: dict[str, str] = {
            _fold(k): _fold(v) for k, v in (aliases or {}).items()
        }

    def canonical(self, token: object) -> str:
        folded = _fold(token)
        return self._aliases.get(folded, folded)

    def axis(self, token: object) -> str | None:
        return self._axis_of.get(self.canonical(token))

    def __contains__(self, token: object) -> bool:
        return self.canonical(token) in self._axis_of


@lru_cache(maxsize=1)
def load_token_whitelist() -> TokenWhitelist:
    """Load (and cache) the committed token whitelist from the packaged YAML."""

    data = yaml.safe_load(_WHITELIST_PATH.read_text(encoding="utf-8")) or {}
    return TokenWhitelist(
        axes=data.get("axes") or {}, aliases=data.get("aliases") or {}
    )


def _is_confident(
    *, value: CriterionValue, target: str, whitelist: TokenWhitelist
) -> bool:
    """Whether ``value`` is a confident basis for a hard filter on ``target``.

    Confident iff the value came from a structured field, or ``target`` is a
    committed whitelist token AND the value is not internally ambiguous (it does
    not also carry a *conflicting* token from the same axis — e.g. a title that
    reads "Mono & Stereo Mix" carries two mutually-exclusive ``mix`` tokens).
    """

    if value.structured:
        return True
    if target not in whitelist:
        return False
    axis = whitelist.axis(target)
    same_axis = {t for t in value.tokens if whitelist.axis(t) == axis}
    return len(same_axis) <= 1


def apply_confidence_gate(
    verdict: Verdict,
    *,
    value: CriterionValue,
    target: str,
    whitelist: TokenWhitelist,
) -> Verdict:
    """Demote a HARD verdict to its soft equivalent unless the value is confident.

    Soft/no verdicts pass through unchanged. A confident hard verdict stands; an
    unconfident one is demoted (``HARD_REJECT`` -> ``SOFT_PENALTY``,
    ``HARD_PASS`` -> ``SOFT_BONUS``) so an ambiguous token can nudge the score
    but never eliminate a candidate.
    """

    if not verdict.is_hard:
        return verdict
    if _is_confident(value=value, target=target, whitelist=whitelist):
        return verdict
    return Verdict.SOFT_PENALTY if verdict is Verdict.HARD_REJECT else Verdict.SOFT_BONUS


def _title_ngrams(title: object) -> list[str]:
    """Folded 1- and 2-word n-grams from a free-text title, for token matching."""

    words = [_fold(w) for w in re.split(r"\W+", str(title))]
    words = [w for w in words if w]
    grams = list(words)
    grams += [words[i] + words[i + 1] for i in range(len(words) - 1)]
    return grams


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
        return _fold(token)

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
        return _soft_signal(self.name, self.weight, verdict)


@dataclass
class TitleTokenCriterion:
    """A criterion whose tokens are PARSED from a free-text title (AC-C3).

    Because title tokens are unstructured, every hard verdict is run through the
    committed-whitelist confidence gate before it may eliminate a candidate. An
    off-whitelist token (e.g. "Deluxe") or an internally ambiguous title (e.g.
    "Mono & Stereo Mix") demotes the hard verdict to a soft signal.
    """

    name: str
    target: str
    whitelist: TokenWhitelist
    field_name: str = "title"
    weight: int = 10
    hard_cap: HardCapPolicy = HardCapPolicy.NONE

    def extract_from_title(self, title: object) -> CriterionValue:
        tokens = frozenset(
            self.whitelist.canonical(gram)
            for gram in _title_ngrams(title)
            if gram in self.whitelist
        )
        return CriterionValue(raw=title, tokens=tokens, structured=False)

    def extract(self, meta: object) -> CriterionValue | None:
        raw = getattr(meta, self.field_name, None)
        if not raw:
            return None
        return self.extract_from_title(raw)

    def compare(
        self,
        source: CriterionValue,
        candidate: CriterionValue,
        strength: Strength | None,
    ) -> Verdict:
        satisfied = self.whitelist.canonical(self.target) in candidate.tokens
        verdict = resolve_strength_verdict(strength, satisfied=satisfied)
        return apply_confidence_gate(
            verdict,
            value=candidate,
            target=self.target,
            whitelist=self.whitelist,
        )

    def to_signal(self, verdict: Verdict) -> SignalPenalty | None:
        return _soft_signal(self.name, self.weight, verdict)


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
