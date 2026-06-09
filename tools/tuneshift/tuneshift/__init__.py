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
