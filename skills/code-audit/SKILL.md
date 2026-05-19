---
name: code-audit
version: "0.4.0"
description: >
  Comprehensive read-only code audit for any repository. Orchestrates SAST tools
  (ruff, bandit, semgrep, radon, eslint, tflint, etc.), skills-hub AI skills
  (cto-review, security-review, tech-debt, code-smell), and custom analysis passes
  (error handling, test gaps, complexity deep dive) to produce a unified audit report.
  Use when: "audit this repo", "code audit", "full repo review", "code review the
  whole repo", "check code quality", or "/code-audit [path]".
---

# Code Audit

Comprehensive read-only audit of any repository. Produces a unified markdown report
covering architecture, security, code quality, error handling, test gaps, complexity,
and technical debt.

## When to Use This Skill

Use this skill when the request involves:
- Auditing an entire repository or major subsystem
- Comprehensive code quality review (not just a PR diff)
- Finding architectural issues, code smells, or spaghetti code
- Identifying test gaps and untested error paths
- Getting an overall health assessment of a codebase
- Any request like "audit this repo", "how healthy is this codebase", "full code review"

Do NOT use for:
- Reviewing a specific PR or diff (use the `review` skill instead)
- Security-only review (use `security-review` directly for faster results)
- Fixing code (this is read-only; it produces a report, not changes)

## Read-Only Contract

This skill never modifies the target repository. Specifically:
- It does NOT modify any source file, config, or git state in the repo
- It writes the report to the session files directory (outside the repo)
- It installs SAST tools into a temporary location (temp venv), not the project
- It may install missing skills-hub skills globally (with user confirmation)

## Invocation

**Input:** Optional `target_path` (defaults to repo root). Everything else is
auto-detected.

**Output:** Written to session files: `<session-folder>/files/audit-report-<repo>-<branch-slug>-<date>.md`

The filename includes:
- `<repo>`: repository name (e.g., `tachikoma`)
- `<branch-slug>`: first 2-3 words of branch name after prefix (e.g., `credential-backend` from `feature/credential-backend-abstraction`)
- `<date>`: YYYY-MM-DD

This ensures multiple audits in the same session (or across sessions) never overwrite each other.

The session folder path is provided in the `<session_context>` system block at the
start of the conversation. Use that path. The `files/` subdirectory is the standard
location for persistent session artifacts.

If the user specifies a custom output path (e.g., `--output ~/reports/audit.md`),
use that instead of the session default.

When invoked, proceed to Phase 1.

## Exclusion Rules (canonical list)

All phases reference this single list. Tool-specific syntax varies but the
semantics are the same: never scan these directories or file patterns.

**Excluded directories:**
`node_modules/`, `.venv/`, `venv/`, `env/`, `.env/`, `dist/`, `build/`, `out/`,
`target/`, `.terraform/`, `.terragrunt-cache/`, `vendor/`, `third_party/`,
`__pycache__/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `.git/`,
`generated/`, `gen/`, `auto_generated/`, `codegen/`

**Excluded file patterns:**
`*_pb2.py`, `*_pb2_grpc.py`, `*.pb.go`, `*.min.js`, `*.min.css`

**Additional rules:**
- Respect `.gitignore` patterns where tools support it
- Do not scan lock files (`package-lock.json`, `poetry.lock`, `Cargo.lock`)
  for code quality; they may be scanned for secrets only

When a tool requires its own exclusion syntax, translate from this canonical
list. Do not invent additional exclusions without noting them in the methodology.

## Token Budget and Context Management

For repos exceeding ~50K LOC, context pressure becomes the primary execution risk.
Follow these rules to prevent context exhaustion:

1. **Summarize tool outputs immediately.** After each tool runs, extract only:
   finding count, severity distribution, and top 10 findings by severity. Do not
   carry raw JSON forward into later phases.

2. **Use sub-agents for Phase 4 passes** so each custom pass gets a fresh context
   window. Pass only the relevant tool summaries as input, not full raw output.

3. **Write intermediate findings between phases.** After Phase 2 completes, write
   a `tool-scan-summary.md` to session files. After Phase 3, write
   `ai-agent-summary.md`. Phase 5 reads these files rather than relying on
   conversation memory.

4. **Progressive disclosure in the report.** List all CRITICAL and HIGH findings
   individually. For MEDIUM: list top 10, then "and N more in category X." For
   LOW: summarize as a count table by category. For INFO: one-line summary only.

5. **Size gate adjustment.** If the repo exceeds 100K LOC, the size gate (Step 1.4)
   offers scoping. Between 50K-100K LOC, note: "Large repo; applying context
   management." No user prompt needed.

## Phase 1: Reconnaissance and Tool Setup

Run these steps sequentially at the start of every audit.

### Step 1.1: Detect repository stack

Scan the repo root for manifest and config files to determine which languages,
frameworks, and tools are in use:

| Manifest file | Indicates |
|--------------|-----------|
| `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements.txt`, `Pipfile` | Python |
| `package.json` | JavaScript / TypeScript |
| `tsconfig.json` | TypeScript (confirms JS detection) |
| `go.mod` | Go |
| `Cargo.toml` | Rust |
| `*.tf` | Terraform |
| `ansible.cfg`, `playbooks/`, `roles/` | Ansible |
| `Gemfile` | Ruby |
| `pom.xml`, `build.gradle` | Java |
| `composer.json` | PHP |
| `.gitlab-ci.yml` | GitLab CI |
| `.github/workflows/*.yml` | GitHub Actions CI |
| `Dockerfile`, `docker-compose.yml` | Docker |

Use `glob` and `view` to check for these files. Record all detected stacks.

### Step 1.2: Collect repo metrics

Run these commands to gather baseline metrics. Apply the canonical exclusion
rules from the "Exclusion Rules" section above. The helper variable below
encodes them for `find`:

```bash
# Build exclusion args from canonical list (define once, reuse below)
EXCL="-not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*' \
  -not -path './venv/*' -not -path './env/*' -not -path './.env/*' \
  -not -path './__pycache__/*' -not -path './dist/*' -not -path './build/*' \
  -not -path './out/*' -not -path './.terraform/*' -not -path './.terragrunt-cache/*' \
  -not -path './vendor/*' -not -path './third_party/*' -not -path './target/*' \
  -not -path './generated/*' -not -path './gen/*' -not -path './auto_generated/*' \
  -not -path './codegen/*' -not -path './.mypy_cache/*' -not -path './.ruff_cache/*' \
  -not -path './.pytest_cache/*' -not -name '*_pb2.py' -not -name '*_pb2_grpc.py' \
  -not -name '*.pb.go' -not -name '*.min.js' -not -name '*.min.css'"

# Total files
eval "find . -type f $EXCL" | wc -l

# LOC estimate (source code only - excludes config/data)
eval "find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' \
  -o -name '*.go' -o -name '*.rs' -o -name '*.rb' -o -name '*.java' \) $EXCL" \
  | xargs wc -l 2>/dev/null | tail -1

# Config/IaC LOC (separate count - do not add to source LOC)
eval "find . -type f \( -name '*.tf' -o -name '*.yml' -o -name '*.yaml' \
  -o -name '*.toml' -o -name '*.json' \) $EXCL" \
  | xargs wc -l 2>/dev/null | tail -1

# Largest source files (top 20)
eval "find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.go' \) $EXCL" \
  | xargs wc -l 2>/dev/null | sort -rn | head -20

# Max directory depth
eval "find . -type d $EXCL" | awk -F/ '{print NF-1}' | sort -rn | head -1
```

### Step 1.3: Read existing CI configuration

If `.gitlab-ci.yml` or `.github/workflows/` exists, read the CI config to understand
which checks already run. Note:
- Which linters are configured (ruff, eslint, pylint, etc.)
- Which security scanners run (bandit, semgrep, snyk, etc.)
- Whether tests run and with what coverage tool
- Whether type checking is configured (mypy, tsc, etc.)

This informs the report: "Your CI already checks X, Y, Z."

### Step 1.4: Size gate

If LOC exceeds 100,000:

> "This is a large repository (~N LOC). A full audit will be token-intensive and
> may take a while. Would you like to scope the audit to a specific directory, or
> proceed with the full repo?"

Use `ask_user` with choices: `["Proceed with full repo", "Scope to a subdirectory"]`

If the user chooses to scope, ask for the target path.

### Step 1.5: Install SAST tools

Based on detected stacks, install missing SAST tools into a temporary venv:

```bash
# Create temp venv for audit tools
AUDIT_VENV=$(mktemp -d)/audit-venv
python3 -m venv "$AUDIT_VENV"
AUDIT_PIP="$AUDIT_VENV/bin/pip"
AUDIT_BIN="$AUDIT_VENV/bin"
```

Install tools per detected stack:

| Stack | Install command |
|-------|----------------|
| Python | `$AUDIT_PIP install -q ruff bandit radon vulture` |
| JS/TS | Check if eslint is already in node_modules; do not npm install into the project. |
| Terraform | Check if `tflint` and `checkov` are on PATH. If not, `$AUDIT_PIP install -q checkov` (tflint requires binary install, skip if not available). |
| Ansible | `$AUDIT_PIP install -q ansible-lint` |
| Go | Check if `staticcheck` and `gosec` are on PATH. Skip if not (Go tools require go install). |
| General | `$AUDIT_PIP install -q detect-secrets` |

**Semgrep:** Do NOT install semgrep for the audit (200MB+ package, slow install).
If `semgrep` is already available on the system PATH, use it opportunistically.
Otherwise, rely on Bandit (Python security) and the security-review AI skill
(cross-language pattern detection).

For each tool, log success or failure. Never abort on a tool install failure.

After installing, verify tools are callable:

```bash
$AUDIT_BIN/ruff --version 2>/dev/null && echo "ruff: OK" || echo "ruff: FAILED"
$AUDIT_BIN/bandit --version 2>/dev/null && echo "bandit: OK" || echo "bandit: FAILED"
$AUDIT_BIN/radon --version 2>/dev/null && echo "radon: OK" || echo "radon: FAILED"
$AUDIT_BIN/vulture --version 2>/dev/null && echo "vulture: OK" || echo "vulture: FAILED"
$AUDIT_BIN/detect-secrets --version 2>/dev/null && echo "detect-secrets: OK" || echo "detect-secrets: FAILED"
$AUDIT_BIN/ansible-lint --version 2>/dev/null && echo "ansible-lint: OK" || echo "ansible-lint: FAILED"
$AUDIT_BIN/checkov --version 2>/dev/null && echo "checkov: OK" || echo "checkov: FAILED"
command -v semgrep &>/dev/null && echo "semgrep: OK (pre-installed)" || echo "semgrep: NOT FOUND (skip)"
command -v tflint &>/dev/null && echo "tflint: OK" || echo "tflint: NOT FOUND (skip)"
command -v staticcheck &>/dev/null && echo "staticcheck: OK" || echo "staticcheck: NOT FOUND (skip)"
command -v gosec &>/dev/null && echo "gosec: OK" || echo "gosec: NOT FOUND (skip)"
```

### Step 1.6: Check skills-hub dependencies

Check if the required skills-hub skills are installed:

```bash
for skill in cto-review security-review tech-debt code-smell; do
  if [ -d "$HOME/.copilot/skills/$skill" ] || \
     [ -d "$HOME/.copilot/skills/gstack-$skill" ] || \
     [ -d "$HOME/.claude/skills/$skill" ] || \
     [ -d "$HOME/.claude/skills/gstack-$skill" ]; then
    echo "$skill: installed"
  else
    echo "$skill: MISSING"
  fi
done
```

If any are missing, collect the missing skill names and inform the user:

> "The following skills-hub skills are not installed and will be needed for AI
> reasoning passes: [comma-separated list]. Install them now with
> `npx @skills-hub-ai/cli install [skill]`?"

Use `ask_user` with choices: `["Yes, install them", "Skip AI reasoning passes"]`

If installing, run the install commands. If skipped, note in the report methodology
that those passes were unavailable.

After Phase 1 completes, you have a `RepoProfile` (mental model, not a data
structure): detected stacks, file counts, LOC, CI config summary, available tools,
available skills.

**Critical execution note:** Launch Phase 3 AI agents IMMEDIATELY after Phase 1,
before waiting for Phase 2 tool scans to complete. Phase 3 agents do not depend
on Phase 2 output; they read source code directly. Running Phases 2 and 3 in
parallel saves 10-15 minutes on a typical audit. The orchestrator (you) should:

1. Start all Phase 2 tool commands (bash, background)
2. Immediately launch all Phase 3 sub-agents (task, background)
3. Collect results from both as they complete
4. Write intermediate summaries after both finish

## Phase 2: Automated Tool Scans (parallel)

Run all available SAST tools in parallel using background bash commands or sub-agents.
Each tool produces raw output that will be normalized later.

**Exclusion rules:** Apply the canonical exclusion list from the "Exclusion Rules"
section above. Translate to each tool's syntax as needed.

### Tool Output Handling

For every tool execution:
1. Separate stdout from stderr: `tool args >tool-stdout.txt 2>tool-stderr.txt`
2. If JSON output is requested and the result is malformed or unparseable,
   re-run the tool with text output format and parse manually.
3. If text output is also unusable, record as `TOOL_ERROR` with the first
   20 lines of stderr. **Never treat a tool error as "no findings."**
4. After each tool completes, immediately extract a summary: finding count,
   severity distribution, and top 10 findings by severity. Discard raw output
   from context (write to session files if needed for the report appendix).

### Tool commands

Run each applicable tool. Use `--format json` or equivalent where available.
Fall back to text format if JSON parsing fails.

**Python tools** (if Python detected):

```bash
# Ruff: lint violations
$AUDIT_BIN/ruff check . --output-format json --exclude node_modules,.venv,venv,dist,build,__pycache__,.git 2>ruff-stderr.txt

# Bandit: security findings (text format is more reliable than JSON at project root)
$AUDIT_BIN/bandit -r . -f txt --exclude .venv,venv,node_modules,dist,build,.git -ll 2>bandit-stderr.txt

# Semgrep (only if pre-installed on system PATH)
if command -v semgrep &>/dev/null; then
  semgrep scan --config auto --json \
    --exclude node_modules --exclude .venv --exclude venv --exclude vendor \
    --exclude dist --exclude build --exclude out --exclude target \
    --exclude .terraform --exclude generated --exclude __pycache__ \
    --exclude .git \
    . 2>semgrep-stderr.txt
fi

# Radon: cyclomatic complexity
$AUDIT_BIN/radon cc . -s -j --exclude "node_modules,venv,.venv,dist,build" 2>radon-cc-stderr.txt

# Radon: maintainability index
$AUDIT_BIN/radon mi . -s -j --exclude "node_modules,venv,.venv,dist,build" 2>radon-mi-stderr.txt

# Vulture: dead code
$AUDIT_BIN/vulture . --exclude "node_modules,venv,.venv,dist,build,.git" 2>vulture-stderr.txt

# Mypy: type errors (only if mypy config exists AND mypy is installed)
if [ -f "mypy.ini" ] || [ -f "setup.cfg" ] || grep -q '\[tool.mypy\]' pyproject.toml 2>/dev/null; then
  if $AUDIT_BIN/mypy --version &>/dev/null; then
    $AUDIT_BIN/mypy . --no-error-summary 2>mypy-stderr.txt
  fi
fi

# detect-secrets: hardcoded secrets
$AUDIT_BIN/detect-secrets scan \
  --exclude-files 'node_modules/|\.venv/|venv/|vendor/|dist/|build/|\.git/|generated/|__pycache__/|\.terraform/' \
  . 2>detect-secrets-stderr.txt
```

**detect-secrets post-scan filtering:**

`detect-secrets` produces high false-positive rates on data files, test fixtures,
and hex/base64 content. After scanning, filter results before counting findings:

1. **Exclude data-heavy files:** Files with >50 findings are almost certainly data
   files (e.g., quote databases, test fixtures, seed data). Remove them from the
   finding count and note: "Excluded N files with >50 detections each (likely data)."
2. **Filter by secret type:** `Hex High Entropy String` findings in `.py` data files,
   `.json` fixtures, and `.yaml` seed files are nearly always false positives.
   Downgrade these to INFO unless they appear in config files, env files, or code
   that handles credentials.
3. **Cross-reference with .gitignore:** Findings in gitignored files are lower risk
   (they won't be committed). Note but do not count them toward the finding total.
4. **Confidence threshold:** Only count findings with confidence > 3 (on detect-secrets'
   internal scale) as actionable. Lower-confidence findings go in the appendix.

**JS/TS tools** (if JS/TS detected):

```bash
# ESLint (only if config exists in the project)
if [ -f ".eslintrc.js" ] || [ -f ".eslintrc.json" ] || [ -f ".eslintrc.yml" ] || [ -f "eslint.config.js" ] || [ -f "eslint.config.mjs" ]; then
  npx eslint . --format json 2>eslint-stderr.txt
fi

# Semgrep (only if pre-installed and not already run in Python section)
if command -v semgrep &>/dev/null && [ ! -f "semgrep-stderr.txt" ]; then
  semgrep scan --config auto --json \
    --exclude node_modules --exclude .venv --exclude venv --exclude vendor \
    --exclude dist --exclude build --exclude out --exclude target \
    --exclude .terraform --exclude generated --exclude __pycache__ \
    --exclude .git \
    . 2>semgrep-stderr.txt
fi
```

**Terraform tools** (if Terraform detected):

```bash
# tflint (if available)
if command -v tflint &>/dev/null; then
  tflint --format json 2>&1
fi

# checkov
$AUDIT_BIN/checkov -d . --output json --quiet 2>&1
```

**Ansible tools** (if Ansible detected):

```bash
# ansible-lint (only if config exists or playbooks directory found)
$AUDIT_BIN/ansible-lint -f json 2>&1
```

**Go tools** (if Go detected):

```bash
# staticcheck (if available)
if command -v staticcheck &>/dev/null; then
  staticcheck -f json ./... 2>&1
fi

# gosec (if available)
if command -v gosec &>/dev/null; then
  gosec -fmt json ./... 2>&1
fi
```

### Tool execution contract

For each tool, record the outcome:

- **Success with findings**: tool ran and produced output. Save the output.
- **Success with no findings**: tool ran and produced empty/clean output. Note in methodology.
- **Tool failure**: tool could not run. Record the error message. Do NOT treat as
  "no findings." Note prominently in the report methodology section.

Tools that require project-specific config (mypy without type stubs, eslint without
config, terraform validate without init) are skipped with a note:
"Skipped [tool]: no project configuration found."

### Coverage data

**Coverage collection is intentionally omitted.** Running tests may have side
effects (DB writes, file creation, API calls) that violate the read-only contract.
Test gap analysis in Phase 4b uses structural heuristics instead:
- File naming conventions (test_*.py, *.test.ts, *_test.go)
- Radon complexity scores cross-referenced with test file existence
- Public API surface analysis

If the user explicitly requests coverage data and confirms they accept potential
side effects, you may offer to run it as a separate step outside the audit flow.

After all tools complete, collect their outputs and proceed to Phase 4.

## Phase 3: AI Reasoning Passes (parallel with Phase 2)

Dispatch skills-hub skills as sub-agents in parallel. Each skill runs autonomously
against the repo. Use the `task` tool to launch each as a background agent:

### Dispatch all four skills simultaneously

Launch all four skills as background agents using the `task` tool. Replace
`<REPO_PATH>` below with the actual absolute path to the repository root (from
`git rev-parse --show-toplevel` or `pwd`).

Each agent is launched with `agent_type="general-purpose"` and `mode="background"`.
Use `read_agent` to collect results after all agents complete.

**Agent 1: CTO Review**

Use the `task` tool:
- `agent_type`: `"general-purpose"`
- `mode`: `"background"`
- `name`: `"cto-review-pass"`
- `description`: `"CTO architecture review"`
- `prompt`: `"You are running a CTO-level architecture review of this repository. Follow the /cto-review skill instructions. Evaluate: architecture decisions, scaling readiness, engineering velocity, technical debt ratio, security posture, team scalability, and cost efficiency. Produce a complete report. Repository root: <REPO_PATH>"`

**Agent 2: Security Review**

Use the `task` tool:
- `agent_type`: `"general-purpose"`
- `mode`: `"background"`
- `name`: `"security-review-pass"`
- `description`: `"Security audit"`
- `prompt`: `"You are running a comprehensive security review of this repository. Follow the /security-review skill instructions. Cover OWASP Top 10, auth audit, injection analysis, data flow tracing, secrets management, and session/transport security. Produce a complete report with file:line citations. Repository root: <REPO_PATH>"`

**Agent 3: Tech Debt**

Use the `task` tool:
- `agent_type`: `"general-purpose"`
- `mode`: `"background"`
- `name`: `"tech-debt-pass"`
- `description`: `"Technical debt inventory"`
- `prompt`: `"You are running a technical debt inventory of this repository. Follow the /tech-debt skill instructions. Scan for TODO/FIXME/HACK markers, high-churn files, cyclomatic complexity hotspots, duplicated code, god objects (500+ lines), circular dependencies, and architectural inconsistencies. Produce a scored priority backlog with a debt score. Repository root: <REPO_PATH>"`

**Agent 4: Code Smell**

Use the `task` tool:
- `agent_type`: `"explore"`
- `mode`: `"background"`
- `name`: `"code-smell-pass"`
- `description`: `"Code smell detection"`
- `prompt`: (see structured prompt below)

The code-smell agent uses `explore` type (not `general-purpose`) because it needs
fast grep/glob scanning across many files rather than deep reasoning on few files.
Use this structured prompt to prevent the agent from stalling on full-file reads:

```
You are scanning a repository for Martin Fowler code smells. Work efficiently:
use grep and glob to find patterns, then read only the specific functions that
match. Do NOT read entire large files.

Repository root: <REPO_PATH>

Scan for these smells in order. For each, use the grep pattern provided, then
read only the matching locations (view with line ranges, not full files):

1. GOD CLASSES: find files >500 lines:
   find <REPO_PATH> -name '*.py' -o -name '*.ts' -o -name '*.js' | xargs wc -l | sort -rn | head -20
   For each >500 lines, check if it has >10 methods and >5 responsibilities.

2. LONG METHODS: find functions >50 lines. Use grep to find def/function lines,
   then check spacing to the next def.

3. FEATURE ENVY: grep for methods that reference another class/module more than
   their own (look for repeated `other_module.` or `self.other.` patterns).

4. DATA CLUMPS: grep for functions with >4 parameters that share 3+ param names
   with other functions.

5. PRIMITIVE OBSESSION: grep for functions with >3 string parameters or repeated
   isinstance checks.

6. SHOTGUN SURGERY: use grep to find a concept (class name, function name) that
   appears in >5 different files.

7. MESSAGE CHAINS: grep for lines with 3+ chained dots (e.g., a.b.c.d).

Produce a prioritized list of findings with: smell type, file:line, severity
(CRITICAL/HIGH/MEDIUM/LOW), and a one-line refactoring recommendation.
Skip directories: node_modules, .venv, venv, __pycache__, dist, build, .git
```

### Collecting results

Wait for all four agents to complete, with **tiered timeouts:**

| Agent | Timeout | Rationale |
|-------|---------|-----------|
| security-review | 15 min | Deep analysis with verification; most valuable agent |
| cto-review | 12 min | Broad architecture scan across many files |
| tech-debt | 10 min | Focused pattern search with scoring |
| code-smell | 8 min | Grep-heavy explore agent; should finish fast |

**Timeout handling:**
- At the timeout, check agent status with `read_agent`.
- If an agent is still running, give it 2 more minutes. If still running after
  timeout + 2 minutes, proceed without that agent's results.
- Note timed-out agents in the methodology section: "Agent X timed out after N
  minutes; results unavailable for this run."

**Quality gate on agent output:**
- If an agent's output is less than 100 words, discard it and note as FAILED
  (likely hit an error early and produced no useful analysis).
- If an agent's output contains no file references or severity assessments,
  treat it as low-quality and note in methodology. Still include if it has
  useful narrative content.
- If an agent produces an error message instead of a report, record the error
  and proceed without that agent.

**Graceful degradation:** The audit can produce a useful report with as few as
zero AI agents completing (tool scans + custom passes still provide value).
The report quality improves with each agent that completes successfully.

### Normalizing skill output

Skills produce markdown reports. Extract structured findings on a best-effort basis:

1. Parse severity headings (CRITICAL, HIGH, MEDIUM, LOW, INFO)
2. Extract file paths and line numbers from code blocks and inline references
3. Map to canonical finding schema:
   - `source`: skill name (e.g., "cto-review")
   - `category`: map to `architecture | security | quality | debt | complexity`
   - `severity`: from heading context
   - `confidence`: default to MEDIUM for AI-reasoning findings
   - `file`, `line`: extracted from references, null if not found
   - `title`, `description`, `risk`, `recommendation`: from finding text

4. Findings that cannot be cleanly extracted remain as raw markdown. They are
   included verbatim in the relevant report section and still counted for scoring.

### Write intermediate summary

After all Phase 3 agents complete (or time out), write an `ai-agent-summary.md`
to session files. This file captures the normalized findings from each agent and
is read by Phase 4 and Phase 5 instead of relying on conversation memory.

Include for each agent that completed:
- Agent name and completion status (completed / timed out / failed)
- Number of findings by severity
- Top 5 findings (title, file, severity, one-line description)
- Key themes or patterns identified

For agents that timed out or failed, note: "Agent X: [status]. No findings available."

This file is mandatory for repos over 50K LOC and recommended for all repos.

## Phase 4: Custom Gap Passes (parallel via sub-agents)

These passes run AFTER Phases 2 and 3 complete. They use tool scan results and
skill outputs as context to perform deeper analysis that no existing tool or skill
covers adequately.

**Sub-agent dispatch:** Launch each Phase 4 pass as a separate sub-agent to get
fresh context windows. This prevents context exhaustion from accumulated Phase 2/3
data. Pass only the relevant summaries from `tool-scan-summary.md` and
`ai-agent-summary.md` (written at the end of Phases 2 and 3 respectively), not
raw tool output. Also pass the `AUDIT_VENV` path (`$AUDIT_BIN`) in case a
sub-agent needs to re-run radon or bandit on specific files for verification.

Agent type selection:
- **4a (Error Handling):** `agent_type="general-purpose"` (needs to read and reason
  about error paths in context).
- **4b (Test Gaps):** `agent_type="explore"` (grep-heavy import scanning across many
  test files; does not need deep reasoning per file).
- **4c (Complexity Deep Dive):** `agent_type="general-purpose"` (needs to read
  functions and reason about structure).

Launch all three passes in parallel:
- **4a (Error Handling):** Pass the repo path and the list of files with broad
  exception catches from the tool scan summary.
- **4b (Test Gaps):** Pass the repo path, the test file inventory from Phase 1
  metrics, and the radon CC hotspots from the tool scan summary.
- **4c (Complexity Deep Dive):** Pass the repo path, the radon CC top-20
  functions, and any coupling data from the CTO review summary.

Collect results with `read_agent`. Timeouts scale with repo LOC:

| LOC range | Error Handling | Test Gaps | Complexity |
|-----------|---------------|-----------|------------|
| < 50K | 8 min | 5 min | 8 min |
| 50K-100K | 12 min | 8 min | 12 min |
| > 100K | 15 min | 10 min | 18 min |

**Exclusion rules apply to all custom passes.** Use the canonical exclusion list
from the "Exclusion Rules" section. Do not analyze files in excluded directories
or generated files.

**Read-only contract:** This audit is strictly read-only. Sub-agents must NOT
create files in the target repository (some gstack skills create `.gstack/`
directories by default). If a sub-agent prompt template references file creation,
override it: instruct the agent to return findings as text output only, not as
files. The only files this audit creates are in the session workspace
(`tool-scan-summary.md`, `ai-agent-summary.md`, and the final `audit-report-<repo>-<branch>-<date>.md`).

**All findings from custom passes must use the full canonical schema:**
```
finding:
  id: "<source>-<short-id>-<file>:<line>"
  source: "<pass-name>"
  category: "<architecture|security|quality|error-handling|test-gap|debt|complexity>"
  severity: "<CRITICAL|HIGH|MEDIUM|LOW|INFO>"
  confidence: "<HIGH|MEDIUM|LOW>"
  file: "<relative file path>"
  line: <line number or range, null if not applicable>
  title: "<one-line summary>"
  description: "<detailed explanation>"
  risk: "<concrete consequence>"
  recommendation: "<specific fix>"
  tool_evidence: null
```

### Phase 4a: Error Handling Audit

Scan the codebase for error handling anti-patterns using grep-first methodology.

**This pass uses `agent_type="general-purpose"`** because it needs to read error
handling context around matches and reason about whether the pattern is dangerous.
However, it MUST use grep to find candidates first, then read only the surrounding
context (5-10 lines) for each match. Do NOT read entire files.

Use this structured prompt for the sub-agent:

```
You are auditing error handling patterns in this repository. Work efficiently:
use grep to find all exception handling patterns first, then read only 5-10 lines
of context around each match to assess severity.

Repository root: <REPO_PATH>

STEP 1: Find all exception handling patterns (run these grep commands):

# Bare except (CRITICAL)
grep -rn "except:" --include="*.py" <REPO_PATH> | grep -v ".venv\|venv\|__pycache__\|node_modules\|/tests/"

# Except with pass/continue (potential swallow)
grep -rn -A 1 "except.*:" --include="*.py" <REPO_PATH> | grep -B 1 "pass$\|continue$" | grep -v ".venv\|__pycache__\|/tests/"

# Broad except Exception
grep -rn "except Exception" --include="*.py" <REPO_PATH> | grep -v ".venv\|__pycache__\|/tests/" | head -50

# Missing 'from' in re-raises
grep -rn "raise.*Error\|raise.*Exception" --include="*.py" <REPO_PATH> | grep -v "from \|from$" | grep -v ".venv\|__pycache__\|/tests/" | head -30

# from None (intentional cause suppression)
grep -rn "from None" --include="*.py" <REPO_PATH> | grep -v ".venv\|__pycache__"

STEP 2: For each grep match, read ONLY 5-10 lines of context (view with line range).
Assess whether the pattern is actually dangerous based on:
- Is this in state-modifying code? (CRITICAL if swallowed)
- Is this at a boundary (entry point)? (HIGH if missing handler)
- Is this in read-only code? (MEDIUM/LOW)

STEP 3: Check boundary handlers at entry points:
grep -rn "def main\|@app.route\|@click.command\|@router." --include="*.py" <REPO_PATH> | grep -v ".venv\|__pycache__\|/tests/"
For each entry point, check if it has a top-level try/except within 5 lines.

Produce max 15 findings (focus on CRITICAL and HIGH). For each:
severity, file:line, title, description, risk, recommendation.
Focus on source code (not test files).
```

Severity classification for the agent's reference:

**CRITICAL severity:**
- **Bare exception handlers**: `except:` or `catch {}` with no specific type.
  These silently swallow every error including system exits and keyboard interrupts.
- **Swallowed exceptions with side effects**: caught exceptions in code that modifies
  state (DB writes, file operations, API calls) with no logging, re-raise, or
  meaningful handling. Silent state corruption risk.

**HIGH severity:**
- **Missing boundary handlers**: entry points (API endpoints, CLI commands, queue
  consumers, scheduled tasks) with no top-level try/except or error middleware.
  Unhandled exceptions in these locations crash the process or leak stack traces.
- **Incomplete error propagation**: errors caught at an intermediate layer that lose
  the original context. In Python: `raise NewError("msg")` without `from original`.
  In JS: `throw new Error("msg")` discarding the original error.
- **Missing cleanup**: resources acquired in try blocks (file handles, DB connections,
  locks, temp files) without finally blocks or context managers/using statements.

**MEDIUM severity:**
- **Swallowed exceptions (non-state)**: caught exceptions with `pass` or empty body
  in read-only code. Less dangerous but hides bugs.
- **Exception as flow control**: using try/except where a conditional check would be
  clearer and more efficient (e.g., `try: d[key] except KeyError` instead of
  `if key in d`).
- **Inconsistent error types**: same logical error raised as different exception types
  in different modules (e.g., `ValueError` in one place, `RuntimeError` in another
  for the same semantic error).
- **Missing error logging**: caught exceptions that are handled (retried, defaulted)
  but never logged. Hides systemic issues.

**LOW severity:**
- **Silent failures**: functions that return None or empty collections on error
  instead of raising. Only flag if the caller does not check the return value.
- **Overly broad exception types**: `except Exception` where a more specific type
  is clearly appropriate.
- **Redundant try/except**: wrapping code that cannot raise the caught exception type.

For each finding, produce a full canonical finding:
- `id`: "error-handling-<pattern>-<file>:<line>" (e.g., "error-handling-bare-except-src/api.py:42")
- `source`: "error-handling-audit"
- `category`: "error-handling"
- `severity`: per the severity rules above
- `confidence`: HIGH for pattern matches (bare except, missing from), MEDIUM for judgment calls (exception as flow control)
- `file`: exact relative file path
- `line`: exact line number
- `title`: one-line summary (e.g., "Bare except handler swallows all exceptions")
- `description`: what the code does and why it is problematic
- `risk`: concrete consequence (e.g., "KeyboardInterrupt and SystemExit are silently caught, preventing clean shutdown")
- `recommendation`: specific fix (e.g., "Replace `except:` with `except SpecificError:` or at minimum `except Exception:`")

### Phase 4b: Test Gap Analysis

Cross-reference tool scan results (radon CC scores) with code structure to
identify the most dangerous test gaps. Coverage data is not collected (to honor
the read-only contract), so this analysis uses structural heuristics.

**This pass uses `agent_type="explore"`** because it needs fast grep/glob scanning
across many test files for import patterns, not deep reasoning on individual files.
Use this structured prompt:

```
You are analyzing test coverage gaps in a repository using structural heuristics.
Work efficiently: use grep and find commands to scan imports in bulk. Do NOT read
entire test files. Read only the first 30 lines of each test file for imports.

Repository root: <REPO_PATH>

STEP 1: Build inventories (run these commands first):

# All source modules (non-test, non-init Python files)
find <REPO_PATH> -name '*.py' -not -name 'test_*' -not -name '*_test.py' \
  -not -name '__init__.py' -not -name 'conftest.py' \
  -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/venv/*' \
  -not -path '*/__pycache__/*' -not -path '*/node_modules/*' \
  | sort

# All test files
find <REPO_PATH> -type f \( -name 'test_*.py' -o -name '*_test.py' \) \
  -not -path '*/.git/*' -not -path '*/.venv/*' -not -path '*/venv/*' \
  | sort

STEP 2: Batch import extraction (DO NOT read files one-by-one):

# Extract all imports from all test files in one command
grep -rn "^from \|^import " --include='test_*.py' --include='*_test.py' <REPO_PATH>/tests/ \
  | grep -v __pycache__ | grep -v .venv

This gives you a complete map of what each test imports.

STEP 3: Match source modules to test coverage:

For each source module path, check if ANY test file imports it (by module name).
A source module is "covered" if at least one test file imports from it.

STEP 4: Find gaps:

Report only modules where NO test file imports from them. For each gap:
- Check if the module has functions with CC >= 11 (from radon data: <PASTE_CC_HOTSPOTS>)
- HIGH severity if CC >= 11 and no test
- MEDIUM severity if no test but low complexity
- LOW if test exists but only partial coverage visible from imports

STEP 5: Quick quality check:

# Tests with no assertions (just pass or assert True)
grep -rn "def test_" --include='test_*.py' <REPO_PATH>/tests/ -A 3 | grep -B 1 "pass$\|assert True"

# Very long test functions (>50 lines between defs)
# Skip this if time is short

Produce findings with: severity, file:line, title, risk, recommendation.
Be conservative: only flag genuinely untested modules, not naming-convention
mismatches.

ADDITIONAL CHECKS (if time permits within 5 min):

6. Untested public API: find modules that export from __init__.py but have no test.
7. Missing integration tests: find CLI/API entry points with no test exercising
   the full call path (grep for @click.command or @app.route, cross-ref with tests).
8. Test quality: already covered in STEP 5 (no-assertion tests).
```

For each finding, produce a full canonical finding:
- `id`: "test-gap-<type>-<file>:<line>" (e.g., "test-gap-high-cc-no-coverage-src/auth.py:15")
- `source`: "test-gap-analysis"
- `category`: "test-gap"
- All other canonical fields populated per the schema above

### Phase 4c: Complexity Deep Dive

Use radon CC scores from Phase 2 plus targeted code reading to identify spaghetti
code and maintainability risks.

**This pass uses `agent_type="general-purpose"`** because it needs to read function
bodies and reason about structure. However, it MUST only read the specific functions
identified by radon (using view with line ranges), not entire files.

Use this structured prompt for the sub-agent:

```
You are doing a complexity deep dive on this repository. Read ONLY the specific
functions listed below (use view with line ranges). Do NOT read entire files.

Repository root: <REPO_PATH>

RADON HOTSPOTS (top 20 by CC score, from Phase 2):
<PASTE_RADON_TOP_20_HERE>

STEP 1: For each of the top 10 hotspots, read ONLY that function (view the
specific line range). Assess:
- Nesting depth (count max indentation, flag if >= 4)
- Multiple responsibilities (does it do >1 distinct thing?)
- God function indicators (>50 lines, >5 params, >3 data sources)
- Specific refactoring recommendation (not generic advice)

STEP 2: Coupling analysis (use grep, not full-file reads):

# Fan-in: count importers per module
grep -rn "^from \|^import " --include="*.py" <REPO_PATH> | grep -v ".venv\|__pycache__\|node_modules" > /tmp/imports.txt
# Then count how many files import each module

# Circular imports: look for mutual imports between modules
# Check the top fan-in modules for back-imports

STEP 3: Churn analysis (if git available):
git -C <REPO_PATH> log --since="6 months ago" --name-only --pretty=format: | sort | uniq -c | sort -rn | head -20

If git log produces no output, note "churn unavailable" and skip.

STEP 4: Cross-reference: files that are BOTH high-CC AND high-churn are the
worst risks. Flag these as HIGH severity.

Produce a top 10 hotspot table and max 10 findings with:
severity, file:line, CC score, churn count, what makes it complex,
specific refactoring recommendation.
```

**Step 1: Identify complexity hotspots**

From radon output, extract all functions/methods with CC grade C or worse (CC >= 11).
Sort by CC score descending. These are the primary candidates for deep analysis.

If radon was not available (non-Python repo), use AI reasoning to estimate complexity:
read the largest source files (from Phase 1 metrics) and identify functions with
deep nesting, many branches, or long bodies.

**Step 2: Analyze each hotspot**

For each of the top 20 complexity hotspots (or fewer if less exist), read the
function and assess:

- **Nesting depth**: count the maximum indentation level. Flag if >= 4 levels.
- **Multiple responsibilities**: does the function do more than one distinct thing?
  (e.g., validates input AND queries DB AND formats output)
- **Control flow clarity**: are there complex conditional chains, multiple return
  points with side effects, or state machines without clear state transitions?
- **God function indicators**: function length > 50 lines, > 5 parameters,
  accesses > 3 different data sources

**Step 3: Coupling analysis**

Analyze module-level coupling:
- **Fan-in**: how many other modules import this module? High fan-in (> 10)
  indicates a central dependency that is risky to change.
- **Fan-out**: how many modules does this module import? High fan-out (> 10)
  indicates the module depends on too many things.
- **Circular imports**: check for import cycles. Use:
  ```bash
  # For Python
  grep -r "^from \|^import " --include="*.py" . | \
    grep -v node_modules | grep -v .venv | grep -v __pycache__
  ```
  Then analyze the import graph for cycles.
- **God modules**: modules imported by > 20% of other modules in the project.

**Step 4: Maintainability hotspots**

If git history is available, cross-reference complexity with change frequency:

```bash
# Most frequently changed files in last 6 months
git log --since="6 months ago" --name-only --pretty=format: | \
  sort | uniq -c | sort -rn | head -20
```

**Git history fallback:** If `git log` produces no output (shallow clone, no git
history, or very new repo), skip churn analysis entirely and note: "Git history
unavailable or insufficient; churn analysis skipped. Run from a full clone for
richer maintainability insights." Proceed with complexity-only analysis.

Files that are both high-complexity AND high-churn are the most dangerous
maintainability risks. If coverage data is available, files that are also
low-coverage form a triple threat: complex + frequently changed + untested.
Flag these as HIGH severity.

**Step 5: Produce top 10 hotspot table**

Produce a ranked list of the top 10 complexity hotspots with:
- Function/module name
- File path and line range
- CC score (if available from radon; for non-Python, note "estimated by AI")
- Nesting depth
- What makes it complex (specific description)
- Refactoring recommendation (specific, not generic)

For each finding, produce a full canonical finding:
- `id`: "complexity-<type>-<file>:<line>" (e.g., "complexity-god-function-src/utils.py:100")
- `source`: "complexity-deep-dive"
- `category`: "complexity"
- All other canonical fields populated per the schema above

## Phase 5: Report Synthesis

After all phases complete, merge everything into a single report.

### Step 5.1: Collect all outputs

Gather:
- Tool scan outputs from Phase 2 (JSON where available, text otherwise)
- Skill outputs from Phase 3 (markdown text per skill)
- Custom pass findings from Phase 4 (canonical finding objects)
- RepoProfile from Phase 1 (stacks, metrics, CI config)
- Tool execution results (which tools ran, which failed, which were skipped)

### Step 5.2: Deduplicate findings

Multiple passes may flag the same issue (e.g., bandit and security-review both
find a hardcoded secret, or ruff and code-smell both flag a god class).

Deduplication rules:
- **Exact match:** same `file + line + category` = definite duplicate
- **Fuzzy match:** same `file + category` within 10 lines = likely duplicate
- **Conceptual match:** same `file + same concern` (e.g., "shell.py is dangerous"
  from one source and "shell.py:87 command injection" from another) = merge if
  they describe the same underlying risk, even with different granularity
- When duplicates found, keep the finding with the richest description
- Add a `also_found_by` note listing all sources that flagged it
- Only deduplicate normalized findings; raw markdown sections pass through as-is
- When in doubt, keep both findings rather than incorrectly merging distinct issues

### Step 5.3: Compute scorecard

Assign a 1-10 score for each dimension using this proportional rubric:

**Scoring formula:**
1. Start at 7 (baseline: no major issues).
2. Subtract 2 per CRITICAL finding in this dimension (minimum score: 1).
3. Subtract 1 per HIGH finding (cap deductions at 4 from HIGH alone).
4. Subtract 0.5 per significant MEDIUM cluster (3+ related MEDIUM findings).
5. Add 1 if the dimension has notable documented strengths (up to max 10).
6. Round to the nearest integer.

**Calibration guidance:**
- 9-10: Exceptional; no HIGH/CRITICAL, proactive practices evident
- 7-8: Healthy; minor issues only, good foundations
- 5-6: Moderate concerns; HIGH findings present but contained
- 3-4: Significant problems; CRITICAL findings or systemic HIGH issues
- 1-2: Severe; multiple unaddressed CRITICAL findings, fundamental gaps

Dimensions and their source data:
- **Architecture**: cto-review output + coupling analysis
- **Code Quality**: code-smell output + ruff findings + radon grades
- **Security**: security-review output + bandit + semgrep + detect-secrets
- **Error Handling**: error handling audit findings
- **Test Coverage**: test gap analysis + coverage data
- **Technical Debt**: tech-debt output + vulture (dead code)
- **Maintainability**: complexity deep dive + maintainability index

Compute an overall health score (0-100) as the average of all dimension scores
multiplied by 10. This is a qualitative summary, not a precise metric.
Round to the nearest integer.

### Step 5.4: Generate the report

Determine the output path. The default is the session files directory:

```
# Session folder is provided in <session_context> at conversation start.
# Example: /Users/username/.copilot/session-state/<uuid>
SESSION_FOLDER="<session-folder-from-context>"
OUTPUT_DIR="$SESSION_FOLDER/files"
# Derive filename components
REPO_NAME=$(basename "$(git -C "$TARGET_PATH" rev-parse --show-toplevel 2>/dev/null || echo "$TARGET_PATH")")
BRANCH_RAW=$(git -C "$TARGET_PATH" branch --show-current 2>/dev/null || echo "main")
# Strip prefix (feature/, hotfix/) and take first 2-3 kebab words
BRANCH_SLUG=$(echo "$BRANCH_RAW" | sed 's|^feature/||;s|^hotfix/||;s|^chore/||' | cut -d- -f1-3)
TODAY=$(date +%Y-%m-%d)
OUTPUT_FILE="$OUTPUT_DIR/audit-report-${REPO_NAME}-${BRANCH_SLUG}-${TODAY}.md"
```

If the session folder is not available or not writable, fall back to a temp file
and inform the user where the report was saved.

If the user specified a custom output path during invocation, use that instead
and create parent directories as needed:
```bash
mkdir -p "$(dirname "$OUTPUT_FILE")"
```

Write the report to `$OUTPUT_FILE` using this template:

```markdown
# Code Audit Report: <repo-name>

**Date**: YYYY-MM-DD
**Scope**: <path audited or "full repository">
**Stack**: <detected languages/frameworks, comma-separated>
**Files scanned**: <N> | **Lines of code**: ~<N>

---

## Executive Summary

Overall health score: **<score>/100**

<1-paragraph narrative summarizing the repo's health. Lead with the most important
finding. Be specific, not generic.>

**Top Critical Findings (up to 5):**
1. <most critical finding, one line>
2. <second most critical>
3. <third most critical>

**Top 3 Strengths:**
1. <strongest aspect of the codebase>
2. <second strongest>
3. <third strongest>

---

## Scorecard

| Dimension          | Score | Key Finding                    |
|--------------------|-------|--------------------------------|
| Architecture       | X/10  | <one-line summary>             |
| Code Quality       | X/10  | <one-line summary>             |
| Security           | X/10  | <one-line summary>             |
| Error Handling     | X/10  | <one-line summary>             |
| Test Coverage      | X/10  | <one-line summary>             |
| Technical Debt     | X/10  | <one-line summary>             |
| Maintainability    | X/10  | <one-line summary>             |

---

## Findings by Severity

### CRITICAL (fix immediately)

<list all CRITICAL findings, each with:>

**[FINDING-ID] <title>**
- **Location**: `<file>:<line>`
- **Issue**: <specific description>
- **Risk**: <concrete consequence>
- **Fix**: <specific remediation>
- **Source**: <tool/skill that found it>

### HIGH (fix soon)
<same format>

### MEDIUM (plan to address)
<same format>

### LOW (nice to have)
<same format>

### INFO (observations)
<same format>

---

## Architecture Analysis

<Insert cto-review output here, edited for consistency with the rest of the report.
Include: architecture decisions, scaling readiness table, dependency analysis.>

---

## Security Analysis

<Insert security-review output + SAST tool findings. Group by vulnerability type.
Include file:line citations for every finding.>

---

## Code Quality and Complexity

<Insert code-smell output + radon metrics.>

### Complexity Hotspots

| Rank | Function | File | CC Score | Nesting | Recommendation |
|------|----------|------|----------|---------|----------------|
| 1    |          |      |          |         |                |
| ...  |          |      |          |         |                |

---

## Error Handling

<Insert error handling audit findings, grouped by severity.>

---

## Test Coverage Gaps

<Insert test gap analysis. If coverage data available, include coverage percentage.
Otherwise note "structural heuristics only.">

---

## Technical Debt Inventory

<Insert tech-debt output. Include debt score if available.>

---

## Appendix: Tool Scan Results

<Summary table of each tool that ran:>

| Tool | Status | Findings | Notes |
|------|--------|----------|-------|
| ruff | OK | N violations | |
| bandit | OK | N findings | |
| radon | OK | N functions CC >= C | |
| ... | | | |

---

## Methodology

**Audit performed**: YYYY-MM-DD
**Total scan time**: <duration from Phase 1 start to Phase 5 completion>
**Phases executed**: 1 (Recon), 2 (Tool Scans), 3 (AI Reasoning), 4 (Custom Passes), 5 (Report)
**Tools used**: <list of tools that ran successfully>
**Skills used**: <list of skills that ran>
**Skipped**: <list of tools/skills that were skipped, with reason>
**Total findings**: N (X critical, Y high, Z medium, W low, V info)
**Deduplicated**: N findings merged from multiple sources
```

### Step 5.5: Verification checklist

Before presenting the report, verify quality:

1. **All template sections have content.** No empty placeholders, no "TODO" markers.
   If a section has no findings, write "No findings in this dimension" explicitly.
2. **Scorecard math is consistent.** Re-check each score against the rubric formula.
   Each CRITICAL finding cited in the Findings section should be reflected in its
   dimension's score deduction.
3. **Every CRITICAL finding appears in both places:** the Findings by Severity section
   AND the Executive Summary's "Top Critical Findings."
4. **Methodology section is complete:** lists all tools/skills that ran, which failed,
   which were skipped, and why.
5. **Report file exists and is >1KB.** If the write failed, retry once.
6. **No raw JSON or tool output leaked into the report body.** All findings should
   be in human-readable format.

If any check fails, fix it before presenting.

### Step 5.6: Present the report

After writing the report:

> "Audit complete. Report saved to `$OUTPUT_FILE`.
>
> **Health Score: X/100**
>
> Summary: <2-3 sentence overview of key findings>
>
> Would you like me to walk through any section in detail?"

### Step 5.7: Cleanup

Remove the temporary audit venv:

```bash
rm -rf "$AUDIT_VENV"
```
