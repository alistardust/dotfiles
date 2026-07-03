"""Track matching: normalization, scoring, and classification.

This package supersedes the former single-file ``matching.py``. Its public
surface is re-exported here unchanged so every existing importer
(``from tuneshift.matching import ...``) keeps working byte-for-byte while the
internals are split across focused modules:

- ``normalize`` — string normalization + the shared version-keyword regexes.
- ``track`` — the legacy track scorers and confidence classifier.

Later chunks add ``similarity``, ``penalties``, ``engine``, ``confidence``,
``preferences``, ``album``, ``artist``, ``version``, ``identity`` and
``audit`` modules; they will be re-exported from here as they land.
"""
from tuneshift.matching.album import (
    ALBUM_THRESHOLDS,
    classify_album_results,
    edition_cost,
    score_album_match,
)
from tuneshift.matching.artist import (
    ARTIST_THRESHOLDS,
    classify_artist_results,
    score_artist_match,
)
from tuneshift.matching.audit import (
    Availability,
    MatchAudit,
    ReasonCode,
    RejectedCandidate,
    describe_availability,
    describe_reason,
)
from tuneshift.matching.fingerprint import (
    DEFAULT_DURATION_BUCKET_SECONDS,
    TrackFingerprint,
    build_fingerprint,
    fingerprint_equal,
)
from tuneshift.matching.normalize import (
    is_remaster,
    normalize_artist,
    normalize_title,
)
from tuneshift.matching.preferences import (
    Preferences,
    VersionPreferences,
    preference_sort_bias,
    resolve_preferences,
    version_intent,
)
from tuneshift.matching.confidence import classify_scores
from tuneshift.matching.track import (
    classify_results,
    duration_penalty,
    duration_proximity_bonus,
    score_match,
    score_match_with_version,
    score_track_match,
    version_penalty,
)
from tuneshift.matching.version import (
    RecordingClass,
    VersionProfile,
    VersionVerdict,
    compare_version,
    infer_version,
)

__all__ = [
    "normalize_title",
    "normalize_artist",
    "is_remaster",
    "score_match",
    "version_penalty",
    "duration_penalty",
    "duration_proximity_bonus",
    "score_match_with_version",
    "score_track_match",
    "classify_results",
    "classify_scores",
    "Preferences",
    "VersionPreferences",
    "resolve_preferences",
    "preference_sort_bias",
    "version_intent",
    "score_album_match",
    "classify_album_results",
    "edition_cost",
    "ALBUM_THRESHOLDS",
    "score_artist_match",
    "classify_artist_results",
    "ARTIST_THRESHOLDS",
    "RecordingClass",
    "VersionProfile",
    "VersionVerdict",
    "infer_version",
    "compare_version",
    "Availability",
    "ReasonCode",
    "RejectedCandidate",
    "MatchAudit",
    "describe_availability",
    "describe_reason",
    "TrackFingerprint",
    "build_fingerprint",
    "fingerprint_equal",
    "DEFAULT_DURATION_BUCKET_SECONDS",
]
