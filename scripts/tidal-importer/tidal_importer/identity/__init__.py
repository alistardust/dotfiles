"""Track identity resolution system."""

from tidal_importer.identity.confidence import compute_confidence
from tidal_importer.identity.db import IdentityDB
from tidal_importer.identity.models import (
    Album,
    Artist,
    ConfidenceTier,
    Evidence,
    PlatformTrack,
    Recording,
    RecordingCandidate,
    Release,
    ResolutionResult,
    ResolvedTrack,
    SourceResult,
    TrackInput,
)
from tidal_importer.identity.resolver import ResolverConfig, TrackResolver

__all__ = [
    "Album",
    "Artist",
    "ConfidenceTier",
    "Evidence",
    "IdentityDB",
    "PlatformTrack",
    "Recording",
    "RecordingCandidate",
    "Release",
    "ResolutionResult",
    "ResolvedTrack",
    "ResolverConfig",
    "SourceResult",
    "TrackInput",
    "TrackResolver",
    "compute_confidence",
]

