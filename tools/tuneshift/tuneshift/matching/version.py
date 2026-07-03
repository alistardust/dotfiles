"""Source-aware version-class model for intent-fidelity matching.

The legacy version scorer only inspected the *candidate*: it penalised any
result whose title/album carried a "version" keyword (live, karaoke, ...).
That is wrong when the SOURCE is itself a live/karaoke/etc. recording — the
correct match then *shares* that class and must NOT be penalised, while the
studio master becomes the substitute.

This module infers a :class:`VersionProfile` for both the source (canonical)
track and each candidate, then compares them *asymmetrically*:

* studio source + non-studio candidate  -> REJECT   (wrong recording)
* live source   + live candidate         -> MATCH
* live source   + studio candidate        -> SUBSTITUTE (fallback recording)
* live source   + karaoke candidate       -> REJECT   (two different non-studio recordings)
* remaster of the same recording          -> SOFT     (cosmetic, same take)
* explicit source + clean candidate        -> REJECT   (censored lyrics differ)

Per-playlist preferences can override the recording axis: a live-takes
playlist (``prefer:[live]``) elevates a live candidate to MATCH even against a
studio source, and ``avoid:[live]`` hard-rejects live candidates regardless of
the source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from tuneshift.matching import normalize as _norm


class RecordingClass(str, Enum):
    """The "which recording is this" axis (distinct performances)."""

    STUDIO = "studio"
    LIVE = "live"
    KARAOKE = "karaoke"
    INSTRUMENTAL = "instrumental"
    REMIX = "remix"
    ACOUSTIC = "acoustic"
    TRIBUTE = "tribute"


# Recording-identity classes in DETECTION PRIORITY order (most specific first);
# each maps to the compiled regex already defined in ``matching.normalize``.
_CLASS_REGEXES: tuple[tuple[RecordingClass, str], ...] = (
    (RecordingClass.KARAOKE, "_KARAOKE_RE"),
    (RecordingClass.INSTRUMENTAL, "_INSTRUMENTAL_RE"),
    (RecordingClass.TRIBUTE, "_TRIBUTE_RE"),
    (RecordingClass.REMIX, "_REMIX_RE"),
    (RecordingClass.ACOUSTIC, "_ACOUSTIC_RE"),
    (RecordingClass.LIVE, "_LIVE_RE"),
)

_EXPLICIT_RE = re.compile(r"\b(explicit)\b", re.IGNORECASE)
_CLEAN_RE = re.compile(r"\b(clean(?:\s+version)?|censored|radio safe)\b", re.IGNORECASE)

# Non-studio recording classes are DISTINCT recordings; a studio source must
# never silently accept one, and vice-versa.
_DISTINCT: frozenset[RecordingClass] = frozenset(RecordingClass) - {RecordingClass.STUDIO}


@dataclass(frozen=True)
class VersionProfile:
    """The inferred version identity of a single track (source or candidate)."""

    recording: RecordingClass = RecordingClass.STUDIO
    is_remaster: bool = False
    is_explicit: bool = False
    is_clean: bool = False


def infer_version(title: str | None, album: str | None = None) -> VersionProfile:
    """Infer a :class:`VersionProfile` from a track's title and album text."""
    combined = f"{title or ''} {album or ''}"
    recording = RecordingClass.STUDIO
    for cls, regex_name in _CLASS_REGEXES:
        if getattr(_norm, regex_name).search(combined):
            recording = cls
            break
    return VersionProfile(
        recording=recording,
        is_remaster=bool(_norm._REMASTER_RE.search(combined)),
        is_explicit=bool(_EXPLICIT_RE.search(combined)),
        is_clean=bool(_CLEAN_RE.search(combined)),
    )


class VersionVerdict(str, Enum):
    """The outcome of comparing a source profile against a candidate profile."""

    MATCH = "match"            # compatible recording; no version penalty
    SOFT = "soft"              # same recording, cosmetic variant (remaster)
    SUBSTITUTE = "substitute"  # requested class unavailable; fallback recording
    REJECT = "reject"          # wrong recording / censored; must not auto-match


def compare_version(
    source: VersionProfile,
    candidate: VersionProfile,
    *,
    prefer: frozenset[str] = frozenset(),
    avoid: frozenset[str] = frozenset(),
) -> VersionVerdict:
    """Compare a source profile to a candidate profile, honouring preferences.

    ``prefer`` / ``avoid`` are sets of :class:`RecordingClass` *values*
    (e.g. ``{"live"}``) resolved from the effective per-playlist preferences.
    """
    # Explicit user avoidance hard-rejects regardless of the source class.
    if candidate.recording.value in avoid:
        return VersionVerdict.REJECT

    prefers_candidate = candidate.recording.value in prefer

    # --- Recording-class axis ---
    if source.recording == candidate.recording:
        verdict = VersionVerdict.MATCH
    elif prefers_candidate:
        # The playlist explicitly wants this class (e.g. a live-takes playlist),
        # so a live candidate beats the studio master's version penalty.
        verdict = VersionVerdict.MATCH
    elif source.recording == RecordingClass.STUDIO and candidate.recording in _DISTINCT:
        # Studio master requested; candidate is a different recording.
        verdict = VersionVerdict.REJECT
    elif candidate.recording == RecordingClass.STUDIO and source.recording in _DISTINCT:
        # A special recording was requested but only the studio master exists.
        verdict = VersionVerdict.SUBSTITUTE
    else:
        # Two different non-studio recordings (e.g. live vs karaoke).
        verdict = VersionVerdict.REJECT

    # --- Explicit / clean axis (lyrics differ) ---
    if source.is_explicit and candidate.is_clean:
        # "clean never satisfies explicit source"
        return VersionVerdict.REJECT
    if source.is_clean and candidate.is_explicit and verdict is VersionVerdict.MATCH:
        verdict = VersionVerdict.SUBSTITUTE
    # A clean/censored edit is a modified master. Unless the source is itself
    # clean (or a clean edit is explicitly preferred), it must not outrank the
    # unmodified master: down-rank it to a substitute so the explicit/original
    # wins by default, while staying findable when it is the only option.
    if (
        candidate.is_clean
        and not source.is_clean
        and "clean" not in prefer
        and verdict is VersionVerdict.MATCH
    ):
        verdict = VersionVerdict.SUBSTITUTE

    # --- Remaster is cosmetic (same recording) ---
    if verdict is VersionVerdict.MATCH and candidate.is_remaster and not source.is_remaster:
        verdict = VersionVerdict.SOFT

    return verdict


__all__ = [
    "RecordingClass",
    "VersionProfile",
    "VersionVerdict",
    "infer_version",
    "compare_version",
]
