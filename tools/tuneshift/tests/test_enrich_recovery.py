"""Recovering tracks a batch classification did not write.

``_run_classification`` matches a model's results back to the rows it asked
about by the echoed title and artist. That binding fails in two ways the
matching code cannot fix from inside.

A key shared by two rows cannot be resolved at all: the echo names both, so
the lookup refuses rather than guessing, and no re-run will ever help.

More commonly the model tidies the title. The library holds editions in full,
``Andmoreagain (2015 Remaster)``, and the model returns the bare title; it
also goes the other way and supplies a subtitle the row does not carry.
``fold_typography`` cannot reach either, and must not, because keeping
editions distinct is the reason it exists rather than ``normalize_title``.

Both are answered by asking about one track at a time. A single-track prompt
returns a single result, so the binding is by construction and no text is
matched. The echoed title can be anything at all.

The silence is what makes this worth automating. A dropped row prints a
warning and a short count, and nothing in the output says a re-run would
recover it.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from tuneshift.commands.enrich_cmd import _run_classification

CLASSIFIER = "tuneshift.sequencer.classifier.TrackClassifier"


def _track(track_id: int, title: str, artist: str) -> SimpleNamespace:
    return SimpleNamespace(id=track_id, title=title, artist=artist, metadata={})


def _run(
    tracks: list,
    results: list,
    retries: dict[str, list[dict]] | None = None,
    narrative: str | None = None,
) -> tuple[Mock, Mock, int]:
    """Run classification with a stubbed backend.

    ``results`` is what the batch call returns. ``retries`` maps a track
    title to what a single-track call returns for it. Returns the database
    mock, the classifier mock and the reported count.
    """
    lookup = retries or {}
    db = Mock()
    db.get_narrative.return_value = narrative
    classifier = Mock()
    classifier.available = True
    classifier.backend_info = "stub"
    classifier.classify_batched.return_value = results
    classifier.classify.side_effect = lambda batch, **kw: lookup.get(
        batch[0]["title"], []
    )
    with patch(CLASSIFIER, return_value=classifier):
        count = _run_classification(db, tracks, "Mix", playlist_id=1)
    return db, classifier, count


def _written(db: Mock) -> dict[int, dict]:
    return {
        call.args[0]: call.args[1] for call in db.update_track_metadata.call_args_list
    }


def _asked_about(classifier: Mock) -> list[str]:
    """Titles passed to the per-track call, in order."""
    return [call.args[0][0]["title"] for call in classifier.classify.call_args_list]


def test_a_tidied_title_is_recovered_and_bound_to_the_right_row() -> None:
    """The headline case: the model drops the edition, so the echo cannot match."""
    tracks = [_track(42, "Andmoreagain (2015 Remaster)", "Love")]
    results = [{"title": "Andmoreagain", "artist": "Love", "tempo": 1}]
    retries = {
        "Andmoreagain (2015 Remaster)": [
            {"title": "Andmoreagain", "artist": "Love", "tempo": 2}
        ]
    }

    db, _, count = _run(tracks, results, retries)

    assert count == 1
    assert _written(db)[42]["tempo"] == 2


def test_an_invented_subtitle_is_recovered_too() -> None:
    """The same failure in reverse: the model adds what the row does not carry."""
    tracks = [_track(7, "If I Had a Hammer", "Peter, Paul and Mary")]
    results = [{"title": "If I Had a Hammer (The Hammer Song)", "artist": "PP&M"}]
    retries = {
        "If I Had a Hammer": [{"title": "whatever it likes", "tempo": 3}],
    }

    db, _, count = _run(tracks, results, retries)

    assert count == 1
    assert _written(db)[7]["tempo"] == 3


def test_the_recovered_result_is_not_matched_by_text() -> None:
    """Binding is positional, so a result naming a different song still lands.

    This is the whole point of the single-track call and the reason it can
    fix what the batch path cannot. It is also the risk it accepts: a model
    that answers about the wrong song is not detectable here, and a
    single-track prompt is the strongest grounding available.
    """
    tracks = [_track(9, "Itchycoo Park", "Small Faces")]
    retries = {"Itchycoo Park": [{"title": "Not This Song At All", "tempo": 4}]}

    db, _, count = _run(tracks, [], retries)

    assert count == 1
    assert _written(db)[9]["tempo"] == 4


def test_both_rows_of_an_ambiguous_key_are_recovered_separately() -> None:
    """The refusal stands in the batch path; recovery resolves it by id."""
    tracks = [
        _track(107, "Caroline, No", "The Beach Boys"),
        _track(2154, "Caroline, No", "The Beach Boys"),
    ]
    results = [{"title": "Caroline, No", "artist": "The Beach Boys", "tempo": 1}]
    calls = iter([[{"tempo": 10}], [{"tempo": 11}]])

    db = Mock()
    db.get_narrative.return_value = None
    classifier = Mock()
    classifier.available = True
    classifier.backend_info = "stub"
    classifier.classify_batched.return_value = results
    classifier.classify.side_effect = lambda batch, **kw: next(calls)
    with patch(CLASSIFIER, return_value=classifier):
        count = _run_classification(db, tracks, "Mix", playlist_id=1)

    assert count == 2
    written = _written(db)
    assert written[107]["tempo"] == 10
    assert written[2154]["tempo"] == 11


def test_a_track_the_batch_wrote_is_not_retried() -> None:
    """Recovery costs a call per track, so it must only cover real misses."""
    tracks = [_track(1, "Ohio", "CSNY"), _track(2, "Helpless", "CSNY")]
    results = [{"title": "Ohio", "artist": "CSNY", "tempo": 1}]
    retries = {"Helpless": [{"tempo": 2}]}

    db, classifier, count = _run(tracks, results, retries)

    assert _asked_about(classifier) == ["Helpless"]
    assert count == 2
    assert _written(db)[1]["tempo"] == 1


def test_nothing_is_retried_when_the_batch_wrote_everything() -> None:
    tracks = [_track(1, "Ohio", "CSNY")]
    results = [{"title": "Ohio", "artist": "CSNY", "tempo": 1}]

    _, classifier, count = _run(tracks, results)

    assert classifier.classify.call_count == 0
    assert count == 1


def test_the_retry_asks_about_exactly_one_track() -> None:
    """A multi-track prompt would reintroduce the binding problem it solves."""
    tracks = [_track(1, "Ohio", "CSNY"), _track(2, "Helpless", "CSNY")]

    _, classifier, _ = _run(tracks, [])

    assert classifier.classify.call_count == 2
    for call in classifier.classify.call_args_list:
        assert len(call.args[0]) == 1


def test_an_empty_retry_leaves_the_track_unwritten() -> None:
    """A model that still returns nothing must not inflate the count."""
    tracks = [_track(1, "Ohio", "CSNY")]

    db, _, count = _run(tracks, [], {})

    assert count == 0
    assert _written(db) == {}


def test_a_retry_returning_more_than_one_result_is_refused() -> None:
    """One track in, one result out. Anything else cannot be bound.

    Binding here is positional rather than by text, so a second result has
    no row to belong to. Taking the first would be a guess of exactly the
    kind the batch path refuses to make.
    """
    tracks = [_track(1, "Ohio", "CSNY")]
    retries = {"Ohio": [{"tempo": 1}, {"tempo": 2}]}

    db, _, count = _run(tracks, [], retries)

    assert count == 0
    assert _written(db) == {}


def test_the_narrative_reaches_the_retry() -> None:
    """A single-track prompt loses the batch's context unless it is passed on."""
    tracks = [_track(1, "Ohio", "CSNY")]

    _, classifier, _ = _run(tracks, [], {}, narrative="Laurel Canyon, 1970")

    assert classifier.classify.call_args.kwargs["narrative"] == "Laurel Canyon, 1970"


def test_the_retry_is_announced(capsys: pytest.CaptureFixture[str]) -> None:
    """Silence is the defect. A run that recovers work has to say so.

    The batch pass reports progress with a carriage return, which is
    invisible through a pipe, so the retry is printed on its own line. The
    announced number counts what is being retried, not the whole playlist,
    so one track here is already written and two are not.
    """
    tracks = [
        _track(1, "Ohio", "CSNY"),
        _track(2, "Helpless", "CSNY"),
        _track(3, "Woodstock", "CSNY"),
    ]
    results = [{"title": "Ohio", "artist": "CSNY", "tempo": 1}]

    _run(tracks, results, {"Helpless": [{"tempo": 2}]})

    out = capsys.readouterr().out
    assert "Retrying 2 track(s)" in out
    assert "Classified 2/3" in out


def test_a_recovered_track_is_written_once() -> None:
    """Recovery must not re-write a row the batch already counted."""
    tracks = [_track(1, "Ohio", "CSNY")]
    results = [{"title": "Ohio", "artist": "CSNY", "tempo": 1}]
    retries = {"Ohio": [{"tempo": 99}]}

    db, _, count = _run(tracks, results, retries)

    assert count == 1
    assert db.update_track_metadata.call_count == 1
    assert _written(db)[1]["tempo"] == 1
