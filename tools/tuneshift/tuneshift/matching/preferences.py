"""User preference model and cascade resolver for reconciliation.

The cascade layers, from lowest to highest precedence:

    defaults  <  global  <  playlist  <  track

Global preferences live in the ``schema_meta`` key/value store; per-playlist
preferences live in ``playlists.preferences`` (JSON). Both are resolved into a
single effective :class:`Preferences` used by the reconciliation scorer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_DEFAULT_PREFER = ("studio", "original", "explicit")
_DEFAULT_AVOID = ("live", "remix", "acoustic", "radio-edit", "clean")
_DEFAULT_TIEBREAK = ("newest-remaster", "original-release")


@dataclass
class Preferences:
    """Effective version preferences for matching a playlist's tracks."""

    prefer: list[str] = field(default_factory=lambda: list(_DEFAULT_PREFER))
    avoid: list[str] = field(default_factory=lambda: list(_DEFAULT_AVOID))
    duration_tolerance_percent: float = 15.0
    tiebreak_order: list[str] = field(default_factory=lambda: list(_DEFAULT_TIEBREAK))

    def is_default(self) -> bool:
        """True when these preferences equal the built-in defaults.

        Used to guarantee a strict no-op (byte-parity) when no user
        preferences have been configured.
        """
        return self == Preferences()


# Backwards-compatible alias for the pre-overhaul name.
VersionPreferences = Preferences


def resolve_preferences(
    global_prefs: dict | None,
    playlist_prefs: dict | None,
    track_prefs: dict | None,
) -> Preferences:
    """Cascade preference layers into a single effective ``Preferences``.

    Precedence (highest last): defaults < global < playlist < track. Each layer
    is a partial dict; absent keys inherit from the layer below.
    """
    base = Preferences()
    for layer in (global_prefs, playlist_prefs, track_prefs):
        if not layer:
            continue
        if "prefer" in layer:
            base.prefer = list(layer["prefer"])
        if "avoid" in layer:
            base.avoid = list(layer["avoid"])
        if "duration_tolerance_percent" in layer:
            base.duration_tolerance_percent = layer["duration_tolerance_percent"]
        if "tiebreak_order" in layer:
            base.tiebreak_order = list(layer["tiebreak_order"])
    return base


def preference_sort_bias(text: str, prefs: Preferences) -> int:
    """Return a signed re-rank bias for a candidate given its version text.

    The bias is a bounded tie-break that adjusts only the *ordering* of
    candidates within a scoring band; it never mutates the reported score or the
    confidence classification. Returns 0 when ``prefs`` are the defaults,
    guaranteeing identical behaviour (byte parity) for playlists with no
    configured preferences.

    A positive bias favours the candidate (preferred keyword present); a
    negative bias disfavours it (avoided keyword present). Full version-intent
    semantics (e.g. a live-recordings playlist overriding the studio master's
    version penalty) are owned by the version-safety work in Chunk 4; this
    function only reorders otherwise-comparable candidates.
    """
    if prefs.is_default():
        return 0
    lowered = text.lower()
    bias = 0
    for keyword in prefs.prefer:
        if keyword and keyword.lower() in lowered:
            bias += 5
    for keyword in prefs.avoid:
        if keyword and keyword.lower() in lowered:
            bias -= 5
    return bias


def version_intent(prefs: Preferences) -> tuple[frozenset[str], frozenset[str]]:
    """Resolve preferences into (prefer, avoid) recording-class sets.

    Only the keywords that name an actual recording class (live, remix,
    acoustic, karaoke, instrumental, tribute) are forwarded to the source-aware
    version comparison; packaging keywords (radio-edit, deluxe) and the studio/
    original defaults are handled elsewhere.

    Returns two empty sets when ``prefs`` are the built-in defaults, so a
    playlist with no configured intent relies purely on source inference (a
    studio source still rejects live takes, a live source still matches live).
    """
    from tuneshift.matching.version import RecordingClass

    if prefs.is_default():
        return frozenset(), frozenset()

    recording_values = {c.value for c in RecordingClass}

    def _classes(keywords: list[str]) -> frozenset[str]:
        return frozenset(
            k.lower() for k in keywords if k and k.lower() in recording_values
        )

    return _classes(prefs.prefer), _classes(prefs.avoid)


__all__ = [
    "Preferences",
    "VersionPreferences",
    "resolve_preferences",
    "preference_sort_bias",
    "version_intent",
]
