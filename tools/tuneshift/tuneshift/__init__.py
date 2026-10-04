"""tuneshift: canonical playlist manager with cross-platform distribution."""

__version__ = "0.1.0"


class TuneShiftError(Exception):
    """Base exception for all tuneshift operational errors."""


class PlatformSyncError(TuneShiftError):
    """One or more platform operations failed during sync."""

    def __init__(self, failures: list[str]) -> None:
        self.failures = failures
        msg = "; ".join(failures)
        super().__init__(f"Platform sync failed: {msg}")


class PlatformAuthError(TuneShiftError):
    """Platform authentication failed or session expired."""


class DatabaseNotFoundError(TuneShiftError):
    """No database could be resolved, and guessing one would be destructive.

    Creating a database at a guessed path yields an empty library that is
    indistinguishable from a lost collection, so resolution stops here instead.
    """


class PrimaryMarkerError(TuneShiftError):
    """The primary-database marker exists but could not be read.

    Distinct from "unregistered". Unregistered is an answer; this is a failure
    to learn the answer. Collapsing the two would let a permissions problem or
    a half-mounted home directory read as "no primary is registered", and the
    push guard treats that state as a refusal with a named remedy, so a silent
    demotion would route around the guard rather than trip it.
    """


class SequenceIntegrityError(TuneShiftError):
    """A sequencer returned a track set that differs from its input.

    Sequencing reorders tracks; it must never add, drop, or duplicate one.
    Raised instead of returning a corrupted playlist, because a silently
    duplicated track looks plausible and gets persisted.
    """

    def __init__(
        self, context: str, missing: list[int], duplicated: list[int], added: list[int]
    ) -> None:
        self.context = context
        self.missing = missing
        self.duplicated = duplicated
        self.added = added
        parts = []
        if missing:
            parts.append(f"dropped={missing}")
        if duplicated:
            parts.append(f"duplicated={duplicated}")
        if added:
            parts.append(f"added={added}")
        detail = " ".join(parts) or "track multiset changed"
        super().__init__(f"{context} corrupted the track set: {detail}")
