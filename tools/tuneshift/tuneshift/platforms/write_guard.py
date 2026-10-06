"""Process-level authority to write to a live streaming platform.

A database is not a sandbox. Platform playlist IDs travel with a copy, so a
push from a copied library reaches the same live playlist as a push from the
original. The only thing that distinguishes them is the registered primary
marker, which records an absolute path rather than deriving one.

Authority is granted once, by the CLI, from the path it already resolved when
it opened the library. It is deliberately not derived here: deriving a library
path from the package location is exactly the arithmetic that made an earlier
version of this guard refuse every legitimate push.

Unset means refuse. A client constructed outside the CLI has no authority, and
a code path that bypasses ``main`` gets the safe answer rather than the
convenient one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tuneshift import TuneShiftError


class NonPrimaryPushError(TuneShiftError):
    """A write to a live platform was attempted without push authority."""


_UNSET = (
    "Refusing to push: no library is active, so there is no way to tell this "
    "from a copy. This is an internal state; a push should only ever be "
    "attempted through the tuneshift CLI."
)

_UNREGISTERED = (
    "Refusing to push: no primary library is registered, so there is no way "
    "to tell this one from a copy. Name this one once with:\n"
    "    tuneshift primary --set <path>"
)


def _mismatch(active: Path, primary: Path) -> str:
    return (
        f"Refusing to push: {active} is not your primary library ({primary}). "
        "Platform IDs travel with a copied database, so this would mutate the "
        "live playlist. Pass --allow-nonprimary-push if you mean it."
    )


def _unreadable(exc: Exception) -> str:
    return (
        f"Refusing to push: {exc}\n"
        "  Until the marker can be read, this library cannot be told apart "
        "from a copy."
    )


@dataclass(frozen=True)
class _Authority:
    """The decision, resolved once at grant time rather than per call."""

    allowed: bool
    error: str | None


_state: _Authority | None = None


def grant_push_authority(active: Path, *, override: bool = False) -> None:
    """Decide, once, whether this run may write to a live platform.

    Resolving here rather than at each call keeps the answer stable for the
    whole run: a marker that changes mid-run cannot flip a push that the user
    was already told would proceed.
    """
    global _state

    if override:
        _state = _Authority(allowed=True, error=None)
        return

    from tuneshift.persistence import primary

    try:
        registered = primary.get_primary_db()
        if registered is None:
            _state = _Authority(allowed=False, error=_UNREGISTERED)
            return
        matches = primary.is_primary_db(Path(active))
    except (TuneShiftError, OSError) as exc:
        # An unreadable marker must not read as permission. Fail-open here
        # would turn any transient permissions problem into silent authority
        # to push to a live account.
        _state = _Authority(allowed=False, error=_unreadable(exc))
        return

    _state = _Authority(
        allowed=matches,
        error=None if matches else _mismatch(Path(active), registered),
    )


def revoke_push_authority() -> None:
    """Return to refusing. Authority does not outlive the run that granted it."""
    global _state
    _state = None


def push_authority_error() -> str | None:
    """Return why a push would be refused, or None if it would be allowed.

    Commands use this to refuse once, with a clear message, before starting a
    per-platform loop that would otherwise report the same refusal repeatedly.
    """
    if _state is None:
        return _UNSET
    return None if _state.allowed else _state.error


def require_push_authority() -> None:
    """Raise unless this run may write to a live platform."""
    error = push_authority_error()
    if error is not None:
        raise NonPrimaryPushError(error)
