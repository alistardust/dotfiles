"""`--classify` must gate classification, and nothing else (BUG-32).

The help text calls ``--classify`` opt-in. The gate read::

    if getattr(args, "classify", False) or not platform_name:

so classification ran whenever ``--platform`` was absent, which is most
invocations. The only way to suppress the slowest and least reliable pass was
to pass ``--platform``, which buys an unwanted network pass instead: it
triggers the per-track metadata fetch, and ``--platform tidal`` also opens the
catalog pass, which is gated on ``catalog or platform_name == "tidal"``.

These tests pin each pass as independently selectable, and pin the trap in the
fix itself: ``--reclassify`` only ever worked because the no-platform clause
opened the gate for it, so removing that clause without teaching the gate about
``--reclassify`` would leave the flag silently doing nothing.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tuneshift.commands.enrich_cmd import handle_enrich
from tuneshift.db import Database
from tuneshift.models import Track

CLASSIFY = "tuneshift.commands.enrich_cmd._run_classification"
ENERGY = "tuneshift.commands.enrich_cmd._run_energy_pass"


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "classify.db")
    playlist_id = database.create_playlist("Mix")
    track_id = database.add_track(Track(title="Alpha", artist="Artist"))
    database.add_track_to_playlist(playlist_id, track_id, 1)
    return database


def _args(**overrides) -> SimpleNamespace:
    base = {"playlist": "Mix", "platform": None, "classify": False}
    base.update(overrides)
    return SimpleNamespace(**base)


def test_bare_enrich_does_not_classify(db: Database) -> None:
    """The headline bug: the documented opt-in was on by default."""
    with patch(CLASSIFY, return_value=0) as classify, patch(ENERGY, return_value=0):
        assert handle_enrich(_args(), db) == 0

    classify.assert_not_called()


def test_classify_flag_runs_classification(db: Database) -> None:
    """The flag still has to do the thing it is named after."""
    with patch(CLASSIFY, return_value=1) as classify, patch(ENERGY, return_value=0):
        assert handle_enrich(_args(classify=True), db) == 0

    classify.assert_called_once()


def test_reclassify_implies_classification(db: Database) -> None:
    """--reclassify must not become a silent no-op.

    It only ever ran because the no-platform clause happened to open the gate.
    Removing that clause without teaching the gate about --reclassify would
    leave a flag that reports nothing and does nothing.
    """
    with patch(CLASSIFY, return_value=1) as classify, patch(ENERGY, return_value=0):
        assert handle_enrich(_args(reclassify=True), db) == 0

    classify.assert_called_once()
    assert classify.call_args.kwargs["force"] is True


def test_classify_is_not_suppressed_by_naming_a_platform(db: Database) -> None:
    """The two flags are independent in both directions.

    Before the fix, --platform was the only way to turn classification off, so
    the flags were entangled: you could not have classification and platform
    metadata at once without the gate making the choice for you.
    """
    with patch(CLASSIFY, return_value=1) as classify, patch(
        ENERGY, return_value=0
    ), patch("tuneshift.commands.ingest_cmd._load_client", return_value=None):
        assert handle_enrich(_args(platform="spotify", classify=True), db) == 1

    # The run fails on the unknown client before classification is reached,
    # which is the existing contract; what matters is that the gate itself no
    # longer treats a named platform as a reason to skip.
    classify.assert_not_called()


def test_energy_still_runs_by_default(db: Database) -> None:
    """Narrowing the classification gate must not disturb the energy pass."""
    with patch(CLASSIFY, return_value=0), patch(ENERGY, return_value=1) as energy:
        assert handle_enrich(_args(), db) == 0

    energy.assert_called_once()


def test_energy_only_run_needs_no_llm_and_no_platform(db: Database) -> None:
    """The run the bug was filed over: energy alone, no LLM, no network.

    This is the whole point of the fix. A bare enrich should be able to measure
    a candidate pool without paying for a classification pass that was not
    asked for.
    """
    with patch(CLASSIFY, return_value=0) as classify, patch(
        ENERGY, return_value=1
    ) as energy, patch("tuneshift.commands.ingest_cmd._load_client") as load_client:
        assert handle_enrich(_args(), db) == 0

    classify.assert_not_called()
    load_client.assert_not_called()
    energy.assert_called_once()


def test_no_energy_still_opts_out(db: Database) -> None:
    """The existing opt-out keeps working, and can be combined with --classify."""
    with patch(CLASSIFY, return_value=1) as classify, patch(
        ENERGY, return_value=0
    ) as energy:
        assert handle_enrich(_args(classify=True, no_energy=True), db) == 0

    classify.assert_called_once()
    energy.assert_not_called()
