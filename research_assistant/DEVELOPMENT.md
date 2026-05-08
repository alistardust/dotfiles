# Research Assistant -- Development Guide

This guide covers the developer workflow: environment setup, architecture
quick-reference, testing standards, documentation rules, and git workflow.

This project follows the same architecture and conventions as `tachikoma`
(io_sre_tools). Patterns established there apply here unless explicitly
overridden below.

**Doing things correctly takes precedence over doing them quickly.** A
solution that cuts corners on architecture, testing, or documentation is not
done. Take the extra time to do it right.

---

## Contents

- [Environment](#environment)
- [Architecture quick-reference](#architecture-quick-reference)
- [Adding a new command or module](#adding-a-new-command-or-module)
- [CLI conventions](#cli-conventions)
- [Testing](#testing)
- [Help text](#help-text)
- [Documentation](#documentation)
- [Git conventions](#git-conventions)

---

## Environment

```bash
# One-time setup
python -m venv .venv
source .venv/bin/activate

# Install in editable mode with dev dependencies
uv pip install -e ".[dev]"

# Install with agent extras
uv pip install -e ".[agent,dev]"

# Verify
<package> --version
```

Python 3.12+ required. Use `uv` for all package operations -- never raw
`pip install`. New dependencies go in `pyproject.toml` first.

---

## Architecture quick-reference

The key structural rule is absolute:

```
cli.py    -- Click layer: option parsing, output, sys.exit(). No business logic.
client.py -- Logic layer: API calls, data work, exceptions. No Click imports.
```

All config access goes through `config.py`. Never read config files directly
in module code.

Every new module must be registered in the root `cli.py` with
`main.add_command(<group>)`. An unregistered module is unreachable.

Error pattern (never deviate):
```python
click.echo(click.style(f"Error: {msg}", fg="red"), err=True)
sys.exit(1)
```

### Agent module layout

```
<package>/
    cli.py
    client.py
    config.py
    agent/
        cli.py          -- agent chat CLI entry point
        loop.py         -- agent_chat() backend; accepts cancel_event
        security.py     -- scan_messages() input validation
        memory/
            __init__.py
            db.py           -- SQLite schema + migrations + get_connection()
            embeddings.py   -- OllamaEmbedder: ensure_running(), embed(), stop()
            summarizer.py   -- MemorySummarizer: summarize, extract_technical_notes, extract_facts
            store.py        -- MemoryStore: start_session, update_summary, end_session, search
        tools/
            __init__.py     -- ToolDef registry: register(), dispatch_tool(), get_tool_definitions()
            memory.py       -- search_memory tool + set_memory_store() singleton
        tui/
            app.py          -- TachiApp(App): root Textual app, memory wiring, clean exit
            scrollback.py   -- ScrollbackPane(RichLog): message history
            input_box.py    -- InputBox(TextArea): user input, vim mode
            status_bar.py   -- StatusBar(Widget): mode indicator, loading state
            controller.py   -- SessionController: worker thread, slash commands, memory
            config.py       -- TuiConfig dataclass + load_tui_config()
            vim.py          -- VimMode state machine
```

---

## Adding a new command or module

### New command on an existing group

1. Add the command function to the relevant `cli.py`.
2. Add business logic to `client.py`.
3. Write tests in `tests/test_<module>.py`.
4. Update `--help` text to describe the new behavior accurately.
5. Update the README command reference for that subsystem.
6. Add a `CHANGELOG.md` entry under `## [Unreleased]`.

### New module (new top-level subcommand)

1. Create `<package>/<module>/` with `__init__.py`, `cli.py`, `client.py`.
2. Export a single `@click.group("<name>")` from `cli.py`.
3. **Register it in `<package>/cli.py`** with `main.add_command(<group>)`.
   Verify with `<package> --help` after adding.
4. Create `tests/test_<module>.py` with happy-path and error-case coverage.
5. Add a section to `README.md` under `## Commands`.
6. Add a `CHANGELOG.md` entry.
7. If new config keys are introduced, update the sample config.

A module that is not documented, not tested, and not registered is not done.

### New agent tool

Tools are registered via `register(ToolDef(...))` at module import time.
`_load_tools()` in `tools/__init__.py` imports each tool module to trigger
registration. To add a new tool:

1. Create `tools/<name>.py` with a handler function and a `register(ToolDef(...))`
   call at module level.
2. Add `from <package>.agent.tools import <name> as _<name>  # noqa: F401` to
   `_load_tools()` in `tools/__init__.py`.
3. Set `tier=0` for read-only tools. Tier 1+ require confirmation plumbing
   (not yet implemented -- register but dispatching will raise ToolError).
4. Write tests in `tests/test_<name>_tool.py` covering all handler branches
   plus `test_tool_registered_in_definitions`.

---

## CLI conventions

### `-h` / `--help`

All commands support both `-h` and `--help`. Enforced globally by
`CONTEXT_SETTINGS` on the root group:

```python
CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])

@click.group(context_settings=CONTEXT_SETTINGS)
def main(): ...
```

**Do not override `help_option_names` on individual commands.**

### Options

- All options must have `help=` text.
- Non-obvious defaults must use `show_default=True`.
- Destructive operations require `@click.confirmation_option` or `--yes`.

### Output

- Success: plain `click.echo()`.
- Warnings: `click.echo(click.style(..., fg="yellow"), err=True)`.
- Errors: `click.echo(click.style(f"Error: {msg}", fg="red"), err=True)` then `sys.exit(1)`.
- Never use `print()` -- always `click.echo()`.

---

## Testing

### Requirements

- Every new function or behavior must have a test. Code without tests is not done.
- Every bug fix must include a regression test.
- When changing existing code, update tests that no longer reflect real behavior.
- Run the full test suite before and after any code change.

```bash
.venv/bin/pytest tests/ -v
.venv/bin/pytest tests/test_memory_db.py -v      # single module
.venv/bin/pytest tests/ -k "search"              # filter by name
```

### File and class conventions

- Test files: `tests/test_<module>.py` matching the module they cover.
- Organize with `class Test<Feature>`: one class per logical unit.
- Descriptive method names: `test_returns_none_when_not_found`, not `test_1`.

### Mocking

- HTTP calls: use `requests-mock` pytest fixture.
- Filesystem, subprocess, OS calls: use `unittest.mock.patch`.
- **Never make live network calls in tests.**
- Use `tmp_path` for any test that reads or writes files.
- For memory tests: use `tmp_path / "mem.db"` and call `migrate(conn)` to get
  a clean, versioned schema.

### What to cover

| Category | What to test |
|----------|-------------|
| Happy path | Expected behavior with valid inputs |
| Error cases | Network failures, missing config, invalid input -- confirm loud failure |
| Edge cases | Empty list inputs, None, pagination boundaries |
| FTS5 triggers | Insert, update, and delete triggers on both `sessions_fts` and `facts_fts` |
| Empty inputs | `summarize_messages([])`, `extract_facts([], [])` -- no API call made |
| Tool wiring | CLI-level test that patches the client constructor and asserts correct types |

### pytest-asyncio config

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Async Pilot tests (Textual) need no decorator in this mode.

---

## Help text

Help text is the inline reference for every command. It must always be accurate.

Update `--help` text whenever:
- A new option is added or removed.
- An option's behavior, default, or name changes.
- The command's behavior changes significantly.
- A new fallback, safety filter, or side effect is introduced.

A code change that affects command behavior is **not complete** until help
text reflects it.

Every command must have:
- A one-line summary (first line of docstring, under ~72 characters)
- `help=` text on every option
- At least one `\b` example block with realistic usage

---

## Documentation

A code change that affects user-visible behavior is not complete until all of
the following are updated:

| Document | When to update |
|----------|---------------|
| `--help` text | Any new/changed option, behavior, fallback, or side effect |
| `README.md` | Any new/changed/removed command, flag, or config key |
| `CHANGELOG.md` | Every user-visible change -- add under `## [Unreleased]` |
| `DEVELOPMENT.md` | When a workflow rule or convention changes |

Follow [Keep a Changelog](https://keepachangelog.com/) for `CHANGELOG.md`.
Entries are user-facing -- describe from the perspective of someone using
the tool, not from the diff.

One source of truth: do not duplicate content between README, help text,
and code comments. `--help` is the inline reference; README is the narrative
guide.

---

## Security rules

- Never fabricate sources, citations, statistics, or quotes.
- PHI and PII: flag immediately, request guidance, do not proceed without it.
- On politically sensitive topics: present multiple credible perspectives,
  clearly labeled. Do not advocate for policy positions.
- Config files containing credentials must be `chmod 0o600`.
- Never use `shell=True` with subprocess -- always pass argument lists.
- No live network calls in tests.

---

## Git conventions

### Commits

Conventional Commits: `<type>: <description>`.
Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

- Subject line under 72 characters.
- Body explains what changed AND why.

AI-assisted commits include:
```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

### Branches

This project has no ticket system. Always use descriptive slugs:

```
feature/<description>
fix/<description>
chore/<description>
```

Examples: `feature/memory-system`, `feature/vim-mode`, `chore/update-deps`

No placeholder project codes. No ticket IDs.

### Parallel branch workflow

Main clone at `~/git/<repo>/` stays on default branch at all times. Feature
work goes in a worktree:

```bash
git worktree add ~/git/parallels/<repo>/<branch-name> -b <branch-name>
cd ~/git/parallels/<repo>/<branch-name>
```

Remove after merging:
```bash
git worktree remove ~/git/parallels/<repo>/<branch-name>
```

### PR descriptions

Every PR must include:
- What changed and why
- Risks or irreversible effects
- What testing was done
