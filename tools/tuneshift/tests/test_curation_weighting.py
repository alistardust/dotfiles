"""Artist balance breaks ties; it does not decide the ranking.

``score_redundancy`` counts artist appearances, so its rank correlation with
artist scarcity is 1.0 by construction. Given an equal vote alongside the
musical dimensions it stopped being an influence on the ranking and became
the ranking, because the dimensions it competes with are frequently silent on
real data: two of the six need playlist metadata that is usually absent, and
a third is near-constant in practice.

Measured on a 64-track playlist, as the rank correlation of the final score
with artist scarcity against its correlation with musical energy, an equal
vote gave +0.790 / +0.351 and a quarter vote gives +0.133 / +0.775.

These tests pin the contract that follows from that weight, in both
directions: redundancy must not overturn a musical verdict, and it must still
settle one that is otherwise tied.
"""

from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from tuneshift.curation import scoring
from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.scoring import (
    DIMENSION_WEIGHTS,
    mean_contribution,
    score_track_contribution,
)
from tuneshift.sequencer.metadata import TrackMetadata


def _ctx() -> PlaylistContext:
    return PlaylistContext(
        goal="", narrative_sections=[], mood_profile=None, all_tracks=[]
    )


def _track(track_id: int, artist: str, energy: float) -> TrackMetadata:
    return TrackMetadata(
        track_id=track_id, title=f"Track {track_id}", artist=artist, energy=energy
    )


def _pool_centred_on(centre: float, count: int = 20) -> list[TrackMetadata]:
    """Filler that fixes the playlist's energetic centre."""
    return [_track(1000 + i, f"Filler {i}", centre) for i in range(count)]


def _mean(track: TrackMetadata, pool: list[TrackMetadata]) -> float:
    return mean_contribution(score_track_contribution(track, _ctx(), pool))


def test_redundancy_does_not_overturn_a_musical_verdict() -> None:
    """The better-fitting song wins even from a heavily represented artist.

    Under an equal vote this case came out the other way: the crowded artist
    scored 0.54 against 0.68, so the worse musical fit was kept.
    """
    pool = _pool_centred_on(0.3)
    crowded = _track(1, "Joni Mitchell", 0.3)
    pool.append(crowded)
    pool += [_track(100 + i, "Joni Mitchell", 0.3) for i in range(11)]
    rare = _track(2, "Fred Neil", 0.45)
    pool.append(rare)
    pool.append(_track(200, "Fred Neil", 0.3))

    assert _mean(crowded, pool) > _mean(rare, pool)


def test_redundancy_still_settles_a_musical_tie() -> None:
    """Equal musical fit, so the crowded artist is the one that gives way."""
    pool = _pool_centred_on(0.3)
    crowded = _track(1, "Joni Mitchell", 0.3)
    pool.append(crowded)
    pool += [_track(100 + i, "Joni Mitchell", 0.3) for i in range(11)]
    rare = _track(2, "Fred Neil", 0.3)
    pool.append(rare)
    pool.append(_track(200, "Fred Neil", 0.3))

    assert _mean(rare, pool) > _mean(crowded, pool)


def test_redundancy_is_weighted_below_the_musical_dimensions() -> None:
    assert DIMENSION_WEIGHTS["redundancy"] == 0.25


def test_the_weight_is_applied_to_the_mean() -> None:
    """A quarter of the redundancy value against a quarter of the divisor."""
    assert mean_contribution({"energy_role": 0.8, "redundancy": 0.4}) == pytest.approx(
        (0.8 + 0.25 * 0.4) / 1.25
    )


def test_an_unlisted_dimension_carries_full_weight() -> None:
    assert mean_contribution({"energy_role": 0.8, "uniqueness": 0.4}) == pytest.approx(
        0.6
    )


def test_an_abstention_drops_its_weight_from_the_divisor() -> None:
    """Scored on what spoke, not depressed by what did not.

    Dividing by the full weight here would give 0.64 for a track whose only
    live dimension said 0.8.
    """
    assert mean_contribution({"energy_role": 0.8, "redundancy": None}) == pytest.approx(
        0.8
    )


def test_a_track_no_dimension_could_judge_sits_mid_field() -> None:
    assert mean_contribution({"energy_role": None, "redundancy": None}) == 0.5


def test_a_weight_naming_no_real_dimension_is_refused_at_import() -> None:
    """A typo would fall back to 1.0 and silently undo the whole change.

    ``DIMENSION_WEIGHTS.get(name, 1.0)`` cannot tell a deliberate omission
    from a misspelling, so the only signal that "redundancey" did nothing
    would be the ranking quietly going back to how it was.
    """
    assert set(scoring.DIMENSION_WEIGHTS) <= set(scoring.CURATION_SCORERS)

    source = Path(scoring.__file__).read_text()
    broken = source.replace('"redundancy": 0.25,', '"redundancey": 0.25,', 1)
    assert broken != source

    module = ModuleType("scoring_with_typo")
    module.__file__ = scoring.__file__
    with pytest.raises(ValueError, match="do not exist"):
        exec(compile(broken, scoring.__file__, "exec"), module.__dict__)


def test_a_negative_weight_is_refused_at_import() -> None:
    """A negative weight breaks the convex combination and lets the score
    leave [0, 1], which every caller assumes it cannot do."""
    source = Path(scoring.__file__).read_text()
    broken = source.replace('"redundancy": 0.25,', '"redundancy": -1.0,', 1)
    assert broken != source

    module = ModuleType("scoring_with_negative")
    module.__file__ = scoring.__file__
    with pytest.raises(ValueError, match="non-negative"):
        exec(compile(broken, scoring.__file__, "exec"), module.__dict__)


def test_a_dimension_weighted_zero_cannot_be_the_only_judge() -> None:
    """Weight 0.0 means no say. Being the last one standing does not grant it
    one, so the track is unjudged and scores the neutral 0.5."""
    with patch.dict(scoring.DIMENSION_WEIGHTS, {"redundancy": 0.0}, clear=True):
        scores = {"redundancy": 0.1, "energy_role": None, "uniqueness": None}
        assert scoring.mean_contribution(scores) == 0.5
