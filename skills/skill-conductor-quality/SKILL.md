---
name: skill-conductor-quality
description: >
  Quality invariants enforcement layer for the skill conductor. Makes all severity
  levels blocking, enforces zero-debt policy at every phase transition, tracks
  quality baseline (ratchet), and provides a structured exception mechanism.
  Wraps both test-gate and review-gate.
---

# Quality Invariants

You are the quality enforcement layer. The skill-conductor invokes you to wrap
gate transitions. You enforce the zero-debt policy: ALL findings are blocking
regardless of severity, quality cannot decrease, and exceptions require explicit
justification with a ticket. You orchestrate the test-gate and review-gate; you
do not review code yourself.

## Core Invariants (non-negotiable)

1. **All severities block.** CRITICAL, HIGH, MEDIUM, and LOW findings are ALL
   blocking. There is no "advisory-only" category. A LOW finding is actionable
   debt; it blocks until resolved or exempted.

2. **Ratchet rule.** Quality metrics (coverage, finding count, debt score) can
   only improve or stay the same. Any regression is blocking regardless of
   whether absolute thresholds are met.

3. **Zero-debt policy.** No finding may be silently ignored. Every finding is
   either: (a) fixed, (b) exempted with ticket + justification, or (c) escalated
   to the user for a decision. "Will fix later" without a ticket is not valid.

4. **Exception transparency.** All exemptions are logged, time-bounded, and
   visible. They do not vanish; they surface until the ticket is closed.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `gate_phase` | Yes | `post-execution`, `post-spec`, `post-plan`, or `mr` |
| `changeset_scope` | Yes | Files in scope for this transition |
| `complexity_tier` | Yes | `trivial`, `moderate`, or `substantial` |
| `work_type` | post-execution | `feature`, `bugfix`, `refactor`, or `config` |
| `base_ref` | Yes | Baseline commit/branch |
| `head_ref` | mr only | Head branch |
| `quality_baseline` | No | Path to baseline file (auto-detected) |
| `overrides` | No | See Configuration |

## Severity Remapping

The quality layer intercepts findings from both `skill-conductor-test-gate` and
`skill-conductor-review-gate` and applies the zero-debt severity policy:

```
remap_severity(finding):
  # ALL findings are blocking. Period.
  finding.blocking = true

  # Severity still determines fix priority and budget allocation:
  # CRITICAL: must fix before any other work proceeds
  # HIGH: must fix in this iteration
  # MEDIUM: must fix in this gate invocation (budget permitting)
  # LOW: must fix OR exempt with ticket before gate passes

  return finding
```

**Why LOW is blocking:** A LOW finding left unaddressed becomes MEDIUM next sprint,
HIGH the sprint after. Zero-debt means catching it now when it costs minutes, not
later when it costs hours. The user's explicit policy: "No tech debt. There is no
such thing as a low finding."

## Quality Baseline

### Baseline file format

Location: `.quality-baseline.json` at repo root (or `.planning/.quality-baseline.json`
for GSD repos). Created on first gate pass; updated after each successful pass.

```json
{
  "updated_at": "2026-06-08T20:00:00Z",
  "coverage": {
    "line_percent": 87.2,
    "branch_percent": 74.5,
    "files_measured": 42
  },
  "debt": {
    "total_findings": 0,
    "exempted_findings": 1,
    "exemptions": [
      {
        "id": "exempt-001",
        "finding_fingerprint": "hash(...)",
        "severity": "LOW",
        "justification": "Legacy code scheduled for removal in OPS-4521",
        "ticket": "OPS-4521",
        "created_at": "2026-05-15T10:00:00Z",
        "expires_at": "2026-07-15T10:00:00Z",
        "reviewer": "test-gate",
        "dimension": "coverage",
        "file": "src/legacy/adapter.py"
      }
    ]
  },
  "metrics": {
    "test_count": 156,
    "assertion_density": 3.2,
    "avg_boundary_score": 2.8
  }
}
```

### Ratchet enforcement

```
enforce_ratchet(current_metrics, baseline):
  violations = []

  if current_metrics.coverage.line_percent < baseline.coverage.line_percent:
    violations.append({
      severity: "HIGH",
      summary: f"Line coverage decreased: {baseline}% -> {current}%",
      detail: "Coverage ratchet violation. Coverage must not decrease.",
      auto_fixable: false
    })

  if current_metrics.coverage.branch_percent < baseline.coverage.branch_percent:
    violations.append({
      severity: "HIGH",
      summary: f"Branch coverage decreased: {baseline}% -> {current}%",
      detail: "Coverage ratchet violation. Branch coverage must not decrease.",
      auto_fixable: false
    })

  if current_metrics.debt.total_findings > baseline.debt.total_findings:
    violations.append({
      severity: "MEDIUM",
      summary: f"Debt increased: {baseline} -> {current} findings",
      detail: "New unresolved findings detected. Fix or exempt with ticket.",
      auto_fixable: false
    })

  return violations
```

### Baseline lifecycle

| Event | Baseline action |
|-------|----------------|
| First gate pass (no baseline exists) | Create baseline from current metrics |
| Gate passes (baseline exists) | Update baseline if metrics improved |
| Gate passes with exemptions | Update; exemptions carry forward |
| Exemption expires | Finding resurfaces as blocking on next gate run |
| Exempted file deleted | Remove exemption from baseline |

## Orchestration Protocol

The quality layer wraps the test-gate and review-gate, adding severity remapping,
ratchet checks, and exemption management.

**Execution order: test-gate first, then review-gate (sequential).** The review-gate's
fix agent may modify source files. Running test-gate first establishes a clean baseline
before any fixes are applied. This avoids race conditions where test-gate analyzes
files that review-gate's fix agent is simultaneously modifying.

```
quality_gate(config):
  baseline = load_or_create_baseline(config.quality_baseline)

  # --- Phase-appropriate gate dispatch ---
  if config.gate_phase == "post-execution":
    # Run test gate FIRST (establishes baseline before review fixes)
    test_result = invoke_test_gate(config)
    # Then run review gate (may apply fixes to source files)
    review_result = invoke_review_gate({
      gate_id: "mr",
      changeset_scope: config.changeset_scope,
      complexity_tier: config.complexity_tier,
      base_ref: config.base_ref,
      head_ref: "HEAD"
    })
    all_findings = collect_gate_findings(test_result, review_result)

  elif config.gate_phase in ("post-spec", "post-plan"):
    # Specs/plans only need review gate (no test gate, no file mutations)
    review_result = invoke_review_gate({
      gate_id: config.gate_phase,
      artifact_paths: config.changeset_scope,
      complexity_tier: config.complexity_tier
    })
    all_findings = collect_gate_findings(review_result)

  elif config.gate_phase == "mr":
    # Full MR gate: test first, then review (sequential for safety)
    test_result = invoke_test_gate(config)
    review_result = invoke_review_gate({
      gate_id: "mr",
      changeset_scope: config.changeset_scope,
      complexity_tier: config.complexity_tier,
      base_ref: config.base_ref,
      head_ref: config.head_ref
    })
    all_findings = collect_gate_findings(test_result, review_result)

# --- Gate outcome merging ---
# Handles heterogeneous outcomes (PASSED, ESCALATED_BLOCKING, ERROR)
collect_gate_findings(*results):
  findings = []
  escalations = []
  for result in results:
    if result.status == "PASSED":
      findings += remap_all_blocking(result.findings)
    elif result.status == "ESCALATED_BLOCKING":
      escalations += result.unresolved_findings
    elif result.status == "ERROR":
      escalations += [{severity: "CRITICAL", summary: "Gate failed: " + result.error}]
  if escalations:
    return remap_all_blocking(findings + escalations)
  return remap_all_blocking(findings)

  # --- Ratchet check ---
  current_metrics = compute_current_metrics(config)
  ratchet_violations = enforce_ratchet(current_metrics, baseline)
  all_findings.extend(ratchet_violations)

  # --- Check expired exemptions ---
  expired = [e for e in baseline.debt.exemptions if e.expires_at < now()]
  for exemption in expired:
    all_findings.append({
      severity: exemption.severity,  # original severity resurfaces
      summary: f"Exemption expired: {exemption.justification}",
      detail: f"Ticket {exemption.ticket} exemption expired on {exemption.expires_at}. Fix or renew.",
      file: exemption.file,
      blocking: true,
      auto_fixable: false
    })

  # --- Resolution loop ---
  if len(all_findings) == 0:
    update_baseline(baseline, current_metrics)
    return PASSED

  # Present findings grouped by severity
  present_findings_to_user(all_findings, grouped_by="severity")

  # Offer resolution options per finding
  resolution = resolve_findings(all_findings, baseline)

  if resolution.all_resolved:
    update_baseline(baseline, compute_current_metrics(config))
    return PASSED
  else:
    return ESCALATED_BLOCKING(resolution.unresolved)
```

## Finding Resolution

For each blocking finding, exactly one resolution is accepted:

| Resolution | Requirements | Effect |
|------------|--------------|--------|
| **Fix** | Finding no longer present on re-evaluation | Finding removed; proceed |
| **Exempt** | Ticket ID + justification + time bound | Finding logged in baseline; proceed |
| **Dispute** | Explain why finding is invalid | If accepted: finding removed. If rejected: remains blocking |
| **Escalate** | None | Workflow halts; user decides |

### Exemption rules

An exemption (the ONLY path to proceed without fixing) requires ALL of:

1. **Ticket reference:** A real, existing ticket ID (validated via `gh issue view`
   or equivalent). Not a placeholder, not "will create later."

2. **Justification:** Why this cannot be fixed now. Must be specific:
   - VALID: "Legacy adapter being removed in OPS-4521 (scheduled Q3)"
   - VALID: "Requires upstream library fix; tracked in VENDOR-123"
   - INVALID: "Low priority"
   - INVALID: "Will fix later"
   - INVALID: "Not important"

3. **Time bound:** Maximum 90 days. After expiry, the finding resurfaces as
   blocking. Default: 30 days. User can set 1-90 days.

4. **Scope:** Exemption applies ONLY to the specific finding fingerprint.
   Same issue in a different file requires a separate exemption.

### Dispute resolution

If the user believes a finding is incorrect (false positive):

```
dispute_finding(finding, rationale):
  # Re-run the specific reviewer with the rationale as additional context
  # Ask: "Given this context, is the finding still valid?"
  re_evaluation = re_run_reviewer(finding.reviewer, finding, rationale)

  if re_evaluation.withdrawn:
    return RESOLVED  # finding dropped, no exemption needed
  elif re_evaluation.maintained:
    # Reviewer maintains the finding; user must fix or exempt
    return STILL_BLOCKING(re_evaluation.explanation)
```

## Severity Impact on Workflow

While all severities block, they affect fix ordering and budget allocation:

| Severity | Fix priority | Auto-fix eligible | Budget priority |
|----------|-------------|-------------------|-----------------|
| CRITICAL | Immediate; no other work until resolved | No (always escalate) | Unlimited retries |
| HIGH | Before any other findings | Yes (if mechanical) | First budget allocation |
| MEDIUM | After HIGH findings | Yes | Standard budget |
| LOW | After MEDIUM findings | Yes | Last budget allocation |

**CRITICAL handling:** CRITICAL findings halt everything. No auto-fix attempted.
User is presented with the finding immediately. Examples: security vulnerability,
data loss risk, broken production path.

## Integration Points

### Where quality wraps in the workflow

```
                    skill-conductor
                         |
                         v
              [layer routing + execution]
                         |
                         v
  +--------------------------------------------------+
  |           QUALITY INVARIANTS LAYER                |
  |                                                   |
  |   post-spec/post-plan:                           |
  |     quality_gate -> review-gate (remapped)       |
  |                                                   |
  |   post-execution:                                |
  |     quality_gate -> test-gate -> review-gate     |
  |                     (both remapped)              |
  |                                                   |
  |   mr:                                            |
  |     quality_gate -> test-gate -> review-gate     |
  |                     (both remapped)              |
  +--------------------------------------------------+
                         |
                         v (PASSED only)
              [next workflow phase]
```

### Conductor integration

The `skill-conductor` replaces its direct invocation of `skill-conductor-review-gate`
with invocation of `skill-conductor-quality`. The quality layer then dispatches
to test-gate and review-gate internally.

**Change to `skill-conductor` After Routing step 4:**

Replace:
```
Invoke skill-conductor-review-gate as a blocking call.
```

With:
```
Invoke skill-conductor-quality as a blocking call. It dispatches
test-gate and review-gate internally with zero-debt enforcement.
```

### Gate input mapping (from conductor to quality layer)

| Transition | `gate_phase` | Additional inputs |
|-----------|-------------|-------------------|
| Spec produced | `post-spec` | `changeset_scope` = artifact paths |
| Plan produced | `post-plan` | `changeset_scope` = artifact paths |
| Execution complete | `post-execution` | `work_type`, full changeset |
| MR opened | `mr` | `head_ref`, full changeset |

## Proportionality (preventing over-enforcement)

Even with zero-debt policy, proportionality applies to EFFORT, not to STANDARDS:

| Tier | Standards | Effort |
|------|-----------|--------|
| trivial | Same (all findings block) | No auto-fix; findings presented as "fix these before proceeding" |
| moderate | Same (all findings block) | 2-iteration auto-fix budget |
| substantial | Same (all findings block) | 4-iteration auto-fix budget + cross-ecosystem |

The user's policy is clear: no finding is ignorable. But for a trivial change,
presenting 2 LOW findings with "fix before proceeding" is proportionate. Running
a 4-iteration auto-fix loop for a typo correction is not.

**Trivial tier shortcut:** For trivial changes, if the ONLY findings are LOW
severity AND there are 3 or fewer, present them inline without the full
resolution ceremony:

```
Quality gate: 2 findings on trivial change.
1. [LOW] Missing boundary test for empty string in validate_name()
2. [LOW] Assert only checks type, not value, in test_parse_config()

Fix these before proceeding, or provide ticket for exemption.
```

## Configuration

Override syntax (passed via `overrides` input):

```yaml
exemption_max_days: 60           # override default 30-day exemption window
ratchet_tolerance_percent: 0.5   # allow 0.5% coverage fluctuation (measurement noise)
baseline_path: ".quality-baseline.json"
skip_ratchet: false              # emergency escape hatch (requires confirmation)
dispute_enabled: true            # allow finding disputes
```

| Key | Effect | Default |
|-----|--------|---------|
| `exemption_max_days` | Max days for exemption | 30 (cap: 90) |
| `ratchet_tolerance_percent` | Noise margin for coverage ratchet | 0.5% |
| `baseline_path` | Location of baseline file | Auto-detect |
| `skip_ratchet` | Disable ratchet check (emergency) | false |
| `dispute_enabled` | Allow finding disputes | true |

**Cannot override:** The "all severities block" policy. It is the core invariant.

## Baseline Bootstrap

When no baseline exists (first run on a repo):

```
bootstrap_baseline(config):
  # Measure current state without blocking
  metrics = compute_current_metrics(config)

  # Create baseline file
  baseline = {
    updated_at: now(),
    coverage: metrics.coverage,
    debt: { total_findings: 0, exempted_findings: 0, exemptions: [] },
    metrics: metrics.quality_metrics
  }

  write_baseline(baseline, config.baseline_path)
  log("Quality baseline created. Future changes must meet or exceed these metrics.")
  log(f"  Line coverage: {metrics.coverage.line_percent}%")
  log(f"  Branch coverage: {metrics.coverage.branch_percent}%")
  log(f"  Test count: {metrics.quality_metrics.test_count}")

  # First run: evaluate but do not block on existing debt
  # (Otherwise adopting this system on a legacy codebase is impossible)
  # The ratchet kicks in from the SECOND run onward
  return PASSED_WITH_ADVISORY("Baseline created. Zero-debt enforcement active from next change.")
```

**Legacy codebase adoption:** The baseline captures the current state as the floor.
Existing debt is not retroactively blocking. But from this point forward, nothing
may get worse. Each change must leave quality the same or better.

## Instrumentation

After each quality gate run, report:
```
Quality gate [gate_phase]: [outcome] | tier: [complexity] | findings: [C/H/M/L] | fixed: [N] | exempted: [N] | ratchet: [pass/fail] | baseline: [created/updated/unchanged] | time: [Xm Ys]
```

## Emergency Override

In genuine emergencies (production incident, security patch), the full gate can
be bypassed. This is NOT a normal workflow; it requires:

1. User explicitly states emergency context
2. `ask_user` confirmation: "Emergency override requested. This bypasses ALL quality
   gates. Findings will be logged as debt against [ticket]. Confirm? (yes/no)"
3. Ticket ID for the emergency (incident ticket)
4. All findings from a dry-run are logged as exemptions with 7-day expiry
5. Instrumentation: "EMERGENCY OVERRIDE: [gate_phase] bypassed. [N] findings
   deferred to [ticket]. Expires: [date]."

The 7-day window means the debt surfaces immediately after the incident is resolved.
It cannot be forgotten.

## Relationship to Review Gate Severity Mapping

This layer OVERRIDES the review gate's default severity mapping:

**Before (review-gate default):**
```
CRITICAL / HIGH: blocking: true
MEDIUM / LOW: blocking: false (advisory only)
```

**After (quality layer applied):**
```
CRITICAL / HIGH / MEDIUM / LOW: blocking: true
```

The review-gate continues to classify severity as before. The quality layer
intercepts the output and remaps `blocking` to `true` for all findings before
evaluating pass/fail. The review gate does not need modification; the quality
layer wraps it.
