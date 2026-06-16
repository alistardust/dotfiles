# Test Audit Gate: Design Spec

**Date:** 2026-06-15
**Status:** Draft
**Scope:** New `skill-conductor-test-audit` skill + modifications to quality layer and router

## Problem Statement

The current test-gate validates test quality (are existing tests well-written?) but
does not validate test strategy (are we testing the right things at the right
levels?). It also lacks verification/validation traceability: no mechanism confirms
that what was built matches what was specified, or that the test suite would catch
real bugs.

This gap means:
- Requirements can pass through to MR with zero test coverage
- The test pyramid can be inverted (all E2E, no units) without detection
- Specs can be written without testable acceptance criteria
- Plans can omit test tasks without consequence

## Solution

A new `skill-conductor-test-audit` skill that:
1. Validates test strategy (right tests at right levels)
2. Enforces requirements traceability (spec -> test -> pass)
3. Runs at every lifecycle phase with proportional depth
4. Blocks MR creation when gaps exist

## Key Design Decisions

### Blocking policy

All findings block, consistent with the zero-debt policy in skill-conductor-quality.
The quality layer intercepts all findings and sets `blocking: true` regardless of
severity. This applies at ALL phases (post-spec, post-plan, post-execution, mr).
Resolution options (fix, exempt, dispute, escalate) are handled by the quality layer,
not by this skill.

### Tier detection

Tier is NOT determined by this skill. The skill-conductor sets `complexity_tier`
during routing and passes it to the quality layer, which passes it to test-audit.
This skill receives tier as an input; it does not compute it.

### Phase detection

Phase is passed by the quality orchestrator via the `gate_phase` input field
(values: `post-spec`, `post-plan`, `post-execution`, `mr`). Test-audit switches
behavior based on this input.

### Requirement source precedence

When building the traceability matrix, use this precedence (first available wins):
1. Spec artifact (acceptance criteria section)
2. Plan artifact (deliverables or requirements section)
3. Commit messages (parse conventional commit bodies for stated intent)

If multiple exist, use the highest-precedence source only.

### Integration with test-gate

Test-gate runs first and produces a `test_gate_result` object containing:
- List of test files found and their locations
- Coverage metrics per file
- Assertion analysis results

Test-audit reads this result if available (avoids re-parsing). Falls back to
direct file analysis if test-gate was skipped (e.g., post-spec phase).

### Auto-fix budget

Test-audit itself is a READ-ONLY analysis gate. It does not fix tests or generate
code. When findings are produced, the quality layer's resolution loop handles them
(user fixes manually, or a fix agent is dispatched by the quality layer if the
finding is marked `auto_fixable: true`). The budget column in proportionality refers
to the quality layer's iteration count, not this skill's behavior.

## Architecture

### Gate Ordering (inside quality layer)

```
post-spec / post-plan:
  review-gate (existing) + test-audit (testability/strategy, lightweight)

post-execution:
  test-gate (quality) -> test-audit (strategy) -> review-gate (code review)

mr:
  test-gate (quality) -> test-audit (strategy + traceability) -> review-gate
```

Test-gate and test-audit are sequential (both read test files, no conflicts).
Review-gate runs last (its fix agent mutates source files).

### Phase-Aware Behavior

| Phase | Test-audit scope | Dimensions active |
|-------|-----------------|-------------------|
| `post-spec` | Testability review of spec | Acceptance criteria verifiability, test level declaration |
| `post-plan` | Test strategy validation of plan | Paired test tasks, pyramid balance, boundary identification |
| `post-execution` | Full audit of implemented tests | All 8 dimensions (proportional to tier) |
| `mr` | Full audit + traceability matrix | All 8 dimensions + requirement-to-test mapping |

## Dimensions

### 1. Validation (Requirements Traceability) [moderate+]

**Question:** Did we build what was specified?

**At spec time:** Each requirement/acceptance criterion must be:
- Phrased as a verifiable statement (not "should feel fast" but "P95 < 200ms")
- Tagged with intended test level (unit/integration/E2E/smoke)
- Defined for both success AND failure states

**At execution/MR time:** For each requirement in the spec (or plan, or commit
message if no spec):
- Map to test(s) that exercise it
- BLOCKING if a requirement has ZERO test coverage
- At MR: produce traceability matrix

**Traceability matrix format:**
```
REQUIREMENT                     | TEST(S)               | LEVEL  | STATUS
User can reset password         | test_reset_flow       | E2E    | PASS
Token expires after 1hr         | test_token_expiry     | unit   | PASS
Invalid token returns 401       | (NONE)                | -      | GAP
```

Any GAP in the matrix is a blocking finding.

### 2. Verification (Correctness) [moderate+]

**Question:** Is it bug-free? Does behavior match intent?

**Evaluation:**
- For each changed function: trace inputs through logic, identify assertions that
  prove correctness (not just exercise the code)
- Check for property-based thinking: do tests verify invariants, not just examples?
- Look for assertion gaps: code paths that execute but whose output is never checked

**Pass/fail criteria:**
- FAIL if any changed function has execution paths with NO assertion covering the output
- FAIL if error paths are exercised but error type/message is not asserted
- PASS if every changed code path has at least one assertion that checks output value

**Positive signals:**
- Tests verify return values against expected computed results
- Edge cases map to documented invariants
- Error paths produce specific, asserted error types/messages

### 3. Test Pyramid [moderate+]

**Question:** Do we have the right test types at the right levels?

**Classification:** Categorize all tests in changeset:
- **Unit:** Tests a single function/class in isolation, mocks dependencies
- **Integration:** Tests interaction between 2+ real components
- **E2E:** Tests a full user flow through the actual system
- **Smoke:** Minimal sanity check that core paths are not broken

**Evaluation:**
- Feature changes should be mostly unit + some integration + selective E2E
- Flag inversions: all E2E with no units (fragile, slow)
- Flag inversions: all units with no integration (gap at boundaries)
- At spec/plan time: validate declared strategy is pyramidal

**Pass/fail criteria:**
- FAIL if E2E tests comprise >50% of new tests AND unit tests = 0
- FAIL if behavior-changing code has zero unit tests
- FAIL if service boundary changes have zero integration tests
- PASS if test distribution is reasonable for the change type
- Advisory (not blocking at moderate): if ratio is suboptimal but not inverted

**Proportionality rules:**
- Small features: unit tests sufficient, integration nice-to-have
- Service boundary changes: integration tests mandatory
- Critical user flows: at least one E2E or smoke test

### 4. Mutation Signal [substantial only]

**Question:** Would the tests catch a real bug?

**Method (AI heuristic, not mutation framework):**

For each conditional in critical logic paths:
```
if (X op Y) { ... }
  Mutation 1: negate condition -> if !(X op Y)
  Mutation 2: boundary shift -> if (X op+1 Y) or (X op-1 Y)
  Mutation 3: swap operator -> < becomes <=, == becomes !=, && becomes ||
```

For each mutation, reason: would an existing test assertion fail?

**Pass/fail criteria:**
- FAIL if a critical logic path has a mutation where NO test would detect the change
- PASS if at least one test assertion would fail for each hypothetical mutation
- Only evaluate critical paths (business logic, security checks, data transforms)
- Skip boilerplate, config, and glue code

**Scope:** Only critical paths (business logic, security checks, data
transformations). Skip boilerplate, config, and glue code.

**This is reasoning about test effectiveness, not running pitest/mutmut.**

### 5. Contract Testing [substantial only]

**Question:** Are cross-service/API boundaries tested?

**API surface definition:**
- External API surface: HTTP/gRPC endpoints, pub/sub topics, event schemas,
  CLI commands documented for external use
- NOT external: internal function calls, private modules, dev-only endpoints

**Triggers:**
- Changeset modifies an API endpoint, response schema, or event payload
- Changeset modifies a client that calls another service
- Changeset changes a shared interface/protocol definition

**Evaluation:**
- Is there a consumer test or contract test for the boundary?
- If not: is there an integration test covering the interaction?
- If neither: blocking finding (boundary changes without boundary tests)

**Pass/fail criteria:**
- FAIL if a public API endpoint is modified with no test exercising the boundary
- FAIL if a shared schema/event payload changes with no consumer-side test
- PASS if boundary has integration or contract test coverage
- NOT APPLICABLE: single-service repos with no external API surface (returns PASSED)

### 6. Maintainability [substantial only]

**Question:** Are tests coupled to behavior or implementation details?

**Red flags (implementation coupling, concrete anti-patterns to detect):**
- Asserting mock call counts (`verify(mock).called(3)`, `assert_called_once_with`)
- Asserting private method names or internal state
- Asserting CSS selectors that encode DOM structure (`.div > .span.className`)
- Asserting exact log messages (implementation detail of error handling)
- Tests that directly test private/unexported functions

**Green signals (behavior coupling):**
- Tests assert observable outputs (return values, HTTP responses, rendered text)
- Tests assert state transitions (before/after)
- Tests use public API surface only

**Pass/fail criteria:**
- FAIL if >30% of test assertions in changeset target implementation details
- PASS if tests primarily assert observable behavior
- Advisory: flag individual implementation-coupled assertions even when ratio is below threshold

### 7. Performance Awareness [substantial only]

**Question:** Are hot paths benchmarked or load-aware?

**Triggers (hot path detection):**
- Loop over unbounded collection
- Database query inside a loop
- HTTP handler or queue consumer
- Code marked with performance-related comments

**Evaluation:**
- Is there a benchmark, performance test, or performance assertion?
- At minimum: a TODO/ticket acknowledging performance implications?
- Not requiring load tests for every change; awareness for hot paths only

**Not applicable:** Changes that don't touch hot paths.

### 8. Determinism [moderate+]

**Question:** Are tests free from flakiness risks?

**Detection method:** Regex patterns per language, applied to test files only
(not implementation code). Flag lines inside test functions/methods.

**Red flags (with detection patterns):**
- Time dependency: `time.now()`, `Date.now()`, `datetime.now()`, `Instant.now()`
  in test without corresponding mock/freeze
- Network dependency: `fetch(`, `requests.get(`, `http.Get(` without mock/fixture/VCR
- Shared filesystem: write to fixed path without cleanup in teardown
- Timing dependency: `sleep(`, `time.sleep(`, `setTimeout(`, `Thread.sleep(`
- Order dependency: tests that pass individually but fail in batch
- Randomness: `random.`, `Math.random()` without seed

**Pass/fail criteria:**
- HIGH finding: network/time calls without mock (will flake in CI)
- MEDIUM finding: sleep in test (slow and timing-dependent)
- HIGH finding: shared state without cleanup (order-dependent)
- PASS if no flakiness signals detected in test files

## Spec/Plan Phase Integration

### At post-spec (testability review)

Lightweight pass; no code exists yet. Validates that the spec is born testable:

```
for each requirement/acceptance_criterion in spec:
  verifiable = is_phrased_as_verifiable(criterion)
  level_declared = has_test_level_tag(criterion)
  failure_defined = has_failure_state(criterion)

  if not verifiable:
    finding(MEDIUM, "Requirement not testable: <criterion>")
  if not level_declared:
    finding(LOW, "No test level declared for: <criterion>")
  if not failure_defined:
    finding(LOW, "No failure state defined for: <criterion>")
```

**Test level tags:** Requirements should declare intended level using bracketed
notation: `[unit]`, `[integration]`, `[e2e]`, `[smoke]`.
Example: "User can reset password [e2e]", "Token expires after 1hr [unit]"

### At post-plan (test strategy validation)

Validates that the plan includes test strategy:

```
for each implementation_task in plan:
  if changes_behavior(task) and not task.is_test_exempt:
    if not has_paired_test_task(task):
      finding(MEDIUM, "Implementation task without test task: <task>")

all_test_levels = collect_test_levels(plan.test_tasks)
if all_same_level(all_test_levels):
  finding(MEDIUM, "Pyramid violation: all tests at <level> level")

boundaries = identify_integration_boundaries(plan)
for boundary in boundaries:
  if not has_integration_test_planned(boundary):
    finding(HIGH, "Integration boundary without test: <boundary>")
```

## Proportionality

| Tier | Dimensions active | Auto-fix budget |
|------|-------------------|-----------------|
| trivial | Gate returns PASSED (no evaluation) | 0 |
| moderate | Validation, Verification, Pyramid, Determinism | 2 |
| substantial | All 8 dimensions | 5 |

Work type modifiers:
- `feature`: all dimensions at tier level
- `bugfix`: Verification is MANDATORY regardless of tier
- `refactor`: Verification ensures test suite still passes (no accidental behavior changes); Pyramid ratio must not worsen (ratchet)
- `config`: Gate skipped unless test files were also changed

## Token Efficiency

Target: under 450 lines for the skill file. Strategies:
- Share test file discovery with test-gate via `test_gate_result` handoff (avoid re-parsing)
- Traceability matrix generation is delegated to a fast-tier subagent if changeset has >20 requirements
- Dimension evaluation logic is described as intent (AI reasoning), not literal code (no pseudocode blocks for simple heuristics)

## Files to Create/Modify

| File | Action | Summary |
|------|--------|---------|
| `skills/skill-conductor-test-audit/SKILL.md` | **CREATE** | New skill: 8 dimensions, phase-aware audit |
| `skills/skill-conductor-quality/SKILL.md` | **MODIFY** | Add test-audit dispatch between test-gate and review-gate |
| `skills/skill-conductor/SKILL.md` | **MODIFY** | Note MR gate is mandatory; update integration diagram |

## Acceptance Criteria

1. `post-spec` gate flags untestable requirements
2. `post-plan` gate flags missing test tasks and pyramid violations
3. `post-execution` gate runs full audit proportional to tier
4. `mr` gate produces traceability matrix; gaps block
5. All 8 dimensions have clear pass/fail criteria
6. Proportionality rules prevent over-enforcement on trivial changes
7. Phase-aware behavior (spec vs plan vs execution vs MR)
8. Zero new hardcoded model versions
9. All text is ASCII-safe
10. Skill is under 450 lines (token efficiency)

## Non-Goals

- Running actual mutation testing frameworks (pitest, mutmut)
- Running actual contract testing frameworks (Pact)
- Generating load tests or benchmarks
- Modifying spec/plan templates (those skills own their own format)
- Retroactively auditing existing test suites (ratchet handles legacy)

## Risks

- **False positives on "testability"**: AI judgment on whether a requirement is
  "verifiable" may be subjective. Mitigation: dispute mechanism exists in quality layer.
- **Traceability matrix on large changesets**: May be noisy for 50+ requirement changes.
  Mitigation: group by file/feature, show summary not every row.
- **Contract testing detection**: Not all repos have clear service boundaries.
  Mitigation: "Not applicable" is a valid dimension result; it does not produce findings.
