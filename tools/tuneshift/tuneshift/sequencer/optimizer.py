"""Greedy nearest-neighbor plus 2-opt sequence optimizer."""
import math
import random

from tuneshift.db import Database
from tuneshift.sequencer.metadata import TrackMetadata, get_track_metadata_map
from tuneshift.sequencer.modifiers import SequenceContext, score_candidate
from tuneshift.sequencer.profiles import get_profile
from tuneshift.sequencer.scoring import score_pair


def _target_energy(position_frac: float, arc: str) -> float | None:
    """Target energy at a given fractional position for an arc shape."""
    if arc == "free":
        return None
    if arc == "wave":
        return 0.5 + 0.3 * math.sin(2 * math.pi * position_frac)
    if arc == "narrative":
        if position_frac < 0.2:
            return 0.3 + 2.0 * position_frac
        if position_frac < 0.6:
            return 0.7
        if position_frac < 0.7:
            return 0.7 - 2.0 * (position_frac - 0.6)
        if position_frac < 0.9:
            return 0.5 + 2.5 * (position_frac - 0.7)
        return 1.0 - 4.0 * (position_frac - 0.9)
    if arc == "descending":
        return 0.8 - 0.6 * position_frac
    if arc == "ascending":
        return 0.2 + 0.6 * position_frac
    return None


def _arc_fit_multiplier(
    track: TrackMetadata,
    position: int,
    total: int,
    arc: str,
) -> float:
    """Multiplier based on how well track energy fits the arc position."""
    if arc == "free" or total <= 1:
        return 1.0
    target = _target_energy(position / max(total - 1, 1), arc)
    if target is None or track.energy is None:
        return 1.0
    return 1.0 - 0.3 * abs(track.energy - target)


def select_opener(tracks: list[TrackMetadata], arc: str) -> TrackMetadata:
    """Select the best opening track for the given arc shape."""
    target = _target_energy(0.0, arc)
    if target is None:
        target = 0.5

    scored: list[tuple[float, TrackMetadata]] = []
    for track in tracks:
        energy = track.energy if track.energy is not None else 0.5
        energy_fit = 1.0 - abs(energy - target)
        valence = track.valence if track.valence is not None else 0.5
        valence_fit = 1.0 - abs(valence - 0.5) * 0.5
        scored.append((energy_fit * 0.7 + valence_fit * 0.3, track))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def select_closer(tracks: list[TrackMetadata], arc: str) -> TrackMetadata:
    """Select the best closing track for the given arc shape."""
    target = _target_energy(1.0, arc)
    if target is None:
        target = 0.3

    scored: list[tuple[float, TrackMetadata]] = []
    for track in tracks:
        energy = track.energy if track.energy is not None else 0.5
        energy_fit = 1.0 - abs(energy - target)
        mode_bonus = 0.2 if track.mode == 1 else 0.0
        scored.append((energy_fit + mode_bonus, track))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def distribute_artists(
    sequence: list[TrackMetadata],
    min_separation: int = 4,
) -> list[TrackMetadata]:
    """Distribute same-artist tracks more evenly across the sequence."""
    result = list(sequence)
    track_count = len(result)
    if track_count <= 3:
        return result

    def _has_adjacency_violation(seq: list[TrackMetadata], idx: int) -> bool:
        if idx > 0 and seq[idx].artist == seq[idx - 1].artist:
            return True
        if idx < len(seq) - 1 and seq[idx].artist == seq[idx + 1].artist:
            return True
        return False

    max_passes = max(50, min_separation * 10)
    for _ in range(max_passes):
        violation_idx = None
        for index in range(track_count - 1):
            if result[index].artist == result[index + 1].artist:
                violation_idx = index + 1
                break

        if violation_idx is None:
            break

        violator = result[violation_idx]
        best_target = None
        best_distance = -1
        artist_positions = [
            index for index in range(track_count) if result[index].artist == violator.artist
        ]

        for target_idx in range(track_count):
            if target_idx == violation_idx:
                continue
            target_track = result[target_idx]
            if target_track.artist == violator.artist:
                continue

            result[violation_idx], result[target_idx] = (
                result[target_idx],
                result[violation_idx],
            )
            creates_violation = _has_adjacency_violation(
                result,
                violation_idx,
            ) or _has_adjacency_violation(result, target_idx)
            result[violation_idx], result[target_idx] = (
                result[target_idx],
                result[violation_idx],
            )

            if creates_violation:
                continue

            if len(artist_positions) > 1:
                min_dist = min(
                    abs(target_idx - position)
                    for position in artist_positions
                    if position != violation_idx
                )
            else:
                min_dist = track_count

            if min_dist > best_distance:
                best_distance = min_dist
                best_target = target_idx

        if best_target is not None:
            result[violation_idx], result[best_target] = (
                result[best_target],
                result[violation_idx],
            )
            continue

        for target_idx in range(track_count - 1, -1, -1):
            if target_idx == violation_idx:
                continue
            if result[target_idx].artist == violator.artist:
                continue
            result[violation_idx], result[target_idx] = (
                result[target_idx],
                result[violation_idx],
            )
            break
        else:
            break

    return result


break_artist_runs = distribute_artists


def optimize_sequence(
    tracks: list[TrackMetadata],
    weights: dict[str, float],
    arc: str = "wave",
    artist_min_separation: int = 4,
    bold_jump_chance: float = 0.10,
    narrative_mode: str = "river",
    context_window: int = 5,
    penalty_overrides: dict[str, float] | None = None,
) -> list[TrackMetadata]:
    """Produce an optimized track sequence."""
    if len(tracks) <= 2:
        return list(tracks)

    track_count = len(tracks)

    opener = select_opener(tracks, arc)
    remaining = [track for track in tracks if track.track_id != opener.track_id]
    closer = select_closer(remaining, arc)
    remaining = [track for track in remaining if track.track_id != closer.track_id]

    context = SequenceContext(
        position=0,
        total=track_count,
        narrative_mode=narrative_mode,
        context_window=context_window,
    )

    sequence = [opener]
    context.advance(opener)

    available = {track.track_id for track in remaining}
    track_map = {track.track_id: track for track in remaining}
    bold_jump_cooldown = 0

    for position in range(1, track_count - 1):
        if not available:
            break

        current = sequence[-1]
        candidates: list[tuple[float, TrackMetadata]] = []

        for track_id in available:
            candidate = track_map[track_id]
            base = score_pair(current, candidate, weights)
            arc_mult = _arc_fit_multiplier(candidate, position, track_count, arc)
            adjusted = score_candidate(
                candidate,
                current,
                context,
                base * arc_mult,
                penalty_overrides,
            )
            candidates.append((adjusted, candidate))

        candidates.sort(key=lambda item: item[0], reverse=True)

        bold_jump_cooldown = max(0, bold_jump_cooldown - 1)
        protect_region = position <= 2 or position >= track_count - 3
        if (
            not protect_region
            and bold_jump_cooldown == 0
            and random.random() < bold_jump_chance
            and len(candidates) > 3
        ):
            bottom_start = max(1, int(len(candidates) * 0.7))
            chosen = random.choice(candidates[bottom_start:])[1]
            bold_jump_cooldown = 10
        else:
            chosen = candidates[0][1]

        sequence.append(chosen)
        context.advance(chosen)
        available.remove(chosen.track_id)

    sequence.append(closer)
    sequence = _two_opt(sequence, weights, max_iterations=100)
    sequence = distribute_artists(sequence, min_separation=artist_min_separation)
    return sequence


def sequence_playlist(
    db: Database,
    track_ids: list[int],
    arc: str = "wave",
    profile: str = "default",
) -> list[int]:
    """Sequence playlist tracks using tuneshift's database as metadata source."""
    if len(track_ids) <= 1:
        return list(track_ids)

    profile_config = get_profile(profile)
    resolved_arc = arc or profile_config.arc
    metadata_map = get_track_metadata_map(db, track_ids)
    metadata_tracks = [metadata_map[track_id] for track_id in track_ids if track_id in metadata_map]
    missing_ids = [track_id for track_id in track_ids if track_id not in metadata_map]

    if len(metadata_tracks) <= 1:
        return [track.track_id for track in metadata_tracks] + missing_ids

    ordered_tracks = optimize_sequence(
        metadata_tracks,
        profile_config.weights,
        arc=resolved_arc,
        artist_min_separation=profile_config.artist_min_separation,
        bold_jump_chance=profile_config.bold_jump_chance,
        narrative_mode=profile_config.narrative_mode,
        context_window=profile_config.context_window,
        penalty_overrides=profile_config.penalty_overrides,
    )
    return [track.track_id for track in ordered_tracks] + missing_ids


def _two_opt(
    sequence: list[TrackMetadata],
    weights: dict[str, float],
    max_iterations: int = 100,
) -> list[TrackMetadata]:
    """2-opt local search: swap non-adjacent pairs to improve total score."""
    track_count = len(sequence)
    if track_count <= 3:
        return sequence

    result = list(sequence)
    no_improvement_count = 0

    def _local_score(idx: int) -> float:
        score = 0.0
        if idx > 0:
            pair_score = score_pair(result[idx - 1], result[idx], weights)
            if result[idx - 1].artist == result[idx].artist:
                pair_score *= 0.3
            score += pair_score
        if idx < track_count - 1:
            pair_score = score_pair(result[idx], result[idx + 1], weights)
            if result[idx].artist == result[idx + 1].artist:
                pair_score *= 0.3
            score += pair_score
        return score

    for _ in range(max_iterations):
        improved = False
        for left_index in range(1, track_count - 2):
            for right_index in range(left_index + 2, track_count - 1):
                current_score = _local_score(left_index) + _local_score(right_index)

                result[left_index], result[right_index] = (
                    result[right_index],
                    result[left_index],
                )
                new_score = _local_score(left_index) + _local_score(right_index)

                if new_score > current_score + 0.001:
                    improved = True
                else:
                    result[left_index], result[right_index] = (
                        result[right_index],
                        result[left_index],
                    )

        if improved:
            no_improvement_count = 0
        else:
            no_improvement_count += 1
            if no_improvement_count >= 10:
                break

    return result
