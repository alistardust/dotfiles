# tests/where-were-we/test_render.py
import pytest
import wwm_render


def test_short_row_puts_tag_on_the_same_line():
    lines = wwm_render.row("Next", "Write the spec", "rec")
    assert len(lines) == 1
    assert lines[0].startswith("  Next")
    assert lines[0].endswith("[rec]")
    assert len(lines[0]) == 72


def test_long_row_wraps_and_tags_the_last_line():
    text = (
        "Hybrid data source, tiny default tier, recorded versus inferred "
        "labeled clearly, and Copilot CLI only for version one"
    )
    lines = wwm_render.row("Decided", text, "rec")
    assert len(lines) >= 2
    assert all(len(line) <= 72 for line in lines)
    assert lines[-1].endswith("[rec]")
    assert lines[1].startswith(" " * 12)


def test_continuation_lines_align_to_the_text_column():
    lines = wwm_render.row("Discussed", "word " * 40, "inf")
    for line in lines[1:]:
        assert line[:12] == " " * 12


def test_no_line_ever_exceeds_72(fake_home):
    for length in range(1, 400):
        for label in ("Next", "Discussed", "Decided"):
            for tag in ("rec", "inf"):
                lines = wwm_render.row(label, "x" * length, tag)
                assert all(len(line) <= 72 for line in lines), (label, length)


def test_unbreakable_token_is_truncated_not_overflowed():
    lines = wwm_render.row("Files", "a" * 200, "inf")
    assert all(len(line) <= 72 for line in lines)


def test_tag_is_always_present():
    lines = wwm_render.row("State", "mid-design", "inf")
    assert lines[-1].endswith("[inf]")


def test_markdown_noise_is_stripped_before_wrapping():
    """Checkpoint text arrives markdown-authored and renders as noise here."""
    lines = wwm_render.row("Next", "**Immediate:** run `pytest` now", "rec")
    body = "".join(lines)
    assert "**" not in body
    assert "`" not in body
    assert "Immediate:" in body


BUNDLE = {
    "session_id": "s1",
    "goal": "Design a session-summary skill",
    "adopted_from": None,
    "origin": [{"turn_index": 0, "text": "let us build a summary skill"}],
    "items": [
        {
            "label": "Decided",
            "text": "Approach B, scripts plus skill",
            "why": "format must be deterministic",
            "rejected": "pure prompt",
            "source": "rec",
            "date": "2026-08-05",
        },
        {"label": "Next", "text": "Write the implementation plan", "source": "rec"},
        {"label": "State", "text": "Mid-design, spec approved", "source": "inf"},
        {"label": "Thread", "text": "Instruction wording", "source": "rec"},
        {"label": "Discussed", "text": "Whether to use Rust", "source": "inf"},
    ],
    "files": ["setup.sh", "sections/_helpers.sh"],
    "stale": False,
    "has_ledger": True,
    "insufficient": False,
}


def test_tldr_is_eight_lines_or_fewer():
    out = wwm_render.render(BUNDLE, level="tldr", prose="Picking up a design session.")
    assert len(out.splitlines()) <= 8


def test_tldr_holds_at_eight_across_prose_lengths():
    """Regression: the budget once forgot the blank line before the menu.

    That produced nine lines. Sweep prose length so the off-by-one cannot
    return.
    """
    for words in range(120):
        prose = "word " * words
        out = wwm_render.render(BUNDLE, level="tldr", prose=prose)
        assert len(out.splitlines()) <= 8, f"{words} words -> {len(out.splitlines())}"


def test_long_prose_is_truncated_rather_than_starving_the_facts():
    out = wwm_render.render(BUNDLE, level="tldr", prose="word " * 200)
    lines = out.splitlines()
    assert lines[1].endswith("...")
    assert lines[2] == ""
    # The label block still got room for at least one sourced fact.
    assert any("[rec]" in line or "[inf]" in line for line in lines)


def test_tldr_always_ends_with_the_menu():
    out = wwm_render.render(BUNDLE, level="tldr", prose="Picking up.")
    assert out.splitlines()[-1].endswith(wwm_render.MENU)


def test_history_only_session_still_shows_facts():
    """Regression, CRITICAL. TLDR_PRIORITY once omitted the history labels.

    A session with no ledger and no checkpoint rendered prose plus a menu and
    nothing else. An empty answer that looks complete is the worst outcome for
    a memory aid.
    """
    bundle = {
        **BUNDLE,
        "has_ledger": False,
        "items": [
            {"label": "Discussed", "text": "Kafka retention settings", "source": "inf"},
            {
                "label": "Discussed",
                "text": "Compared us-east-1 and -2",
                "source": "inf",
            },
        ],
    }
    out = wwm_render.render(bundle, level="tldr", prose="Picking up.")
    assert sum("[inf]" in line for line in out.splitlines()) >= 1


def test_oversized_first_item_is_shortened_not_dropped():
    """Regression, CRITICAL. The budget loop broke on the first item.

    When the first item did not fit, the body ended up with zero facts.
    """
    bundle = {
        **BUNDLE,
        "items": [
            {"label": "Decided", "text": "x" * 600, "source": "rec"},
            {"label": "Next", "text": "short", "source": "rec"},
        ],
    }
    out = wwm_render.render(bundle, level="tldr", prose="word " * 40)
    assert any("[rec]" in line for line in out.splitlines())
    assert len(out.splitlines()) <= 8


def test_no_single_item_consumes_the_whole_tldr():
    bundle = {
        **BUNDLE,
        "items": [
            {"label": "Next", "text": "y" * 500, "source": "inf"},
            {"label": "State", "text": "z" * 500, "source": "inf"},
        ],
    }
    out = wwm_render.render(bundle, level="tldr", prose="Short.")
    assert sum("[inf]" in line for line in out.splitlines()) == 2


def test_truncation_is_stated_not_silent():
    bundle = {
        **BUNDLE,
        "items": [
            {"label": "Decided", "text": f"decision {n}", "source": "rec"}
            for n in range(9)
        ],
    }
    out = wwm_render.render(bundle, level="tldr", prose="Short.")
    assert "more." in out.splitlines()[-1]


def test_markdown_noise_is_stripped():
    bundle = {
        **BUNDLE,
        "items": [
            {
                "label": "Next",
                "text": "**Immediate:** run `pytest` now",
                "source": "inf",
            }
        ],
    }
    out = wwm_render.render(bundle, level="tldr", prose="Short.")
    assert "**" not in out and "`" not in out
    assert "Immediate: run pytest now" in out


def test_damaged_ledger_is_disclosed():
    bundle = {**BUNDLE, "ledger_damaged": ["decisions"]}
    out = wwm_render.render(bundle, level="tldr", prose="")
    assert "unreadable in ledger: decisions" in out


def test_every_line_within_72_at_every_level():
    for level in ("tldr", "summary", "full"):
        out = wwm_render.render(BUNDLE, level=level, prose="Picking up a session.")
        assert all(len(line) <= 72 for line in out.splitlines()), level


def test_full_level_may_be_long_but_still_wrapped():
    out = wwm_render.render(BUNDLE, level="full", prose="Picking up.")
    assert len(out.splitlines()) > 8
    assert all(len(line) <= 72 for line in out.splitlines())


def test_sections_render_only_their_own_content():
    out = wwm_render.render(BUNDLE, level="summary", section="threads", prose="")
    assert "Instruction wording" in out
    assert "Approach B" not in out


def test_unknown_section_is_refused_not_guessed():
    with pytest.raises(wwm_render.UnknownSection):
        wwm_render.render(BUNDLE, level="summary", section="banana", prose="")


def test_prose_is_dropped_when_empty_without_leaving_a_blank():
    out = wwm_render.render(BUNDLE, level="tldr", prose="")
    assert not out.startswith("\n")


def test_prose_is_wrapped_to_72():
    out = wwm_render.render(BUNDLE, level="tldr", prose="word " * 60)
    assert all(len(line) <= 72 for line in out.splitlines())


def test_stale_bundle_says_so():
    stale = {**BUNDLE, "stale": True}
    out = wwm_render.render(stale, level="tldr", prose="")
    assert "behind" in out.lower() or "newer" in out.lower()


def test_insufficient_bundle_refuses_plainly():
    empty = {**BUNDLE, "items": [], "origin": [], "insufficient": True}
    out = wwm_render.render(empty, level="tldr", prose="")
    assert "not enough" in out.lower()
    assert "[rec]" not in out and "[inf]" not in out


def test_adopted_ledger_is_disclosed():
    adopted = {**BUNDLE, "adopted_from": "old-session-id"}
    out = wwm_render.render(adopted, level="tldr", prose="")
    assert "adopted" in out.lower()


def test_sessions_table_survives_a_multiline_summary():
    """Regression. A real session was titled "How to talk to me in this
    session:\n\n- W...", and the bare slice in the CLI broke it into three
    ragged lines that destroyed every column in the table."""
    rows = [
        {
            "summary": "How to talk to me in this session:\n\n- Wrap at 80\n- Ask",
            "repository": "alistardust/dotfiles",
            "updated_at": "2026-08-06T12:00:00Z",
        }
    ]
    out = wwm_render.sessions_table(rows, total=1, days=14)
    assert len(out.splitlines()) == 1
    assert all(len(line) <= wwm_render.TOTAL for line in out.splitlines())


def test_sessions_table_never_exceeds_the_fixed_width():
    rows = [
        {"summary": "s" * 200, "repository": "r" * 200, "updated_at": "2026-08-06"}
    ] * 5
    out = wwm_render.sessions_table(rows, total=99, days=14)
    assert all(len(line) <= wwm_render.TOTAL for line in out.splitlines())


def test_sessions_table_tolerates_missing_fields():
    rows = [{"summary": None, "repository": None, "updated_at": None}]
    out = wwm_render.sessions_table(rows, total=1, days=14)
    assert "(no summary)" in out
    assert all(len(line) <= wwm_render.TOTAL for line in out.splitlines())


def test_sessions_table_says_so_when_there_is_nothing():
    out = wwm_render.sessions_table([], total=0, days=14)
    assert "No sessions" in out


def test_sessions_table_counts_the_remainder():
    rows = [{"summary": "a", "repository": "b", "updated_at": "2026-08-06"}]
    out = wwm_render.sessions_table(rows, total=20, days=14)
    assert "19 more in the last 14 days" in out


def test_tldr_orients_before_it_directs():
    """State outranks Next by explicit user decision.

    The question this skill is named after is "where am I", so orienting comes
    before acting. Nothing pinned the order before, which meant the decision
    could be reversed by an unrelated edit without a single test noticing.
    """
    order = wwm_render.TLDR_PRIORITY
    assert order.index("State") < order.index("Next")
    assert order.index("Decided") < order.index("State")

    bundle = {
        "items": [
            {"label": "Next", "text": "run the migration", "source": "inf"},
            {"label": "State", "text": "halfway through the rewrite", "source": "inf"},
        ],
        "origin": [],
    }
    out = wwm_render.render(bundle, level="tldr", prose="")
    assert out.index("halfway through the rewrite") < out.index("run the migration")


def test_tldr_never_comes_back_empty_when_the_first_item_cannot_fit():
    """The renderer's most important safety net, and it was untested. An empty
    body reads as a confident 'nothing to report', which is the worst possible
    failure for a memory aid: it looks like an answer and carries nothing.

    The trigger is a maximally degraded session: an adopted ledger, stale
    content, unreadable history and a damaged heading all emit a note, which
    leaves exactly one line of budget for an item that wants two. Squeeze it
    rather than dropping it.
    """
    bundle = {
        "items": [
            {"label": "Decided", "text": "x" * 300, "source": "rec"},
            {"label": "Next", "text": "y" * 300, "source": "rec"},
        ],
        "origin": [],
        "adopted_from": "abcdef123456",
        "stale": True,
        "has_history": False,
        "ledger_damaged": ["Decisions"],
    }
    out = wwm_render.render(bundle, "tldr")
    assert "Decided" in out, "tldr rendered with zero facts"
    assert len(out.splitlines()) <= wwm_render.TLDR_MAX_LINES
    assert max(len(ln) for ln in out.splitlines()) <= wwm_render.TOTAL
    assert "+1 more" in out, "omitted count lost when the fallback fired"


def test_an_unknown_level_is_refused_rather_than_guessed():
    """LEVELS is ("tldr", "summary", "full"); anything else must refuse rather
    than silently falling through to a default shape."""
    with pytest.raises(ValueError, match="unknown level"):
        wwm_render.render({"items": [], "origin": [], "damaged": []}, "brief")


def test_ellipsize_does_not_pad_a_column_narrower_than_its_marker():
    """Under four characters there is no room for both text and '...', so the
    marker is dropped rather than overflowing the column and breaking width."""
    assert wwm_render._ellipsize("abcdef", 3) == "abc"
    assert wwm_render._ellipsize("abcdef", 2) == "ab"
    assert wwm_render._ellipsize("ab", 5) == "ab"
    assert wwm_render._ellipsize("abcdef", 5) == "ab..."


def test_fit_honours_its_never_empty_contract_even_at_zero_budget():
    """_fit's docstring promises it never returns empty; before the clamp a
    zero budget made that false. render() never asks for zero today, but a
    helper whose stated contract is a lie is a trap for the next caller."""
    item = {"label": "Decided", "text": "chose python for the parser", "source": "rec"}
    for budget in (0, -3):
        out = wwm_render._fit(item, budget)
        assert out, f"_fit returned nothing at budget {budget}"
        assert max(len(ln) for ln in out) <= wwm_render.TOTAL


def test_fit_shortens_rather_than_overflowing_a_tight_budget():
    item = {"label": "Decided", "text": "z" * 500, "source": "rec"}
    out = wwm_render._fit(item, 1)
    assert len(out) == 1
    assert len(out[0]) <= wwm_render.TOTAL
    assert "[rec]" in out[0], "source tag lost while shortening"


def test_fit_still_labels_an_item_whose_text_is_empty():
    """An empty text would otherwise render as a bare label with no tag. The
    label plus an ellipsis at least says 'there was something here'."""
    out = wwm_render._fit({"label": "Decided", "text": "", "source": "rec"}, 2)
    assert out
    assert "Decided" in out[0] and "[rec]" in out[0]


def test_status_notes_never_crowd_out_every_fact():
    """The worst failure this skill can produce: prose plus apologies with no
    facts under them, while still announcing "newer turns folded in below".

    Two notes plus a two-line prose drove the tldr budget to zero, and the
    "at least one fact" guard was itself gated on the budget being positive,
    so it never ran. Adopting a stranded ledger and doing a little work is
    exactly when the recorded facts are the only reliable record.
    """
    prose = (
        "Carrying the design-session ledger forward into this new session and "
        "picking up right where the earlier thread left off before the reboot."
    )
    bundle = {
        "items": [
            {"label": "Decided", "text": "chose python", "source": "rec"},
            {"label": "Next", "text": "wire the CLI", "source": "rec"},
            {"label": "Blocked", "text": "vendor cert", "source": "rec"},
        ],
        "origin": [],
        "adopted_from": "a1b2c3d4e5f6",
        "stale": True,
    }
    out = wwm_render.render(bundle, "tldr", prose=prose)
    facts = [ln for ln in out.splitlines() if "[rec]" in ln or "[inf]" in ln]
    assert facts, "tldr returned prose and apologies with zero facts"
    assert len(out.splitlines()) <= wwm_render.TLDR_MAX_LINES
    assert max(len(ln) for ln in out.splitlines()) <= wwm_render.TOTAL
    # Collapsing the notes must not silently hide that they existed.
    assert "notes" in out


def test_a_long_hand_typed_heading_cannot_break_the_fixed_width():
    """Damage notes quote names straight out of the user's ledger, so nothing
    upstream bounds their length. Emitted raw, one invented heading produced a
    109-character line and shattered the layout."""
    bundle = {
        "items": [{"label": "Decided", "text": "chose python", "source": "rec"}],
        "origin": [],
        "ledger_damaged": [
            "a-very-long-hand-typed-heading-name-that-someone-invented",
            "another-equally-long-one",
        ],
    }
    for level in ("tldr", "summary", "full"):
        out = wwm_render.render(bundle, level)
        widest = max(len(ln) for ln in out.splitlines())
        assert widest <= wwm_render.TOTAL, f"{level} produced a {widest}-char line"
