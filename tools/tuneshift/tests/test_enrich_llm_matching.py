"""Matching an LLM's echoed title back to the row we asked about.

``_run_classification`` sends ``(title, artist)`` to the model and matches the
returned rows back by that pair. The key was built with ``.lower().strip()``
and nothing else, so a model that echoed the title with typographic
punctuation missed every lookup. The track was then dropped with a warning
that reads like a model error rather than a matching bug, and the run still
reported success.

That is not a rare shape. 11.3% of the library carries a straight apostrophe
in the title, and a model is free to return the typographic form of any of
them.

The repo already had the answer in ``matching.normalize``, whose punctuation
table maps U+2019 to U+0027. These tests pin that the lookup uses it through
``fold_typography``, which folds accents, punctuation, case and whitespace and
stops there. ``normalize_title`` would have been the obvious reach, but it also
strips edition parentheticals and feature credits, which is right for finding
one song across catalogues and wrong here: it collapses rows the library holds
separately, and the ambiguity guard then refuses both.

They also pin that ambiguity: two rows reducing to one key must be refused
rather than guessed between.
"""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from tuneshift.commands.enrich_cmd import _run_classification

CLASSIFIER = "tuneshift.sequencer.classifier.TrackClassifier"

STRAIGHT = "I'll Feel a Whole Lot Better"
CURLY = "I\u2019ll Feel a Whole Lot Better"


def _track(track_id: int, title: str, artist: str) -> SimpleNamespace:
    return SimpleNamespace(id=track_id, title=title, artist=artist, metadata={})


def _run(tracks: list, results: list) -> tuple[Mock, int]:
    """Run classification with a stubbed backend. Returns (db, classified).

    The per-track recovery call returns nothing, so these tests see the
    matching path alone. Recovery is covered in ``test_enrich_recovery``.
    """
    db = Mock()
    db.get_narrative.return_value = None
    classifier = Mock()
    classifier.available = True
    classifier.backend_info = "stub"
    classifier.classify_batched.return_value = results
    classifier.classify.return_value = []
    with patch(CLASSIFIER, return_value=classifier):
        count = _run_classification(db, tracks, "Mix", playlist_id=1)
    return db, count


def _written(db: Mock) -> dict[int, dict]:
    return {
        call.args[0]: call.args[1] for call in db.update_track_metadata.call_args_list
    }


def test_typographic_apostrophe_in_the_result_still_matches() -> None:
    """The headline defect: 11.3% of the library was one keystroke from loss."""
    tracks = [_track(106, STRAIGHT, "The Byrds")]
    results = [{"title": CURLY, "artist": "The Byrds", "narrator_stance": "first"}]

    db, count = _run(tracks, results)

    assert count == 1
    assert _written(db)[106]["narrator_stance"] == "first"


def test_typographic_apostrophe_in_the_library_still_matches() -> None:
    """The same defect in reverse: 8 library titles carry the curly form."""
    tracks = [_track(106, CURLY, "The Byrds")]
    results = [{"title": STRAIGHT, "artist": "The Byrds", "narrator_stance": "first"}]

    db, count = _run(tracks, results)

    assert count == 1
    assert 106 in _written(db)


@pytest.mark.parametrize(
    "returned_title",
    [
        "i'll feel a whole lot better",
        "  I'll Feel a Whole Lot Better  ",
        "I\u2018ll Feel a Whole Lot Better",
    ],
    ids=["case", "whitespace", "left-quote"],
)
def test_benign_variation_in_the_echo_still_matches(returned_title: str) -> None:
    tracks = [_track(106, STRAIGHT, "The Byrds")]
    results = [{"title": returned_title, "artist": "The Byrds", "tempo": 120}]

    db, count = _run(tracks, results)

    assert count == 1
    assert 106 in _written(db)


def test_artist_variation_falls_back_to_a_unique_title() -> None:
    """The fallback earns its place when the title identifies one row.

    The artist here is a different name, not a spelling variant, so
    normalisation cannot reconcile it and only the fallback can match.
    """
    tracks = [_track(106, "Chestnut Mare", "The Byrds")]
    results = [{"title": "Chestnut Mare", "artist": "Roger McGuinn", "tempo": 120}]

    db, count = _run(tracks, results)

    assert count == 1
    assert 106 in _written(db)


def test_the_artist_is_normalised_when_only_the_artist_can_disambiguate() -> None:
    """Both rows share a title, so the fallback cannot rescue a bad artist key."""
    tracks = [
        _track(1, "Patience", "Guns N' Roses"),
        _track(2, "Patience", "Take That"),
    ]
    results = [{"title": "Patience", "artist": "Guns N\u2019 Roses", "tempo": 120}]

    db, count = _run(tracks, results)

    assert count == 1
    assert 1 in _written(db)


def test_a_result_with_no_identifying_fields_never_matches() -> None:
    """A malformed row folds to an empty key, so an empty key must not match.

    Without the guard, a model result that omitted title and artist would
    land on whichever row happens to carry no usable title.
    """
    tracks = [_track(1, "", "")]
    results = [{"tempo": 120}]

    db, count = _run(tracks, results)

    assert count == 0
    assert _written(db) == {}


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Bohemian Rhapsody", "Bohemian Rhapsody (Remastered 2011)"),
        ("Big Yellow Taxi", "Big Yellow Taxi (feat. Lucius)"),
    ],
    ids=["remaster", "feature"],
)
def test_an_edition_or_feature_is_not_folded_away(first: str, second: str) -> None:
    """These are separate rows in the library and must stay separate keys.

    ``normalize_title`` strips both deliberately, because its job is to find
    one song across catalogues that label releases differently. Borrowing it
    here would collapse the pair, and the ambiguity guard would then refuse
    to classify either. 411 library tracks fold together under that rule
    against 378 under this one.
    """
    tracks = [_track(1, first, "Artist"), _track(2, second, "Artist")]
    results = [
        {"title": first, "artist": "Artist", "tempo": 1},
        {"title": second, "artist": "Artist", "tempo": 2},
    ]

    db, count = _run(tracks, results)

    assert count == 2
    written = _written(db)
    assert written[1]["tempo"] == 1
    assert written[2]["tempo"] == 2


def test_a_third_row_does_not_reset_the_refusal() -> None:
    """The sentinel must survive every later row that shares its key."""
    tracks = [_track(i, "Blue Moon", "The Marcels") for i in (1, 2, 3)]
    results = [{"title": "Blue Moon", "artist": "The Marcels", "tempo": 120}]

    db, count = _run(tracks, results)

    assert count == 0
    assert _written(db) == {}


def test_the_two_refusals_are_told_apart_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A dropped track reads as a model error unless the log says otherwise."""
    tracks = [_track(1, "Blue Moon", "A"), _track(2, "Blue Moon", "B")]
    results = [
        {"title": "Blue Moon", "artist": "C"},
        {"title": "Nothing Like It", "artist": "D"},
    ]

    with caplog.at_level(logging.WARNING):
        _run(tracks, results)

    messages = [r.getMessage() for r in caplog.records]
    assert any("ambiguous" in m and "Blue Moon" in m for m in messages)
    assert any("unmatched" in m and "Nothing Like It" in m for m in messages)


def test_a_title_shared_by_two_artists_is_refused_not_guessed() -> None:
    """The fallback took the first dict match, which can write the wrong row.

    Normalising the key harder makes this easier to reach, so the two are
    fixed together: an ambiguous title is not a match.
    """
    tracks = [
        _track(1, "Blue Moon", "The Marcels"),
        _track(2, "Blue Moon", "Billie Holiday"),
    ]
    results = [{"title": "Blue Moon", "artist": "Someone Else", "tempo": 120}]

    db, count = _run(tracks, results)

    assert count == 0
    assert _written(db) == {}


def test_two_rows_reducing_to_one_key_are_refused_not_guessed() -> None:
    """Normalisation must not silently merge two distinct rows."""
    tracks = [
        _track(1, STRAIGHT, "The Byrds"),
        _track(2, CURLY, "The Byrds"),
    ]
    results = [{"title": STRAIGHT, "artist": "The Byrds", "tempo": 120}]

    db, count = _run(tracks, results)

    assert count == 0
    assert _written(db) == {}


def test_an_unrelated_result_is_still_skipped() -> None:
    """The existing guard against silent miswrites has to survive the fix."""
    tracks = [_track(106, STRAIGHT, "The Byrds")]
    results = [{"title": "Something Else Entirely", "artist": "Nobody"}]

    db, count = _run(tracks, results)

    assert count == 0
    assert _written(db) == {}


def test_each_result_matches_its_own_track() -> None:
    """A batch must not cross-assign, whatever punctuation comes back."""
    tracks = [
        _track(106, STRAIGHT, "The Byrds"),
        _track(135, "For What It's Worth", "Buffalo Springfield"),
    ]
    results = [
        {
            "title": "For What It\u2019s Worth",
            "artist": "Buffalo Springfield",
            "tempo": 1,
        },
        {"title": CURLY, "artist": "The Byrds", "tempo": 2},
    ]

    db, count = _run(tracks, results)

    assert count == 2
    written = _written(db)
    assert written[135]["tempo"] == 1
    assert written[106]["tempo"] == 2


def test_a_track_echoed_twice_is_written_once() -> None:
    """A repeated result must not inflate the count past the denominator.

    The run prints "Classified N/M tracks" and the caller sums N across
    playlists. Counting one track twice reports more work than was done, and
    the second write silently overwrites the first with whichever copy the
    model sent last.
    """
    tracks = [_track(1, "Ohio", "CSNY"), _track(2, "Helpless", "CSNY")]
    results = [
        {"title": "Ohio", "artist": "CSNY", "tempo": 1},
        {"title": "Ohio", "artist": "CSNY", "tempo": 2},
        {"title": "Helpless", "artist": "CSNY", "tempo": 3},
    ]

    db, count = _run(tracks, results)

    assert count == 2
    assert db.update_track_metadata.call_count == 2
    assert _written(db)[1]["tempo"] == 1
