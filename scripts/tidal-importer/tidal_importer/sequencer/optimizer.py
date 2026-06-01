"""Greedy nearest-neighbor + 2-opt sequence optimizer."""
import math
import random

from tidal_importer.sequencer.cache import TrackMetadata
from tidal_importer.sequencer.modifiers import SequenceContext, score_candidate
from tidal_importer.sequencer.scoring import score_pair


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


def _arc_fit_multiplier(track: TrackMetadata, position: int, total: int, arc: str) -> float:
    """Multiplier (0.7-1.0) based on how well track energy fits the arc position."""
    if arc == "free" or total <= 1:
        return 1.0
    target = _target_energy(position / max(total - 1, 1), arc)
    if target is None or track.energy is None:
        return 1.0
    return 1.0 - 0.3 * abs(track.energy - target)


def select_opener(tracks: list[TrackMetadata], arc: str) -> TrackMetadata:
    """Select best opening track for the given arc shape."""
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
    """Select best closing track for the given arc shape."""
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


def break_artist_runs(
    sequence: list[TrackMetadata],
    min_separation: int = 4,
) -> list[TrackMetadata]:
    """Post-process to break runs of 3+ consecutive same-artist tracks."""
    _ = min_separation  # reserved for future threshold tuning
    result = list(sequence)
    max_attempts = 20

    for _ in range(max_attempts):
        run_start = None
        for index in range(len(result) - 2):
            if result[index].artist == result[index + 1].artist == result[index + 2].artist:
                run_start = index
                break

        if run_start is None:
            break

        mid_idx = run_start + 1
        mid_track = result[mid_idx]

        swapped = False
        for offset in range(1, len(result)):
            for target_idx in [mid_idx + offset, mid_idx - offset]:
                if target_idx < 0 or target_idx >= len(result):
                    continue
                if target_idx == mid_idx:
                    continue
                target_track = result[target_idx]
                if target_track.artist == mid_track.artist:
                    continue
                result[mid_idx], result[target_idx] = result[target_idx], result[mid_idx]
                valid = True
                for check_idx in [mid_idx, target_idx]:
                    start = max(0, check_idx - 2)
                    end = min(len(result) - 3, check_idx)
                    for candidate_index in range(start, end + 1):
                        if (
                            result[candidate_index].artist
                            == result[candidate_index + 1].artist
                            == result[candidate_index + 2].artist
                        ):
                            valid = False
                            break
                    if not valid:
                        break
                if valid:
                    swapped = True
                    break
                result[mid_idx], result[target_idx] = result[target_idx], result[mid_idx]
            if swapped:
                break

        if not swapped:
            break

    return result


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
    """Produce optimized track sequence using context-aware greedy + 2-opt."""
    if len(tracks) <= 2:
        return list(tracks)

    track_count = len(tracks)

    opener = select_opener(tracks, arc)
    remaining = [track for track in tracks if track.isrc != opener.isrc]
    closer = select_closer(remaining, arc)
    remaining = [track for track in remaining if track.isrc != closer.isrc]

    # Initialize context
    context = SequenceContext(
        position=0,
        total=track_count,
        narrative_mode=narrative_mode,
        context_window=context_window,
    )

    sequence = [opener]
    context.advance(opener)

    available = {track.isrc for track in remaining}
    track_map = {track.isrc: track for track in remaining}
    bold_jump_cooldown = 0

    for position in range(1, track_count - 1):
        if not available:
            break

        current = sequence[-1]
        candidates: list[tuple[float, TrackMetadata]] = []

        for isrc in available:
            candidate = track_map[isrc]
            base = score_pair(current, candidate, weights)
            arc_mult = _arc_fit_multiplier(candidate, position, track_count, arc)
            adjusted = score_candidate(
                candidate, current, context, base * arc_mult, penalty_overrides
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
        available.remove(chosen.isrc)

    sequence.append(closer)
    sequence = _two_opt(sequence, weights, max_iterations=100)
    # Safety net: break extreme artist runs (5+ consecutive)
    sequence = break_artist_runs(sequence, min_separation=5)
    return sequence


def _two_opt(
    sequence: list[TrackMetadata],
    weights: dict[str, float],
    max_iterations: int = 100,
) -> list[TrackMetadata]:
    """2-opt local search: swap non-adjacent pairs to improve total score.

    Includes artist adjacency penalty to prevent re-clustering.
    """
    track_count = len(sequence)
    if track_count <= 3:
        return sequence

    result = list(sequence)
    no_improvement_count = 0

    def _local_score(idx: int) -> float:
        """Score for a position considering its neighbors + artist penalty."""
        s = 0.0
        if idx > 0:
            pair_s = score_pair(result[idx - 1], result[idx], weights)
            if result[idx - 1].artist == result[idx].artist:
                pair_s *= 0.3
            s += pair_s
        if idx < track_count - 1:
            pair_s = score_pair(result[idx], result[idx + 1], weights)
            if result[idx].artist == result[idx + 1].artist:
                pair_s *= 0.3
            s += pair_s
        return s

    for _ in range(max_iterations):
        improved = False
        for left_index in range(1, track_count - 2):
            for right_index in range(left_index + 2, track_count - 1):
                current_score = _local_score(left_index) + _local_score(right_index)

                result[left_index], result[right_index] = result[right_index], result[left_index]
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
