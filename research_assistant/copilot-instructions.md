# Copilot Instructions -- Research Assistant

A personal research assistant TUI -- similar in architecture and design to
`tachikoma` (io_sre_tools), but focused on academic research, political analysis,
economics, social science, data science, and general research project management
rather than SRE/DevOps workflows.

The authoritative developer reference is **`DEVELOPMENT.md`** at the repo root.
This file adds project-specific context on top of any global Copilot instructions.

---

## Architecture

This project follows the same architecture as tachikoma. All patterns established
there apply here unless explicitly overridden below.

### Module structure

```
<package>/
    __init__.py
    cli.py              -- Click entry point ONLY; no business logic
    client.py           -- Business logic; no Click imports
    config.py           -- Config loading and dataclass
    agent/
        cli.py          -- agent chat CLI entry point
        loop.py         -- agent_chat() backend; accepts cancel_event
        security.py     -- scan_messages() input validation
        tui/
            app.py      -- TachiApp(App) -- root textual app
            scrollback.py  -- ScrollbackPane(RichLog) -- message history
            input_box.py   -- InputBox(TextArea) -- user input widget
            status_bar.py  -- StatusBar(Widget) -- status display
            controller.py  -- SessionController -- business logic bridge
            config.py      -- TuiConfig dataclass + load_tui_config()
            vim.py         -- VimMode state machine
```

### cli.py / client.py split (absolute)

- Click imports, decorators, and group/command definitions: `cli.py` ONLY
- Business logic, API calls, data processing: `client.py` ONLY
- `client.py` never imports Click
- This boundary is enforced in every module

### Error handling

Errors print to stderr in red and call `sys.exit(1)`. The pattern:

```python
click.echo(click.style(f"Error: {msg}", fg="red"), err=True)
sys.exit(1)
```

Never silently swallow errors. Never exit 0 on failure.

### Help flags

The root group's `CONTEXT_SETTINGS` propagates `-h` to all subcommands automatically.
Do not override `help_option_names` on individual commands.

---

## TUI Architecture

The TUI is built with `textual`. Key decisions locked in from design:

### Component hierarchy

```
TachiApp(App)
  Layout
    ScrollbackPane(RichLog)   -- message history, markup=True
    StatusBar(Widget)          -- mode indicator, loading state
    InputBox(TextArea)         -- user input, optional vim mode
```

### Critical textual API facts

- `RichLog` requires `markup=True` in constructor for Rich markup to render
- `App.suspend()` is a `@contextmanager` -- use `with self.app.suspend(): ...`
  NEVER call `suspend()` and `resume()` as standalone methods
- `call_from_thread()` is ONLY valid from worker threads; calling it from the
  UI thread raises RuntimeError -- always check which thread you are on
- `thread.join(timeout)` blocks the calling thread -- acceptable at shutdown,
  never acceptable mid-session
- In `_on_key()`, only pass single printable ASCII chars to VimMode.on_key();
  navigation keys (arrows, home, end, page up/down) fall through to TextArea default

### Threading model

```
UI thread (textual event loop)
  |-- handles all widget events, key presses, rendering
  |-- calls controller methods directly (no call_from_thread)
  |
  +-- spawns daemon threading.Thread for agent_chat()
        |-- worker thread: calls agent, handles cancellation
        +-- calls app.call_from_thread(callback) to post results back to UI
```

- Never use `asyncio.run()` in worker threads
- Never use `time.sleep()` in the UI thread
- Set `_worker_thread` attribute before starting; check `worker.is_alive()` in
  `cancel()` to avoid posting `[cancelled]` after worker has already finished

### Cancellation

- `SessionController.cancel()` checks `worker.is_alive()` before posting `[cancelled]`
  to prevent the race where worker finishes and callback is queued simultaneously
- `agent_chat()` accepts `cancel_event: threading.Event | None = None`
- Cancellation is best-effort between tool rounds; not preemptive

### Security scanning

`scan_messages()` in `security.py` returns `(clean_messages, flagged_events)` --
always unpack both values. If `flagged` is non-empty, reject input and fail CLOSED:

```python
_clean, flagged = scan_messages([{"role": "user", "content": text}])
if flagged:
    self.scrollback.append_system("Input rejected: possible prompt injection.")
    return False
```

If the security module is unavailable, fail CLOSED (reject, warn -- never silently pass).

### Vim mode

- `VimMode` state machine in `vim.py`; `on_key(char: str, is_paste: bool) -> (action, payload)`
- Only single printable ASCII characters enter `VimMode.on_key()` -- filter in `_on_key()`
- `vim_escape` sequence is configurable (default `"jj"`); single-char sequences complete immediately
- `Ctrl+[` is indistinguishable from Escape at terminal level -- not supported as vim escape
- Escape = cancel in-flight request (if any); no-op when idle (Phase 1)
- NORMAL mode navigation: `h/j/k/l`, `w/b`, `0/$`, `G/gg` mapped to TextArea actions

### `/edit` slash command

Opens the current input in `$EDITOR`. Pattern:

```python
with self.app.suspend():
    # editor runs here with full terminal access
    subprocess.run([editor, tmpfile])
# resume is automatic on context manager exit
```

Read the file BEFORE deleting it:

```python
content = tmp.read_text()
tmp.unlink()
```

---

## Memory System

The agent uses a three-layer memory architecture. All memory operations are
best-effort and never block the chat loop.

### Layer 1 -- Working memory (sliding window)

`loop.py` trims `messages` to the last `_MAX_HISTORY_MESSAGES = 30` entries
before building each API payload. The controller's display list is never
modified -- trimming is a read-side safety net only.

### Layer 2 -- Session memory (in-session narrative compression)

`SessionController._detect_and_summarize_aged()` is called from `submit()`
before launching the worker thread. When `len(self.messages)` exceeds the
window, the aged batch is summarized by `MemorySummarizer.summarize_messages()`
and stored in `self._session_summary`. The worker receives this via
`_run_worker(messages, cancel_event, session_summary)`, which passes it to
`agent_chat(session_summary=...)`. The loop injects it as a
`--- EARLIER IN THIS SESSION ---` content block between the system prompt
and the live window.

Periodic flush: every `flush_every_n_turns` (default 10) turns, `_on_reply()`
spawns a daemon thread to call `MemoryStore.update_session_summary()` with a
fresh embedding. This never runs on the UI thread.

### Layer 3 -- Persistent memory (SQLite + Ollama)

Database: `~/.config/<appname>/memory.db` (WAL mode, FTS5).

Schema tables:
- `sessions` -- id, nick, started_at, ended_at, summary, technical_notes,
  embedding (BLOB), turn_count
- `facts` -- id, category, fact_text, source_session_id, embedding, created_at,
  updated_at
- `sessions_fts` / `facts_fts` -- FTS5 external-content tables with explicit
  `_ai`, `_ad`, `_au` triggers (required -- without triggers FTS5 returns
  stale data)
- `schema_version` -- single row for migration tracking

**FTS5 trigger rule:** Every `INSERT`, `DELETE`, and `UPDATE` on `sessions`
and `facts` must have a corresponding trigger to keep the FTS5 index in sync.
Test all three trigger types for both tables.

### OllamaEmbedder lifecycle

`OllamaEmbedder.ensure_running()` checks `http://localhost:11434/`, launches
`ollama serve` via `subprocess.Popen` if not reachable, waits up to
`startup_timeout` seconds. `FileNotFoundError` (ollama not in PATH) is caught
and returns `False`. Started in a daemon thread from `TachiApp._wire_memory()`
-- never blocks the UI thread. `stop_on_exit` config controls whether the
process is terminated at exit.

Embedding model: `nomic-embed-text` (default). Embeddings stored as
`struct.pack("f" * len(v), *v)` BLOB. FTS5 keyword search is the fallback
when Ollama is unavailable.

### MemoryStore API

```python
store.start_session(nick: str) -> str                         # returns session_id
store.update_session_summary(id, summary, embedding, turns)   # periodic flush
store.end_session(id, summary, technical_notes, embedding, facts)  # on exit
store.add_fact(category, text, source_session_id)             # /remember command
store.search(query, limit=5) -> list[SearchResult]            # semantic + FTS5
store.list_sessions(limit=20) -> list[SessionRecord]
store.get_session_detail(id) -> SessionDetail | None          # lazy technical_notes
store.delete(id, type: Literal["session", "fact"]) -> bool
```

`technical_notes` is lazy -- NULL until `end_session()`. Only fetched via
`/memory show <id>` (use `get_session_detail()`).

### search_memory tool

Registered via `register(ToolDef(...))` at import time in `tools/memory.py`.
`_load_tools()` in `tools/__init__.py` imports it to trigger registration.
Module-level `_store: MemoryStore | None = None` singleton wired at startup
via `set_memory_store()` called from `TachiApp._wire_memory()`.

The agent invokes this tool automatically when the user asks about past work,
says "do you remember", or references previous sessions.

### finalize_session()

Called from `TachiApp._clean_exit()` before worker shutdown:

```python
self.controller.finalize_session(embedder=self._embedder, timeout=15.0)
```

Runs in a daemon thread with a 15s join timeout. Calls `summarize_messages()`,
`extract_technical_notes()`, `extract_facts()`, then `store.end_session()`.
Best-effort -- failures are logged as warnings, never raised.

### Slash commands

| Command | Description |
|---------|-------------|
| `/memory search <query>` | Semantic + FTS5 search over sessions and facts |
| `/memory list` | Recent stored sessions (most recent first) |
| `/memory show <id>` | Full session narrative + technical notes |
| `/memory forget session:<id>` | Delete a stored session |
| `/memory forget fact:<id>` | Delete a stored fact |
| `/remember <text>` | Pin an explicit fact to long-term memory |

Both `/memory` and `/remember` are in `_KNOWN_SLASH` in `controller.py`.
Handlers are `_cmd_memory()` and `_cmd_remember()` on `SessionController`.
Slash dispatch reads from the full `command` string (not just the first token)
for the subcommand remainder.

### Config

```toml
[agent.memory]
enabled = true
embedding_model = "nomic-embed-text"
stop_ollama_on_exit = false
flush_every_n_turns = 10
max_search_results = 5
```

---

## Configuration

Config is loaded from `~/.config/<appname>/config.toml` (or `~/<appname>.toml` as
fallback). The agent section drives TUI behavior:

```toml
[agent]
vim_mode = false
vim_escape = "jj"
vim_escape_timeout_ms = 500
input_max_lines = 8
nick = ""
```

`load_tui_config(cfg_dict)` returns a `TuiConfig` dataclass. Validated integers
clamp to documented min/max ranges with defaults as fallback.

---

## Integrations

This assistant integrates with research-focused APIs and tools:

- **Claude API** -- primary reasoning model
- **GitHub Copilot / Codex** -- code generation, data pipelines
- **gstack** -- headless browser for web research, content retrieval
- **Superpowers skills** -- brainstorming, writing-plans, executing-plans,
  systematic-debugging, dispatching-parallel-agents, requesting-code-review

Integration clients follow the same `cli.py` / `client.py` split.
No live network calls in tests -- use `requests-mock` or `unittest.mock.patch`.

---

## Research Project Management

The assistant manages research projects with this structure:

```
~/research/projects/<project-name>/
    README.md           -- question, scope, methodology
    sources/            -- bibliography and raw source material
    notes/              -- working notes and annotations
    analysis/           -- code, notebooks, data
    output/             -- reports, papers, visualizations
    TODO.md             -- project-scoped task list
    FINDINGS.md         -- evolving summary of conclusions
```

Cross-project todos: `~/research/TODO.md`

Todo format:
```
- [ ] [NOW] Description -- context or next action
- [ ] [SOON] ...
- [ ] [SOMEDAY] ...
- [ ] [BLOCKED: reason] ...
```

---

## Coding Rules

- **No em-dashes (U+2014) anywhere** -- use `-` or `--`. Absolute rule.
- **All source files must be ASCII-safe** -- no curly quotes, smart apostrophes,
  non-breaking spaces, ellipses, or any Unicode above U+007F
- `snake_case` for Python; follow language conventions in all other files
- No leading underscores on regular variables -- reserve for module-private helpers
- Never hardcode secrets, credentials, or environment-specific values
- Write idempotent code where the stack supports it
- Fail loudly with a clear error -- never silently continue in a bad state
- Only comment code that genuinely needs clarification
- **Do not modify unrelated code** when fixing a specific issue

---

## Testing

Run the test suite:

```bash
.venv/bin/pytest tests/ -v
```

Run linting:

```bash
.venv/bin/ruff check <package>/ tests/
.venv/bin/ruff format --check <package>/ tests/
.venv/bin/bandit -r <package>/ -ll
```

### Test conventions

- Test files: `tests/test_<module>.py` matching the module they cover
- Class-based: `class Test<Feature>` with descriptive method names
- `requests-mock` for HTTP calls; `unittest.mock.patch` for everything else
- `tmp_path` fixture for any test that reads or writes files
- `asyncio_mode = "auto"` in `pyproject.toml` -- async Pilot tests need no decorator
- No live network calls in tests

### What to test

- Happy path with valid inputs
- Error cases: 404s, network failures, missing config, invalid input
- Edge cases: empty results, None inputs, case-insensitive matching
- CLI wiring: for every command that constructs an API client, assert correct
  constructor arguments via a CLI-level wiring test (not just unit tests on sync functions)

### pytest-asyncio config

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## Dependencies

Use `uv` for all package operations:

```bash
~/.local/bin/uv pip install -e ".[dev]"
~/.local/bin/uv pip install --python .venv/bin/python -e ".[agent,dev]"
```

Never use raw `pip install`. New dependencies go in `pyproject.toml` first.

Core deps: `textual>=0.50.0`, `click`, `requests`, `tomllib`/`tomli`
Agent deps: `textual>=0.50.0`, `pytest-asyncio>=0.21` (dev)

---

## Commit and Branch Rules

### Commit format

Conventional Commits: `<type>: <description>`. Types: `feat`, `fix`, `docs`,
`refactor`, `test`, `chore`. Subject line under 72 characters. Body explains
what changed and why.

Always include:
```
Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

### Branch naming

```
^(feature/|hotfix/)?[a-z0-9-]+
```

Examples: `feature/vim-mode`, `feature/claude-integration`, `chore/config-refactor`

This project has no ticket system -- always use descriptive slugs. No placeholder
project codes.

### Parallel branch workflow

Main clone at `~/git/<repo>/` stays on default branch. Feature work is checked out
as a worktree:

```
~/git/parallels/<repo>/<branch-name>/
```

Never switch the main clone to a feature branch. Remove worktrees after merging:

```bash
git worktree remove ~/git/parallels/<repo>/<branch-name>
```

---

## Code Change Workflow

Before any non-trivial change:

1. **Propose the approach** -- explain what will change and why
2. **Make the change**
3. **Review hunk by hunk** -- one hunk per message, with context
4. **Request explicit approval** before committing
5. **`git status`** before commit to confirm staged changes
6. **Commit and push** only after approval

Never run `git commit` or `git push` without completing steps 3-4 in the current turn.

---

## Changelog

Maintain `CHANGELOG.md` following Keep a Changelog format. Add entries under
`## [Unreleased]` for every user-visible change. Entries are user-facing -- describe
from the perspective of someone using the tool, not from the diff.

---

## Safety

- Never guess -- only provide answers that can be verified
- Surface assumptions explicitly when they affect the outcome
- For anything version-sensitive, verify against current documentation
- Do not generate content that could be harmful or that fabricates sources
- Research data containing PII or health data: flag it, request guidance, do not proceed
- On politically sensitive topics: present multiple credible perspectives, do not advocate

---

## Output Directories

```
~/research/projects/<project-name>/   -- active research projects
~/research/scratch/                   -- quick notes, one-off lookups
~/research/simulations/               -- standalone simulations
~/research/bibliography/              -- shared bibliography
~/Documents/copilot-output/           -- non-research Copilot output
```
