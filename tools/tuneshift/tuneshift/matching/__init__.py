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
)
from tuneshift.matching.track import (
    classify_results,
    duration_penalty,
    duration_proximity_bonus,
    score_match,
    score_match_with_version,
    score_track_match,
    version_penalty,
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
    "Preferences",
    "VersionPreferences",
    "resolve_preferences",
    "preference_sort_bias",
]
