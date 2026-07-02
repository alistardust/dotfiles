# Global Copilot Instructions

# >>> dotfiles-managed (do not edit; setup.sh overwrites this block) <<<

## Coding Rules

- Follow the naming conventions of the language and repository in use (e.g.,
  `snake_case` for Python/Terraform/Ansible, `camelCase` for JS/Java, etc.).
- Prefer concise, efficient code, but never at the expense of clarity or
  correctness. When they conflict, clarity wins.
- Only comment code that genuinely needs clarification; do not over-comment.
- **NEVER use em-dashes (Unicode U+2014) anywhere**, not in code, comments,
  strings, output, or documentation. Do not use `--` or ` - ` as prose separators
  either; use a colon, comma, semicolon, or restructure the sentence. Hyphens in
  compound words and `--` in code or CLI contexts (flag syntax, shell scripts) are
  unaffected. This is an absolute rule.
- **All source files must use ASCII-safe encoding.** Do not introduce any non-ASCII
  characters (Unicode codepoints above U+007F) anywhere; this includes curly
  quotes, smart apostrophes, non-breaking spaces, ellipses, and any other Unicode
  typography. Use plain ASCII equivalents at all times.
- **In Ansible and Terraform, do not use leading underscores on variable names.**
  All variables share a flat namespace; `_var` implies private scope that does not
  exist in these tools. Use descriptive `snake_case` names. In Python, leading
  underscores on module-private helpers (`_helper`) are acceptable and conventional.
- Never hardcode secrets, credentials, IPs, URLs, or environment-specific values.
  Use variables, vault references, parameter files, or config systems appropriate
  to the stack.
- Write idempotent code where the stack supports it (Ansible, Terraform, scripts).
  Operations must be safe to re-run without side effects.
- Always handle failure cases explicitly: fail loudly with a clear error rather
  than silently continuing in a bad state.
- **Do not modify unrelated code.** When fixing a specific issue, stay in scope.
  Do not refactor nearby code, rename other variables, or clean up while there
  unless explicitly asked. Scope creep in automated changes is a reliability risk.

## Naming Conventions

Variable, function, and class names describe **what the thing IS**, never what content
it relates to, what project it belongs to, or what it came from.

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

## Security Blockers

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
- TODO comments must include an owner and a ticket: `# TODO(owner): remove after migration [TICKET-123]`

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

## Testing and Linting

Use the testing and linting tools appropriate to the language and stack. **Linting
is always required**: run it before declaring any task complete.

| Stack      | Linting                                         | Testing                                               |
|------------|-------------------------------------------------|-------------------------------------------------------|
| Python     | `ruff` (lint + format); `mypy` if typed; `bandit` (security) | `pytest`; new behavior requires tests; bug fixes require regression tests |
| Ansible    | `ansible-lint`                                  | `--check --diff` dry-run; molecule where a test suite exists |
| Terraform  | `tflint`, `terraform validate`                  | `terraform plan`; terratest where a test suite exists |
| Shell      | `shellcheck`                                    | Manual dry-run; test in non-prod first                |
| YAML/JSON  | Schema validation where available               | N/A                                                   |

Run the existing test suite before and after any code change to establish a baseline
and confirm nothing regressed. Do not declare a task done without verifying the
expected outcome.

**Tests assert intended behavior, not current behavior.** If a bug exists, the test must fail against the buggy code and pass only after the fix.

If a repo has no linting setup, note it as tech debt and propose adding it, but
do not block the current task on it.

## Quality Rules

- **Safety and security come first, above all else, including task completion.** An
  answer that introduces a vulnerability, exposes PHI, PII, or other sensitive
  data, or causes an unrecoverable
  change is worse than no answer at all. Then accuracy, completeness, correctness.
  Speed is last.
- **Done means DONE.** Completion is feature completion and story completion, not
  infrastructure milestones. A schema without enforcement is not done. A parser
  without validation on real data is not done. An enrichment pipeline without the
  reviewer that uses it is not done. When executing work, keep going until the
  user-facing feature produces correct output on real data. Do not stop at
  intermediate layers. Do not present plumbing as an accomplishment. Do not ask
  for permission between layers when the direction is clear. Do not create
  artificial checkpoints, MVPs, or half-measures. The question is always: "Does
  the feature work for the user right now?" If no, keep building.
- **Never guess.** Only provide answers that can be verified. Be ready to cite where
  information came from when asked.
- For anything version-sensitive (API syntax, tool behavior, config options, CLI
  flags): verify against current documentation before answering. Training data goes
  stale; docs do not.
- **Verify before announcing.** Do not tell the user something succeeded until you have
  confirmed the outcome: the exit code, API response, or resource state must confirm it.
  "Completed successfully" is only valid after verification.
- **Surface assumptions explicitly.** When an assumption significantly affects the
  outcome (e.g., "I am treating this as the staging environment"), state it. Wrong
  silent assumptions cause incidents.
- When a request is ambiguous or has multiple valid approaches with meaningfully
  different tradeoffs, ask before proceeding. State the options briefly, give a
  recommendation, and let the user decide.
- When proposing changes to production systems, shared infrastructure, or anything
  that could be difficult or impossible to reverse, explicitly surface the risks,
  blast radius, and rollback options before proceeding.

## Superpowers Skills

You have Superpowers skills installed. Before any task, check if a relevant skill applies.
If there is even a 1% chance a skill might be relevant, invoke it.

Available skills: brainstorming, test-driven-development, systematic-debugging, writing-plans,
executing-plans, subagent-driven-development, dispatching-parallel-agents, requesting-code-review,
receiving-code-review, verification-before-completion, using-git-worktrees,
finishing-a-development-branch, writing-skills, using-superpowers.

Priority order:
1. Process skills first (brainstorming, debugging): these determine HOW to approach the task
2. Implementation skills second: they guide execution

"Let's build X" -> brainstorming first, then implementation skills.
"Fix this bug" -> systematic-debugging first, then domain-specific skills.

# <<< dotfiles-managed >>>

# >>> local overrides (setup.sh never touches below) <<<

# Machine-local and personal instructions live below this line. setup.sh never
# reads or overwrites anything here; the managed block above is the only part
# this repo owns. Add your personal sections below, for example:
#
#   ## Identity and Preferences
#   ## Model Preference        (pin your default model; settings.json is authoritative)
#   ## Context
#   ## Safety and Security     (work / PHI-specific rules)
#   ## Commit and Branch Rules
#   ## Output Directories
#
# Populate these per machine.
