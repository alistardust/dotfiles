# Global Copilot Instructions

<!-- BACK-SYNC NOTE: This is the generic dotfiles bootstrap. The live file at
     ~/.copilot/copilot-instructions.md intentionally diverges in these ways:
     - Adds "## Identity and Preferences" (Sam identity, Ali preferences)
     - Adds "## Model Preference" (pins claude-sonnet-4.5 default; delegation table; never-GPT rule)
     - Adds "## Context" (Iodine/SRE work context)
     - Adds work-specific sections (Tachikoma, AWX, PagerDuty, Jira, etc.)
     - Adds Superpowers skills section
     Do NOT back-sync those sections into this file. -->

## Quality Rules

- Prioritize accuracy over speed.
- Never guess. Only provide answers that can be verified.
- Base answers on the latest stable version of the technology being discussed.
- Perform an adversarial review on all code: actively seek edge cases, failure modes, and security issues.
- Always trace through code against multiple input scenarios before declaring it correct.


## Naming Conventions

Variable, function, and class names describe **what the thing IS**, never what content it relates to,
what project it belongs to, or what it came from.

| Accept | Reject | Rule |
|--------|--------|------|
| `const siteData` | `const ARP` | No project acronyms as variable names |
| `user_count` | `n` | No single-letter names (except `i`/`j` loop counters) |
| `is_active` | `flag` | Booleans use question form: `is_`, `has_`, `can_` |
| `get_user()` | `doThing()` | Functions are verb phrases |
| `MAX_RETRIES` | `3` | No magic numbers; name the constant |
| `PaymentProcessor` | `Processor` | Classes are specific noun phrases |

- Never shadow built-ins (`list`, `id`, `type`, `input`, `filter`, `map`)
- Only well-known abbreviations: `id`, `url`, `db`, `http`. Never invent new ones.
- Negative booleans (`is_not_valid`): invert and use `is_invalid` instead.


## Error Handling

- **Fail fast and loudly.** A crash immediately is better than silent data corruption hours later.
- **Never swallow exceptions silently.** A bare `except: pass` or empty `catch {}` is almost always
  a bug. If you must suppress, log it and document why.
- **Always chain exceptions** (Python): `raise AppError("context") from original_error`; bare
  re-raise loses the original traceback.
- **Handle errors at the layer that can meaningfully respond.** Do not catch what you cannot handle.
- Distinguish: programmer errors (bugs, let crash, fix the code); operational errors (retry and alert);
  user input errors (validate early, return clear message).


## Logging

- Use **structured logging** (JSON or key-value). Never build log strings with f-strings/interpolation
  in production code; structured logs are machine-parseable.
- **Never log** passwords, tokens, API keys, secrets, or PII (names, emails, SSNs, card numbers) at
  any log level.
- Log level semantics: `DEBUG` (dev only), `INFO` (normal ops), `WARNING` (unexpected but handled),
  `ERROR` (operation failed), `CRITICAL` (service impaired).
- Include a correlation/request ID on every log line in a request context.
- Python: use `structlog`. Node: use `pino`.


## Security

These are CI failures and immediate review rejects. No exceptions.

- No `eval()`, `exec()`, or equivalent with any external or user-supplied input
- No `subprocess(..., shell=True)` with any variable content; always pass argument lists
- No SQL built by string formatting/concatenation; always use parameterized queries
- No `pickle.loads()` / `pickle.load()` on any external data; it is arbitrary code execution
- No `yaml.load()`; always use `yaml.safe_load()`
- No hardcoded API keys, passwords, tokens, or credentials anywhere in source code
- No `.env` files with real secrets committed to any repo (`.env` in `.gitignore`;
  `.env.example` with placeholder values is fine)
- No PII, passwords, or tokens in log output at any level
- No `random` module for any security purpose; use `secrets` (Python) or `crypto.randomBytes` (Node)
- No MD5 or SHA-1 for any security purpose; use SHA-256+
- No home-rolled cryptography; use `cryptography`, `passlib`, or `bcrypt`
- No `innerHTML` with any unsanitized content in JavaScript (XSS)

Input validation: validate at every external boundary (API, CLI, queue). Whitelist what is allowed;
reject everything else. Never trust client-supplied role or permission data.


## Function and Code Design

- **Single Responsibility:** one function does one thing, completely.
- Size target: 40 lines per function or fewer. If you can't see the whole function at once, it's
  doing too much.
- Max 3-4 arguments. Group related args into a data class or config object beyond that.
- Prefer **pure functions** (same input, same output, no external mutation) where possible.
- **Command/Query Separation:** a function either returns a value OR changes state. Functions that
  do both must be documented explicitly.
- Do not comment *what* the code does; write code so clear it doesn't need that. Comment *why* for
  non-obvious decisions.
- TODO comments must include an owner and a ticket: `# TODO(alice): remove after migration [PROJ-1234]`


## Architecture Principles

- Business logic never lives in API handlers or DB queries; it lives in a service/domain layer.
- DB queries never live in business logic; use a repository pattern.
- Import direction flows **inward only**: presentation, service, domain, infrastructure. Inner layers
  must not import outer layers.
- **Fail-secure defaults:** new features, endpoints, and flags default to off/denied, not on/public.
  Access must be explicitly granted.
- **YAGNI:** don't build abstractions for requirements you don't have yet. Add generality when the
  second real case arrives.
- **KISS:** the simple solution that works today beats the elegant abstraction. Flat over nested;
  function over class-with-one-method; stdlib over framework where both work.
- **DRY:** every piece of *knowledge* has one authoritative representation. Do not mistake accidental
  visual similarity for duplication of knowledge.
- **Dependency Inversion:** classes depend on abstractions (Protocols/ABCs/interfaces), not concrete
  implementations. Inject dependencies; do not construct them internally.


## Testing

- Test **behaviour**, not implementation. Tests that break on renaming a private method are wrong.
- Test names must be sentences: `test_create_user_with_duplicate_email_raises_conflict_error`
- **Arrange, Act, Assert** structure. One logical assertion per test.
- Tests must be **deterministic and isolated**. Flakey tests and order-dependent tests are bugs.
- Cover: all branching logic, all error paths, all boundary values, the happy path.
- 80% line coverage is a floor, not a goal.


## Git Hygiene

- Commit messages follow **Conventional Commits**: `<type>[scope]: <description>`
  - Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, `revert`
  - Description: imperative mood, present tense, 72 characters or fewer
  - Body explains *why*, not *what* (the diff shows what)
- **Atomic commits:** one logical change per commit. Every commit must pass tests independently.
- Never mix refactoring and feature changes in the same commit.
- Never force-push to `main` or any shared branch.
- PRs target 400 lines changed or fewer. Larger PRs must be split.
- Branch naming: `feature/ID-description`, `fix/ID-description`, `chore/description`


## Python Standards

- **Formatter/Linter:** Ruff (lint + format, line-length=88). Replaces Black, Flake8, isort.
  Enable rulesets: `E/W/F/I/N/B/C4/UP/S/ANN/D`. Run in pre-commit and CI.
- **Type checking:** mypy --strict. All public functions, methods, and class attributes must have
  type annotations.
- **Python 3.10+ syntax:** `X | None` not `Optional[X]`; `list[str]` not `List[str]`;
  `X | Y` not `Union[X, Y]`.
- **Testing:** pytest. Fixtures in `conftest.py`. Parametrize for input variation.
- **Dependency management:** uv. Pin versions in lockfiles. Commit both `pyproject.toml` and the
  lockfile. Separate dev from runtime deps.
- **CVE scanning:** `pip-audit` in CI. Block on HIGH/CRITICAL.
- **Secrets scanning:** `detect-secrets` pre-commit hook.
- **Docstrings:** Google style on all public functions, classes, modules.
- **Exceptions:** always subclass `Exception` not `BaseException`; always chain with `from`; one
  custom exception per meaningful error category.
- **Idioms:** `pathlib.Path` not `os.path`; `secrets` not `random` for security; f-strings not `%`
  or `.format()`; `isinstance()` not `type() ==`; `x is None` not `x == None`.


## JavaScript / Web Standards

- `const` by default; `let` only when you know you'll reassign; `var` is forbidden.
- ESLint + Prettier for linting and formatting. No manual formatting debates.
- ESM (`import`/`export`) in new code. No mixing module systems within a project.
- All interactive elements need `aria-label` or visible label text.
- All `<img>` need meaningful `alt` text (decorative images: `alt=""`).
- All custom property values (colors, spacing, z-index) in CSS custom properties; no magic numbers.
- No `innerHTML` with unsanitized content.
- No inline event handlers (`onclick=`); use `addEventListener`.


## Confirmation Requirement

When a task requires explicit approval, ask directly and wait for an unambiguous affirmative before
acting. Valid approvals include: "yes", "go ahead", "proceed", "confirm", "approved", or a clear
equivalent spoken in the current session in direct response to the question.

The following do NOT count as approval:
- Implied intent or contextual inference
- Language that could reasonably be interpreted in more than one way
- Approval given earlier in the conversation for a different step

Review and approval requests must be presented one at a time. Each request must cover one complete
logical change set. Do not split a coherent edit into smaller fragments solely to reduce size. Do
not combine unrelated edits into one request.


## Code Change Workflow

Before writing any non-trivial code change:
1. **Propose the approach**: explain what will change and why. If multiple valid approaches exist
   with meaningfully different tradeoffs, present them and get a decision before writing any code.
2. **Make the change** after approach is confirmed.
3. **Review hunk by hunk**: determine diff state and run the appropriate command:
   - **Mixed** (both `git diff --cached` and `git diff` show output): review staged changes first.
     After those are approved, ask whether to also stage and review the unstaged changes or leave
     them for a separate commit.
   - **Staged only** (`git diff --cached` shows output, `git diff` does not): review staged
     changes. This is the source of truth for what will be committed.
   - **Unstaged only** (`git diff` shows output, `git diff --cached` does not): review unstaged
     changes, then stage them before commit.
   For each hunk (one `@@` block), sequentially:
   - Show the **raw unified diff** in a fenced code block. Include the diff file header
     (`--- a/path`, `+++ b/path`) and the `@@` context line.
   - Dispatch an automated code review of the hunk and post-change file content using the
     hunk-reviewer skill prompt. If the review fails or times out, proceed without it: show
     the diff and explanation, note "Review unavailable" in place of the summary.
   - Below the diff, present: (a) the automated review summary (or "Review unavailable" on
     failure); (b) what the code does technically; (c) why this change was made.
   - Present approval choices for the hunk:
     - Non-final hunk: Approve (next hunk), Skip this file, Request changes, Abort
     - Final hunk: Approve (commit and push), Request changes, Abort
     - If "Skip this file" is selected on the last remaining file, present the review summary
       for skipped hunks, then ask: Commit as-is, Request changes, or Abort
   - **"Request changes" handling:** the user describes what needs to change. Make the edit,
     re-run `git diff` for the affected file, and re-present only the changed hunk(s) starting
     from the rejected hunk. Previously approved hunks in other files are not re-reviewed.
   - Do not proceed to the next hunk until the current one is approved.
   - If "Skip this file" is selected, skip remaining hunks for that file. Run the automated
     review on skipped hunks and present a one-line summary of findings (if any) before moving
     to the next file.
   - **Non-hunk diffs** (binary files, mode-only changes, pure renames without content changes,
     submodule updates): present at file level. Show the diff header and a one-line description,
     then offer the same approval choices. No automated review for non-hunk diffs. Renamed files
     that also have content changes follow the normal hunk-by-hunk flow.
   - **Trivial hunk grouping:** If multiple consecutive hunks in the same file are purely
     whitespace, import reordering, or single-line version bumps, present them as a group with
     a single approval.
   - **Skip-review patterns** (auto-skip, still committed): files matching declared patterns
     skip hunk review but are staged and committed normally. Default: none.
   - **Never-commit patterns** (auto-skip, never staged): see "Commit safety" below.
   - **Verbal override:** the user can say "skip the hunk review for this change" or "skip
     review for this repo" at any point. A verbal override lasts for the current commit
     operation only. It does not carry to subsequent commits unless the user says "skip review
     for the rest of this session." To make a skip permanent, request it be added to the
     skip-review patterns list.
4. **Before `git commit`:** run `git status` to confirm the staged changes are exactly what was
   reviewed: nothing extra, nothing missing.
5. **Commit and push** only after approval is given.
6. **Before `git push`:** run `git status` to confirm no uncommitted changes related to this
   commit remain. Unrelated local WIP in the working tree does not block the push.

Never run `git commit` or `git push` without completing step 3 in the current turn. Approval of a
plan or approach does not authorize the commit.

### Commit safety

**Never-commit patterns:** Do not `git add` or include in any commit:
- `~/.copilot/session-state/**` or equivalent session directories
- `.copilot/` directories within work repos
- `docs/ai-*/`, `**/specs/**`, `**/plans/**` generated by AI planning tools

Detection rule: before staging, check if any file path matches these patterns.
If so, do not stage it.

**Force-add prohibition:** Never use `git add -f` or `git add --force` on files
matched by `.gitignore`. If a file is gitignored, it stays gitignored. No exceptions.

**Pre-commit verification (step 4):** When running `git status` before commit,
explicitly verify no never-commit files are staged. If any are found, unstage them
(`git reset HEAD <path>`) and report before proceeding. This auto-unstage is a safety
guardrail that prevents accidental commits and never removes data from the worktree.


## tmux Auto-Rename

On every session start, if inside tmux (`$TMUX` is set), automatically rename
the current window and pane to reflect what this session is about. Do this
silently at the beginning of the session without announcing it.

**How to rename:**
```bash
# Check for manual override first
WINDOW_ID=$(tmux display-message -p '#{window_id}' 2>/dev/null)
MANUAL=$(tmux show-environment -g "@manual_name_${WINDOW_ID}" 2>/dev/null)
if [ "${MANUAL##*=}" = "1" ]; then exit 0; fi

# Derive name from CWD + git context
TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -n "$TOPLEVEL" ]; then
  REPO=$(basename "$TOPLEVEL")
  BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null)
  TICKET=$(echo "$BRANCH" | grep -oE '[A-Z]{2,10}-[0-9]+' | head -1)
  if [ -n "$TICKET" ]; then
    NAME="${REPO}:${TICKET}"
  else
    NAME="$REPO"
  fi
else
  NAME=$(basename "$PWD")
fi
tmux rename-window "$NAME" 2>/dev/null
printf '\033]2;%s\033\\' "copilot" 2>/dev/null
```

**Rules:**
- Run this once at session start, silently (no output to user)
- If the work has an obvious theme (ticket, project), use that as the name
- Set the pane title to "copilot" so it is distinguishable from other panes
- Do not rename if a manual override is set: check
  `tmux show-environment -g "@manual_name_$(tmux display-message -p '#{window_id}')" 2>/dev/null`
  and skip if it returns a value ending in `=1`

