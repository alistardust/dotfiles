"""Curation engine: trim and analyze playlist contents."""

from dataclasses import dataclass, field

from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.scoring import score_track_contribution
from tuneshift.sequencer.metadata import TrackMetadata


class CurationConstraintError(RuntimeError):
    """The constraints cannot be met without cutting a protected track.

    Raised instead of silently discarding a pin (BUG-22). A pin is the one
    explicit instruction the user has given, so trim stops and reports rather
    than resolving the conflict on its own.
    """


@dataclass
class CurationResult:
    keep: list[TrackMetadata]
    cut: list[TrackMetadata] = field(default_factory=list)
    reasoning: dict[int, str] = field(default_factory=dict)


def curate_trim(
    tracks: list[TrackMetadata],
    ctx: PlaylistContext,
    constraints: dict,
    protected_ids: frozenset[int] | set[int] | None = None,
) -> CurationResult:
    """Trim playlist to meet constraints, cutting lowest-scoring tracks first.

    ``protected_ids`` are never cut, regardless of score or duration pressure
    (BUG-22). When the count target is lower than the number of protected
    tracks, :class:`CurationConstraintError` is raised rather than cutting one.

    A ``track_count`` target is exact (BUG-23): it is never padded by a
    tolerance. ``hard_limit`` remains a separate, lower ceiling when supplied.
    """
    protected = frozenset(protected_ids or ())

    scored = []
    for track in tracks:
        scores = score_track_contribution(track, ctx, tracks)
        avg_score = sum(scores.values()) / len(scores) if scores else 0.5
        scored.append((track, avg_score))

    # Sort by score descending (best tracks first)
    scored.sort(key=lambda x: x[1], reverse=True)

    # Determine how many to keep based on constraints
    target_count = None
    hard_limit_count = len(tracks)  # default: keep all

    if "track_count" in constraints:
        tc = constraints["track_count"]
        target_count = tc.get("target")
        hard_limit_count = tc.get("hard_limit", len(tracks)) or len(tracks)

    eligible = scored
    if "duration" in constraints:
        dc = constraints["duration"]
        hard_limit_ms = (dc.get("hard_limit_minutes") or 999) * 60 * 1000
        # Protected tracks claim their runtime first; only optional tracks are
        # dropped to fit the ceiling.
        total_ms = sum(t.duration_ms or 0 for t, _ in scored if t.track_id in protected)
        duration_limited = []
        for track, score in scored:
            if track.track_id in protected:
                duration_limited.append((track, score))
                continue
            track_ms = track.duration_ms or 0
            if total_ms + track_ms > hard_limit_ms:
                continue
            duration_limited.append((track, score))
            total_ms += track_ms
        eligible = duration_limited
        hard_limit_count = min(hard_limit_count, len(eligible))

    keep_count = min(hard_limit_count, len(eligible))
    if target_count is not None:
        keep_count = min(keep_count, target_count)

    protected_present = [t for t, _ in eligible if t.track_id in protected]
    if keep_count < len(protected_present):
        raise CurationConstraintError(
            f"cannot trim to {keep_count} track(s) without cutting "
            f"{len(protected_present)} pinned track(s); "
            "raise the target or remove a pin"
        )

    keep_ids = {t.track_id for t in protected_present}
    for track, _score in eligible:
        if len(keep_ids) >= keep_count:
            break
        keep_ids.add(track.track_id)

    keep = [t for t, _ in eligible if t.track_id in keep_ids]
    cut = [t for t in tracks if t.track_id not in keep_ids]
    reasoning = {
        t.track_id: f"score={s:.2f}" for t, s in eligible if t.track_id in keep_ids
    }

    return CurationResult(keep=keep, cut=cut, reasoning=reasoning)


def curate_analyze(
    tracks: list[TrackMetadata],
    ctx: PlaylistContext,
) -> dict:
    """Analyze playlist coverage without making changes."""
    scores = {}
    for track in tracks:
        track_scores = score_track_contribution(track, ctx, tracks)
        scores[track.track_id] = {
            "title": track.title,
            "artist": track.artist,
            "dimensions": track_scores,
            "average": sum(track_scores.values()) / len(track_scores),
        }

    # Sort by average score
    ranked = sorted(scores.items(), key=lambda x: x[1]["average"])

    return {
        "scores": scores,
        "weakest": [{"track_id": tid, **data} for tid, data in ranked[:5]],
        "strongest": [{"track_id": tid, **data} for tid, data in ranked[-5:]],
    }
