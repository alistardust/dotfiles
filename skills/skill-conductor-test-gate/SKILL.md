---
name: skill-conductor-test-gate
description: >
  Test quality gate for the skill conductor. Validates coverage, assertion
  strength, boundary cases, independence, and regression tests after execution
  completes. Blocks progression on any dimension failure. Runs after TDD/execution,
  before review-gate.
---

# Test Quality Gate

You are a test quality gate. The skill-conductor invoked you after execution
completed (post-TDD or post-implementation). Validate that the test suite meets
quality thresholds across five dimensions. Block progression if any dimension
fails. You evaluate and fix; you do not write the feature code.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `changeset_scope` | Yes | Files changed during execution (source + test files) |
| `complexity_tier` | Yes | `trivial`, `moderate`, or `substantial` |
| `work_type` | Yes | `feature`, `bugfix`, `refactor`, or `config` |
| `base_ref` | Yes | Branch/commit before execution started |
| `test_command` | No | Override for test runner (auto-detected if absent) |
| `coverage_command` | No | Override for coverage tool (auto-detected if absent) |
| `overrides` | No | Threshold overrides (see Configuration) |

Validation:
- If `changeset_scope` is empty: reject "No files changed; nothing to gate."
- If `work_type` is `config` and no test files in changeset: return PASSED with
  advisory "Config-only change; test gate not applicable."

## Proportionality Rules

Gate depth scales with complexity and work type:

| Tier | Dimensions evaluated | Auto-fix budget | Coverage required |
|------|---------------------|----------------|-------------------|
| **trivial** | Gate returns PASSED (no evaluation) | 0 | N/A |
| **moderate** | Coverage + Assertions + Boundaries | 2 iterations | Line: 85%, Branch: 75% |
| **substantial** | All 5 dimensions | 5 iterations | Line: 90%, Branch: 80% |

Work type modifiers:

| Work type | Additional rules |
|-----------|-----------------|
| `feature` | All dimensions at tier level |
| `bugfix` | Regression dimension is MANDATORY regardless of tier |
| `refactor` | Coverage must not decrease from baseline (ratchet rule) |
| `config` | Gate skipped unless test files were also changed |

## Dimension Definitions

### 1. Coverage (all tiers)

**What:** Line and branch coverage on changed source files (not test files).

**How to measure:**
```
1. Identify source files: changeset_scope minus test files
2. Run coverage tool with scope limited to changed files
3. Parse coverage report for line% and branch%
4. Compare against thresholds (tier-adjusted)
5. If baseline exists (.coverage-baseline or CI artifact): verify no regression
```

**Auto-detection for test/coverage commands:**
```
detect_test_runner():
  if package.json exists and has "test" script: "npm test" or "npx jest"
  if pyproject.toml or setup.cfg: "pytest"
  if Cargo.toml: "cargo test"
  if go.mod: "go test ./..."
  if Makefile has "test" target: "make test"
  else: ask_user("No test runner detected. Provide command or skip.")

detect_coverage_tool():
  if jest: "npx jest --coverage --collectCoverageFrom='<changed_files>'"
  if pytest: "pytest --cov=<packages> --cov-branch --cov-report=json"
  if cargo: "cargo tarpaulin --files <changed>"
  if go: "go test -coverprofile=coverage.out ./..."
  else: ask_user or skip with advisory
```

**Pass criteria:** Both line AND branch coverage meet tier threshold on changed
files. If no coverage tool available, escalate as advisory (do not block on
tooling absence, but note it as tech debt).

**Ratchet rule (refactors):** For `work_type=refactor`, coverage on changed files
must be >= pre-change coverage. Compute delta; any decrease is blocking.

### 2. Assertion Quality (moderate+)

**What:** Tests assert meaningful behavior, not just "it runs without crashing."

**How to evaluate (AI-driven analysis of test files):**

Scan each test file in `changeset_scope` for these anti-patterns:

| Anti-pattern | Detection | Severity |
|--------------|-----------|----------|
| No assertions | Test function body has no assert/expect/should | CRITICAL |
| Tautological assertion | `assert True`, `expect(1).toBe(1)`, `assert x == x` | HIGH |
| Only checks type/existence | `assert result is not None` without value check | MEDIUM |
| Overly broad assertion | `assert len(result) > 0` without content validation | MEDIUM |
| Only happy path | All test names are positive; no error/edge tests in file | HIGH |
| Snapshot-only without semantic | Only snapshot tests, no behavioral assertions | MEDIUM |

**Pass criteria:** Zero CRITICAL or HIGH anti-patterns. MEDIUM anti-patterns are
blocking at `substantial` tier, advisory at `moderate`.

**Positive signals (strengthen pass confidence):**
- Assertions check return values against expected constants
- Error messages are asserted (not just error type)
- State transitions are verified (before/after)
- Mock interactions are verified (called with correct args)

### 3. Boundary Cases (moderate+)

**What:** Tests cover edge cases, not just the happy path.

**How to evaluate:**

For each public function/method in changed source files, check if test suite covers:

| Boundary category | Examples | Required at |
|-------------------|----------|-------------|
| Empty/zero | Empty string, empty list, 0, None/null | moderate+ |
| Error/exception | Invalid input, missing resource, timeout | moderate+ |
| Boundary values | Off-by-one, max int, empty vs whitespace | substantial |
| Concurrent/async | Race conditions, deadlocks (if applicable) | substantial |
| Permission/auth | Unauthorized, expired token (if applicable) | substantial |

**Evaluation method:**
```
for each changed_source_file:
  functions = extract_public_functions(file)
  for each function:
    params = extract_parameters(function)
    test_names = find_tests_targeting(function)
    test_bodies = read_test_bodies(test_names)

    score = 0
    if has_empty_input_test(test_bodies, params): score += 1
    if has_error_case_test(test_bodies): score += 1
    if has_boundary_value_test(test_bodies, params): score += 1  # substantial only
    if has_concurrent_test(test_bodies) or not_applicable: score += 1  # substantial only

    required = tier_requirement(complexity_tier)
    if score < required: add_finding(function, missing_categories)
```

**Pass criteria:**
- moderate: Each public function has at least empty + error coverage
- substantial: Each public function has at least 3 of 4 categories (or documented N/A)

### 4. Test Independence (substantial only)

**What:** Tests do not depend on execution order or shared mutable state.

**How to evaluate:**

| Signal | Detection method | Severity |
|--------|-----------------|----------|
| Shared mutable state | Global/module-level variables mutated in tests | HIGH |
| Missing cleanup | setUp without tearDown, beforeAll without afterAll modifying state | HIGH |
| Order dependency | Test references output of another test (variable, file) | CRITICAL |
| Shared fixtures mutated | Fixture returns mutable object AND tests mutate it | MEDIUM |
| Database state leaking | Tests insert without cleanup or transaction rollback | HIGH |

**Evaluation method:** Static analysis of test files. Look for:
- Module-level assignments that are not constants
- Fixtures/setup methods that modify external state without cleanup
- Tests that read files written by other tests
- Tests that share a database connection without isolation

**Pass criteria:** Zero CRITICAL or HIGH independence violations.

### 5. Regression Coverage (bugfix only, all tiers)

**What:** Bug fixes include a test that fails against the bug and passes after the fix.

**How to evaluate:**
```
1. Identify the fix commit(s) in changeset
2. Find test files added or modified in same changeset
3. For each new/modified test:
   a. Stash the fix (git stash or checkout base_ref for target file)
   b. Run ONLY the new test against the pre-fix code
   c. Verify it FAILS (reproduces the bug)
   d. Restore the fix
   e. Run the test again; verify it PASSES
4. If no test reproduces the bug: BLOCKING finding
```

**Pass criteria:** At least one test in the changeset demonstrably fails on the
bug and passes on the fix. If the bug cannot be reproduced in test (infrastructure
dependency, timing), accept a documented justification with ticket reference.

**Shortcut for trivial bugs:** If the fix is a one-line change and the test
clearly targets that line (covers the exact branch), skip the stash/checkout
verification and pass on static analysis alone.

## Gate Protocol

```
test_gate_triggered(gate_config):
  if gate_config.work_type == "config" and no_test_files_in(gate_config.changeset_scope):
    return PASSED  # advisory: config-only, no test gate needed

  # --- Proportionality ---
  dimensions = select_dimensions(gate_config.complexity_tier, gate_config.work_type)
  budget = select_budget(gate_config.complexity_tier)
  thresholds = merge_thresholds(defaults_for_tier, gate_config.overrides)

  all_findings = []
  iteration = 0

  loop:
    if iteration >= budget:
      return ESCALATED_BLOCKING(all_findings)

    # --- Evaluate each applicable dimension ---
    findings = []

    if "coverage" in dimensions:
      cov_result = evaluate_coverage(gate_config, thresholds)
      findings.extend(cov_result.findings)

    if "assertions" in dimensions:
      assert_result = evaluate_assertion_quality(gate_config.changeset_scope)
      findings.extend(assert_result.findings)

    if "boundaries" in dimensions:
      boundary_result = evaluate_boundary_coverage(gate_config)
      findings.extend(boundary_result.findings)

    if "independence" in dimensions:
      indep_result = evaluate_test_independence(gate_config.changeset_scope)
      findings.extend(indep_result.findings)

    if "regression" in dimensions:
      reg_result = evaluate_regression_coverage(gate_config)
      findings.extend(reg_result.findings)

    # --- Classify findings ---
    blocking = [f for f in findings if f.severity in ("CRITICAL", "HIGH")
                or (f.severity == "MEDIUM" and gate_config.complexity_tier == "substantial")]
    advisory = [f for f in findings if f not in blocking]

    if len(blocking) == 0:
      report_advisory(advisory)
      return PASSED

    # --- Attempt auto-fix ---
    fixable = [f for f in blocking if f.auto_fixable]
    unfixable = [f for f in blocking if not f.auto_fixable]

    if len(fixable) == 0:
      # All blocking findings require human judgment
      return ESCALATED_BLOCKING(blocking)

    # Apply fixes for fixable findings
    fix_agent = dispatch_test_fix(fixable, gate_config)
    fix_agent.apply_fixes()
    iteration += 1

    # Re-run tests to confirm fixes don't break anything
    test_result = run_tests(gate_config.test_command)
    if test_result.failed:
      revert_fixes()
      return ESCALATED_BLOCKING("Auto-fix broke existing tests. Manual fix required.")

    # Loop back to re-evaluate (fixes may have addressed multiple findings)

  report_advisory(all_findings)
  return PASSED
```

## Findings Schema

Test gate findings follow the same structure as review-gate findings for
compatibility with the quality invariants layer:

```yaml
findings:
  - reviewer: "test-gate"
    dimension: "coverage"        # coverage | assertions | boundaries | independence | regression
    severity: "HIGH"             # CRITICAL | HIGH | MEDIUM | LOW
    file: "src/auth.py"
    unit: "authenticate()"
    summary: "Branch coverage 62% (threshold: 75%)"
    detail: "Missing coverage on error branch lines 45-52 (invalid token path)"
    auto_fixable: true
    fix_hint: "Add test for invalid JWT token input"
    blocking: true
```

## Auto-Fix Capabilities

The test gate can auto-fix specific finding types:

| Finding type | Auto-fix approach | Model |
|--------------|-------------------|-------|
| Missing boundary test | Generate test from function signature + detected gap | `claude-sonnet-4.5` |
| No assertions in test | Add meaningful assertions based on function contract | `claude-sonnet-4.5` |
| Tautological assertion | Replace with meaningful value assertion | `claude-haiku-4.5` |
| Missing regression test | Generate failing-then-passing test from diff | `claude-sonnet-4.5` |
| Low coverage (single branch) | Generate test targeting uncovered branch | `claude-sonnet-4.5` |

**Cannot auto-fix (escalate immediately):**
- Test architecture issues (shared mutable state)
- Order-dependent tests (requires redesign)
- Coverage gaps requiring mocks/infrastructure setup
- Tests that need domain knowledge to write meaningful assertions
- Coverage tool not available or not configured

### Fix safety

- Auto-generated tests are run immediately after creation
- If a generated test fails unexpectedly (not a regression test): revert and escalate
- Generated tests are scoped to `changeset_scope` only (no new test files for unchanged code)
- Fix agent prompt: "Write a focused test for [specific gap]. Follow existing test
  patterns in this file. Do not modify source code. Do not modify other tests."

## Gate Outcomes

| Outcome | Meaning | Workflow effect |
|---------|---------|----------------|
| `PASSED` | All dimensions meet thresholds | Proceed to review-gate |
| `ESCALATED_BLOCKING` | Unfixable findings or budget exhausted | Workflow STOPS; user must resolve |
| `SKIPPED` | Config-only change or user override | Proceed; logged |

## Integration Points

### Where this gate fires in the workflow

```
Execution layer completes (TDD/implementing/executing-plans)
  |
  v
[test-gate] <-- YOU ARE HERE
  |
  v (if PASSED or SKIPPED)
Review gate (skill-conductor-review-gate)
  |
  v (if PASSED)
Verification / Shipping
```

### Conductor integration

The `skill-conductor` invokes this gate AFTER execution skills complete and BEFORE
triggering `skill-conductor-review-gate`. The conductor passes:

```
Test gate requested.
  changeset_scope: [files from git diff --name-only base..HEAD]
  complexity_tier: <from conductor>
  work_type: <detected from context: feature/bugfix/refactor/config>
  base_ref: <branch point>
```

### Work type detection

The conductor detects `work_type` from context:
- `bugfix`: commit messages contain "fix", "bug", "patch"; branch starts with "fix/" or "hotfix/"
- `refactor`: commit messages contain "refactor", "restructure"; no new public API
- `config`: only config/yaml/toml/json/env files changed; no source code
- `feature`: default (new behavior, new files, new API surface)

## Configuration

Override syntax (passed via `overrides` input):

```yaml
coverage_line_threshold: 90
coverage_branch_threshold: 80
assertion_severity_override: "advisory"  # downgrade assertion findings to advisory
skip_dimensions: ["independence"]        # skip specific dimensions
regression_verify_method: "static"       # skip stash/checkout, use static analysis only
```

| Key | Effect | Valid values |
|-----|--------|--------------|
| `coverage_line_threshold` | Override line coverage % | 0-100 |
| `coverage_branch_threshold` | Override branch coverage % | 0-100 |
| `skip_dimensions` | Exclude dimensions from evaluation | Array of dimension names |
| `assertion_severity_override` | Treat assertion findings as advisory | `"advisory"` |
| `regression_verify_method` | How to verify regression tests | `"runtime"` (default), `"static"` |
| `auto_fix` | Enable/disable auto-fix | `true` (default), `false` |

**Cannot override:** The regression dimension for bugfixes. It is always blocking.

## Instrumentation

After each gate run, report:
```
Test gate: [outcome] | tier: [complexity] | type: [work_type] | dims: [N]/[total] | blocking: [N] | fixed: [N] | iters: [N]/[budget] | coverage: [line%/branch%] | time: [Xm Ys]
```

## Escalation Protocol

When findings cannot be auto-fixed, present to user:

```
## Test Quality Gate: BLOCKED

### Findings requiring attention:

1. [DIMENSION] [SEVERITY] [file:function]
   Issue: <summary>
   Suggested fix: <fix_hint>

### Options:
1. Fix and re-run: Address findings, then re-invoke test gate
2. Override with justification: Provide ticket ID and reason
3. Abort: Return to execution phase
```

Option 2 (override) requires a ticket reference. The finding is logged as
acknowledged debt in the quality baseline (see skill-conductor-quality).
