"""Trim must rank songs, not artist scarcity.

Four of the six curation scorers returned a constant 0.5 for real tracks, and
``score_energy_role`` returned 0.5 on both sides of its own None check, so
energy and valence could not influence trim under any circumstances. Averaging
those constants into the mean compressed the usable range to about 0.16 and
left ``score_redundancy``, a per-artist pool count, as the only live signal.

Two corrections are pinned here. Energy is scored by proximity to the pool's
centre, not by band rarity: rarity would protect the loud outliers and cut the
quiet core, inverting a playlist whose mass is its character. And redundancy is
measured against the selection as it is built, so cutting an artist's weakest
track changes the pressure on the rest.
"""

import random

from tuneshift.curation.context import PlaylistContext
from tuneshift.curation.scoring import (
    mean_contribution,
    score_energy_role,
    score_redundancy,
    score_track_contribution,
)
from tuneshift.sequencer.metadata import TrackMetadata


def _ctx() -> PlaylistContext:
    """A context with no goal or mood, which is the common real case."""
    return PlaylistContext(
        goal="", narrative_sections=[], mood_profile=None, all_tracks=[]
    )


def _track(
    track_id: int,
    *,
    artist: str = "Joni Mitchell",
    energy: float | None = None,
    valence: float | None = None,
) -> TrackMetadata:
    return TrackMetadata(
        track_id=track_id,
        title=f"Track {track_id}",
        artist=artist,
        energy=energy,
        valence=valence,
    )


def _laurel_canyon_pool() -> list[TrackMetadata]:
    """A pool shaped like the real playlist: mass low, a sparse loud tail.

    Four tracks at 0.2, twenty-nine at 0.3, sixteen at 0.4, two at 0.5, nine at
    0.6 and four at 0.7. Seventy percent of it sits at 0.3 and 0.4.

    The order is shuffled with a fixed seed so that a tied ranking cannot
    produce the right answer by construction: built in energy order, a scorer
    that ranks nothing at all would still appear to cut the loud tail.
    """
    bands = {0.2: 4, 0.3: 29, 0.4: 16, 0.5: 2, 0.6: 9, 0.7: 4}
    pool: list[TrackMetadata] = []
    track_id = 1
    for energy, count in bands.items():
        for _ in range(count):
            pool.append(_track(track_id, artist=f"Artist {track_id}", energy=energy))
            track_id += 1
    random.Random(0).shuffle(pool)
    return pool


def test_energy_role_is_not_a_constant() -> None:
    """The scorer has to separate tracks, which the stub could never do."""
    ctx = _ctx()
    pool = _laurel_canyon_pool()

    scores = {score_energy_role(t, ctx, pool) for t in pool}

    assert len(scores) > 1, "every track scored identically, the scorer is inert"


def test_energy_favours_the_core_over_the_loud_outlier() -> None:
    """Band rarity would invert this playlist; proximity to the centre must not."""
    ctx = _ctx()
    pool = _laurel_canyon_pool()

    core = score_energy_role(_track(900, energy=0.3), ctx, pool)
    outlier = score_energy_role(_track(901, energy=0.7), ctx, pool)

    assert core > outlier, (
        f"the sparse loud band outranked the playlist's core: "
        f"0.3 scored {core}, 0.7 scored {outlier}"
    )


def test_energy_centre_is_the_median_not_the_mean() -> None:
    """The centre must be robust to the loud tail that drags a mean upward.

    This pool's mean is about 0.39, pulled there by the 0.6 and 0.7 bands. A
    mean-centred scorer ranks the 16-track 0.4 band above the 29-track 0.3
    band that is the playlist's actual core, and scores a quiet 0.2 track and
    a loud 0.6 track as near equals. The median sits at 0.3 and does neither.
    """
    ctx = _ctx()
    pool = _laurel_canyon_pool()

    modal = score_energy_role(_track(900, energy=0.3), ctx, pool)
    off_centre = score_energy_role(_track(901, energy=0.4), ctx, pool)
    quiet = score_energy_role(_track(902, energy=0.2), ctx, pool)
    loud = score_energy_role(_track(903, energy=0.6), ctx, pool)

    assert modal > off_centre, (
        f"the 0.4 band outranked the 0.3 core ({off_centre} vs {modal}); "
        "the centre is being dragged up by the loud tail, so it is a mean"
    )
    assert quiet > loud


def test_energy_abstains_when_the_track_has_no_energy() -> None:
    """No data is an abstention, not a vote of 0.5."""
    ctx = _ctx()
    pool = _laurel_canyon_pool()

    assert score_energy_role(_track(900, energy=None), ctx, pool) is None


def test_abstentions_are_excluded_from_the_mean() -> None:
    """A dimension with no data must not dilute the dimensions that have it."""
    ctx = _ctx()
    pool = [_track(1, energy=0.3), _track(2, energy=0.3)]

    scores = score_track_contribution(pool[0], ctx, pool)
    present = [v for v in scores.values() if v is not None]

    assert None in scores.values(), "no dimension abstained, so nothing is excluded"
    assert present, "every dimension abstained"


def test_redundancy_responds_to_the_selection_not_the_pool() -> None:
    """An artist's next track is worth less once one of theirs is already in.

    Redundancy only penalises: with nothing of the artist selected there is no
    redundancy to report, so it abstains rather than scoring the track well
    for an unused name.
    """
    ctx = _ctx()
    pool = [
        _track(1, artist="Neil Young"),
        _track(2, artist="Neil Young"),
        _track(3, artist="Neil Young"),
        _track(4, artist="Judee Sill"),
    ]
    candidate = pool[2]

    assert score_redundancy(candidate, ctx, pool, []) is None

    one_in = score_redundancy(candidate, ctx, pool, [pool[0]])
    two_in = score_redundancy(candidate, ctx, pool, [pool[0], pool[1]])

    assert two_in < one_in, (
        "redundancy ignored the selection, so it is a per-artist constant"
    )


def test_a_track_with_no_data_does_not_outrank_a_described_one() -> None:
    """Absence of data must not become an advantage.

    Redundancy is the one dimension that can speak for an unclassified track,
    so if it votes high on an unused artist name, the least-known track in the
    pool floats to the top of the ranking.
    """
    ctx = _ctx()
    bare = _track(1, artist="Unknown")
    described = _track(2, artist="Joni Mitchell", energy=0.3, valence=0.4)
    pool = [bare, described]

    bare_avg = mean_contribution(score_track_contribution(bare, ctx, pool))
    described_avg = mean_contribution(score_track_contribution(described, ctx, pool))

    assert described_avg > bare_avg


def test_trim_cuts_the_loud_outliers_from_a_quiet_playlist() -> None:
    """End to end: the character of the playlist survives the trim."""
    from tuneshift.curation.curator import curate_trim

    ctx = _ctx()
    pool = _laurel_canyon_pool()

    result = curate_trim(pool, ctx, {"track_count": {"target": 40}})

    assert len(result.keep) == 40
    kept_loud = sum(1 for t in result.keep if (t.energy or 0) >= 0.6)
    cut_loud = sum(1 for t in result.cut if (t.energy or 0) >= 0.6)
    assert cut_loud > kept_loud, (
        f"trim kept {kept_loud} loud tracks and cut {cut_loud}; "
        "the sparse loud band is being protected rather than trimmed"
    )


def test_trim_spread_is_wider_than_the_artist_count_signal() -> None:
    """The ranking must not collapse back onto a single dimension."""
    from tuneshift.curation.curator import curate_analyze

    ctx = _ctx()
    pool = _laurel_canyon_pool()

    report = curate_analyze(pool, ctx)
    averages = [data["average"] for data in report["scores"].values()]

    assert max(averages) - min(averages) > 0.16, (
        f"score range is {max(averages) - min(averages):.3f}, no wider than the "
        "one-dimensional ranking it replaced"
    )


def test_trim_selects_greedily_against_what_it_has_already_kept() -> None:
    """Redundancy pressure has to build during selection, not be fixed up front.

    Scored once against the whole pool, an artist with six tracks carries the
    same penalty on all six, which is a per-artist constant. That constant was
    strong enough to rank two distant outliers above a core the playlist is
    actually made of.

    Scored against the growing selection, the first of that artist is free,
    the second costs something, and the third costs more. The core survives
    and the pressure is still real.
    """
    from tuneshift.curation.curator import curate_trim

    ctx = _ctx()
    core = [_track(i, artist="Prolific", energy=0.3) for i in range(1, 7)]
    outliers = [
        _track(7, artist="Solo A", energy=0.7),
        _track(8, artist="Solo B", energy=0.7),
    ]

    result = curate_trim(core + outliers, ctx, {"track_count": {"target": 3}})

    assert [t.artist for t in result.keep] == ["Prolific"] * 3, (
        "the playlist's core was cut in favour of its outliers, which is the "
        "artist-scarcity ranking the fix replaced"
    )

    # The decaying scores are the fingerprint: they can only fall as the
    # selection grows if each pick is scored against what came before it.
    scores = [float(s.removeprefix("score=")) for s in result.reasoning.values()]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[-1], (
        f"redundancy pressure never built: {scores}; every pick was scored "
        "against the same fixed pool"
    )
