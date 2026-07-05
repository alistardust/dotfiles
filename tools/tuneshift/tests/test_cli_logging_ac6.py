"""FL2 AC6: enrichment is no longer silent -- global -v/-q logging to stderr.

Nothing configured the root logger, so every enrichment ``logger.info`` line
(classification, derived tags, energy/valence estimates) was invisible. AC6:
progress visible by default, ``-v`` shows per-source detail, ``-q`` suppresses
it -- all on stderr so stdout stays clean for piping.
"""

from __future__ import annotations

import logging
import sys

import pytest

from tuneshift.cli import _configure_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    root = logging.getLogger()
    saved = root.level, list(root.handlers)
    yield
    root.handlers[:] = saved[1]
    root.setLevel(saved[0])


def _make_args(verbose=0, quiet=False):
    class _A:
        pass

    a = _A()
    a.verbose = verbose
    a.quiet = quiet
    return a


def test_default_is_info_progress_on_stderr():
    _configure_logging(_make_args())
    root = logging.getLogger()
    assert root.level == logging.INFO
    handler = root.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr


def test_verbose_drops_to_debug_with_source_annotation():
    _configure_logging(_make_args(verbose=1))
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert "%(name)s" in root.handlers[0].formatter._fmt


def test_quiet_suppresses_below_warning():
    _configure_logging(_make_args(quiet=True))
    assert logging.getLogger().level == logging.WARNING


def test_quiet_wins_over_verbose():
    _configure_logging(_make_args(verbose=2, quiet=True))
    assert logging.getLogger().level == logging.WARNING


def test_enrichment_info_visible_by_default(capsys):
    _configure_logging(_make_args())
    logging.getLogger("tuneshift.library.enrichment").info("classified track: A - B")
    assert "classified track: A - B" in capsys.readouterr().err
