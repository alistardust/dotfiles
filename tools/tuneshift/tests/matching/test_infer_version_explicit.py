"""infer_version honors a structured explicit flag over title text (Task 3)."""

from tuneshift.matching.version import infer_version


def test_structured_explicit_true_sets_is_explicit():
    p = infer_version("Song", "Album", None, explicit=True)
    assert p.is_explicit is True and p.is_clean is False


def test_structured_explicit_false_sets_is_clean():
    p = infer_version("Song", "Album", None, explicit=False)
    assert p.is_clean is True and p.is_explicit is False


def test_unknown_flag_falls_back_to_text_regex():
    # No structured flag, no marker -> neutral (parity with today).
    p = infer_version("Song", "Album", None)
    assert p.is_explicit is False and p.is_clean is False
    # Title marker still works when the flag is unknown.
    assert infer_version("Song (Clean)", "Album", None).is_clean is True
