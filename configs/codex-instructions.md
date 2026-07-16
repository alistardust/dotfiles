# Global Agent Instructions

## User Preference

- The user's name is Alice (Ali). Use she/her pronouns when referring to her.

## Model Preference

- Prefer Anthropic (Claude) models over OpenAI models when a choice is available.
- Default to Claude Sonnet for standard tasks; use Claude Opus for complex, multi-step reasoning.

## Quality Rules

- Prioritize accuracy over speed.
- Never guess. Only provide answers that can be verified.
- Base answers on the latest stable version of the technology being discussed.
- Perform an adversarial review on all code: actively seek edge cases, failure modes, and security issues.
- Always trace through code against multiple input scenarios before declaring it correct.

---

## Naming Conventions (Universal)

Variable, function, and class names describe **what the thing IS** — never what content it relates to, what project it belongs to, or what it came from.

| ✓ | ✗ | Rule |
|---|---|---|
| `const siteData` | `const ARP` | No project acronyms as variable names |
| `user_count` | `n` | No single-letter names (except `i`/`j` loop counters) |
| `is_active` | `flag` | Booleans use question form: `is_`, `has_`, `can_` |
| `get_user()` | `doThing()` | Functions are verb phrases |
| `MAX_RETRIES` | `3` | No magic numbers — name the constant |
| `PaymentProcessor` | `Processor` | Classes are specific noun phrases |

- Never shadow built-ins (`list`, `id`, `type`, `input`, `filter`, `map`)
- Only well-known abbreviations: `id`, `url`, `db`, `http`. Never invent new ones.
- Negative booleans (`is_not_valid`) — invert: use `is_invalid` instead.

---

## Error Handling (Universal)

- **Fail fast and loudly.** A crash immediately is better than silent data corruption hours later.
- **Never swallow exceptions silently.** A bare `except: pass` or empty `catch {}` is almost always a bug. If you must suppress, log it and document why.
- **Always chain exceptions** (Python): `raise AppError("context") from original_error` — bare re-raise loses the original traceback.
- **Handle errors at the layer that can meaningfully respond.** Do not catch what you cannot handle.
- Distinguish: programmer errors (bugs — let crash, fix the code); operational errors (retry+alert); user input errors (validate early, return clear message).

---

## Logging (Universal)

- Use **structured logging** (JSON or key-value). Never build log strings with f-strings/interpolation in production code — structured logs are machine-parseable.
- **Never log** passwords, tokens, API keys, secrets, or PII (names, emails, SSNs, card numbers) at any log level.
- Log level semantics: `DEBUG` (dev only), `INFO` (normal ops), `WARNING` (unexpected but handled), `ERROR` (operation failed), `CRITICAL` (service impaired).
- Include a correlation/request ID on every log line in a request context.
- Python: use `structlog`. Node: use `pino`.

---

## Security — Absolute Blockers

These are CI failures and immediate review rejects. No exceptions.

- ❌ `eval()`, `exec()`, or equivalent with any external or user-supplied input
- ❌ `subprocess(..., shell=True)` with any variable content — always pass argument lists
- ❌ SQL built by string formatting/concatenation — always use parameterized queries
- ❌ `pickle.loads()` / `pickle.load()` on any external data — it is arbitrary code execution
- ❌ `yaml.load()` — always use `yaml.safe_load()`
- ❌ Hardcoded API keys, passwords, tokens, or credentials anywhere in source code
- ❌ `.env` files with real secrets committed to any repo (`.env` in `.gitignore`; `.env.example` with placeholder values is fine)
- ❌ PII, passwords, or tokens in log output at any level
- ❌ `random` module for any security purpose — use `secrets` (Python) or `crypto.randomBytes` (Node)
- ❌ MD5 or SHA-1 for any security purpose — use SHA-256+
- ❌ Home-rolled cryptography — use `cryptography`, `passlib`, or `bcrypt`
- ❌ `innerHTML` with any unsanitized content in JavaScript (XSS)

Input validation: validate at every external boundary (API, CLI, queue). Whitelist what is allowed; reject everything else. Never trust client-supplied role or permission data.

---

## Function and Code Design (Universal)

- **Single Responsibility:** one function does one thing, completely.
- Size target: ≤40 lines per function. If you can't see the whole function at once, it's doing too much.
- Max 3–4 arguments. Group related args into a data class or config object beyond that.
- Prefer **pure functions** (same input → same output, no external mutation) where possible.
- **Command–Query Separation:** a function either returns a value OR changes state. Functions that do both must be documented explicitly.
- Do not comment *what* the code does — write code so clear it doesn't need that. Comment *why* for non-obvious decisions.
- TODO comments must include an owner and a ticket: `# TODO(alice): remove after migration — PROJ-1234`

---

## Architecture Principles (Universal)

- Business logic never lives in API handlers or DB queries — it lives in a service/domain layer.
- DB queries never live in business logic — use a repository pattern.
- Import direction flows **inward only**: presentation → service → domain → infrastructure. Inner layers must not import outer layers.
- **Fail-secure defaults:** new features, endpoints, and flags default to off/denied, not on/public. Access must be explicitly granted.
- **No speculative scope-cutting.** Do not drop features, data, or capability because they "might not be needed" (do not invoke YAGNI). Deliver the complete, correct solution; cut scope only for concrete cost or correctness reasons. Prefer the simplest implementation that delivers the full scope (see KISS).
- **KISS:** the simple solution that works today beats the elegant abstraction. Flat > nested; function > class-with-one-method; stdlib > framework where both work.
- **DRY:** every piece of *knowledge* has one authoritative representation. Do not mistake accidental visual similarity for duplication of knowledge.
- **Dependency Inversion:** classes depend on abstractions (Protocols/ABCs/interfaces), not concrete implementations. Inject dependencies; do not construct them internally.

---

## Testing (Universal)

- Test **behaviour**, not implementation. Tests that break on renaming a private method are wrong.
- Test names must be sentences: `test_create_user_with_duplicate_email_raises_conflict_error`
- **Arrange–Act–Assert** structure. One logical assertion per test.
- Tests must be **deterministic and isolated**. Flakey tests and order-dependent tests are bugs.
- Cover: all branching logic, all error paths, all boundary values, the happy path.
- 80% line coverage is a floor, not a goal.

---

## Git Hygiene (Universal)

- Commit messages follow **Conventional Commits**: `<type>[scope]: <description>`
  - Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`, `revert`
  - Description: imperative mood, present tense, ≤72 characters
  - Body explains *why*, not *what* (the diff shows what)
- **Atomic commits:** one logical change per commit. Every commit must pass tests independently.
- Never mix refactoring and feature changes in the same commit.
- Never force-push to `main` or any shared branch.
- PRs target ≤400 lines changed. Larger PRs must be split.
- Branch naming: `feature/ID-description`, `fix/ID-description`, `chore/description`

---

## Python Standards

- **Formatter:** Black (line-length=88). Run in pre-commit and CI. Non-negotiable.
- **Linter:** Ruff with `E/W/F/I/N/B/C4/UP/S/ANN/D` rulesets. Replaces Flake8 + isort.
- **Type checking:** mypy --strict. All public functions, methods, and class attributes must have type annotations.
- **Python 3.10+ syntax:** `X | None` not `Optional[X]`; `list[str]` not `List[str]`; `X | Y` not `Union[X, Y]`.
- **Testing:** pytest. Fixtures in `conftest.py`. Parametrize for input variation.
- **Dependency management:** uv. Pin versions in lockfiles. Commit both `pyproject.toml` and the lockfile. Separate dev from runtime deps.
- **CVE scanning:** `pip-audit` in CI. Block on HIGH/CRITICAL.
- **Secrets scanning:** `detect-secrets` pre-commit hook.
- **Docstrings:** Google style on all public functions, classes, modules.
- **Exceptions:** always subclass `Exception` not `BaseException`; always chain with `from`; one custom exception per meaningful error category.
- **Idioms:** `pathlib.Path` not `os.path`; `secrets` not `random` for security; f-strings not `%` or `.format()`; `isinstance()` not `type() ==`; `x is None` not `x == None`.

---

## JavaScript / Web Standards

- `const` by default; `let` only when you know you'll reassign; `var` is forbidden.
- ESLint + Prettier for linting and formatting. No manual formatting debates.
- ESM (`import`/`export`) in new code. No mixing module systems within a project.
- All interactive elements need `aria-label` or visible label text.
- All `<img>` need meaningful `alt` text (decorative images: `alt=""`).
- All custom property values (colors, spacing, z-index) in CSS custom properties — no magic numbers.
- No `innerHTML` with unsanitized content.
- No inline event handlers (`onclick=`); use `addEventListener`.

---

## Explicit Approval

When a task requires user approval, the agent must ask directly and wait for an unambiguous affirmative confirmation before acting.

Valid approval includes clear affirmative confirmations such as:
- `Yes`
- `Approve`
- `Approved`
- `Affirmative`
- `Confirmed`

The following do not count as approval:
- `Go ahead`
- `Go ahead and do this`
- `Proceed`
- `Sounds good`
- implied intent
- contextual inference
- language that could reasonably be interpreted in more than one way

If approval is required and has not been given, the agent may prepare work, explain the next step, or show a proposed patch, but must not apply the change.

Review and approval requests must be presented one at a time.

When proposing edits for approval:
- Show only one approval request before waiting for a reply.
- Each approval request must contain one complete logical change set.
- Do not split a coherent edit into smaller fragments solely to reduce size.
- Do not combine unrelated edits into one approval request.
- If a file contains multiple unrelated edits, present them as separate approval requests.
- Prefer smaller diffs when possible, but preserve logical completeness.

---

## AI Instruction File Best Practices

- Put hard constraints (security, never-do-this) **first** — they must be seen before context limits cut in.
- Use bullets and discrete rules, not prose paragraphs — LLMs comply more reliably with explicit lists.
- Provide positive AND negative code examples for non-obvious rules.
- State the *why* for non-obvious constraints.
- Keep repo-level instruction files under ~2,000 words -- longer files get deprioritized.
- Global rules (these) belong in user-level config (~/.codex/AGENTS.md). Project-specific rules belong in the project's AGENTS.md.
- Never put secrets, PII, or project-sensitive content in instruction files.


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
printf '\033]2;%s\033\\' "codex" 2>/dev/null
```

**Rules:**
- Run this once at session start, silently (no output to user)
- If the work has an obvious theme (ticket, project), use that as the name
- Set the pane title to "codex" so it is distinguishable from other panes
- Do not rename if a manual override is set: check
  `tmux show-environment -g "@manual_name_$(tmux display-message -p '#{window_id}')" 2>/dev/null`
  and skip if it returns a value ending in `=1`
