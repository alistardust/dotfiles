---
name: skill-conductor-execution
description: Execution layer guidance for the skill conductor. Helps choose the right Superpowers execution skill for the current phase of implementation work.
---

# Execution Layer: Building with Superpowers

You were routed here because requirements are clear and it is time to build.
Superpowers provides a disciplined execution loop: plan, implement (TDD),
verify, ship.

## Decision Tree

Priority-ordered: first matching branch wins.

```
What phase of execution are you in?
  PLANNING (need implementation plan)
    --> invoke writing-plans
  IMPLEMENTING (plan exists, building features)
    --> Priority order (first match wins):
        1. Complex multi-step with shared state? --> subagent-driven-development
        2. 2+ independent tasks, no shared state? --> dispatching-parallel-agents
        3. New behavior where tests should drive design? --> test-driven-development
        4. Otherwise --> executing-plans
  DEBUGGING (something is broken)
    --> invoke systematic-debugging
  REVIEWING (code is written, needs review)
    --> Has review feedback already been received? --> receiving-code-review
    --> No feedback yet, want to request it? --> requesting-code-review
  VERIFYING (think you are done)
    --> invoke verification-before-completion
  SHIPPING (verified, ready to merge)
    --> invoke finishing-a-development-branch
```

## Skill Descriptions

### writing-plans
**When:** Requirements clear, need step-by-step implementation plan.
**Suggested tier:** reasoning (structured reasoning, dependency analysis)
**Output:** plan.md with numbered steps

### executing-plans
**When:** Plan exists, time to build step by step.
**Suggested tier:** reasoning (precision, follows plan faithfully)
**Prerequisite:** A plan artifact must exist (`plan.md`, `docs/superpowers/plans/*`,
or `.planning/*/PLAN.md`). For GSD plans (`.planning/`), prefer `gsd-execute-phase`
via the Context layer instead.
**Output:** Implemented code, updated plan status

### test-driven-development
**When:** Building new behavior where tests should drive design.
**Suggested tier:** reasoning (TDD requires disciplined cycle adherence)
**Best for:** Functions, services, APIs, business logic
**Not for:** Config, docs, scaffolding

### dispatching-parallel-agents
**When:** 2+ independent tasks that can run simultaneously.
**Suggested tier:** fast per agent; reasoning for orchestrator
**Best for:** Multiple file edits, independent modules, research

### subagent-driven-development
**When:** Complex multi-step work requiring coordination.
**Suggested tier:** reasoning for orchestrator; per-agent tier depends on task complexity
**Best for:** Large features spanning many files/modules

### systematic-debugging
**When:** Something broken, cause not obvious.
**Suggested tier:** reasoning (hypothesis generation, root cause analysis)
**Best for:** Intermittent bugs, mysterious failures, regressions

### requesting-code-review
**When:** Code written, want feedback before merging.
**Suggested tier:** fast (preparing review request is mechanical)

### receiving-code-review
**When:** Review feedback received, need to address it.
**Suggested tier:** reasoning (judgment needed for non-trivial feedback)

### verification-before-completion
**When:** Implementation seems done, need to confirm.
**Suggested tier:** reasoning (needs to reason about acceptance criteria)
**Output:** Verification report

### finishing-a-development-branch
**When:** Verified, ready to merge/ship.
**Suggested tier:** fast (mechanical: PR creation, cleanup)
**Output:** Merged branch

## Choosing Between Similar Skills

| Situation | Choose |
|-----------|--------|
| Simple sequential steps | executing-plans |
| New behavior needs tests | test-driven-development |
| Many independent pieces | dispatching-parallel-agents |
| Complex coordinated work | subagent-driven-development |
| Bug fix | systematic-debugging |
| "Am I done?" | verification-before-completion |
| "Ship it" | verification-before-completion (then finishing-a-development-branch) |

## Mandatory Verification Gate

Verification is NOT optional. It is a required gate between execution and shipping:

1. **Never skip:** Code changes cannot be committed, merged, or shipped without
   running `verification-before-completion` first. This is non-negotiable.
2. **Fail loudly:** If verification fails, invoke `systematic-debugging` to
   diagnose, or escalate to the user. Do not proceed past a failed verification.
3. **No direct path to ship:** You cannot transition from implementing/TDD/executing
   directly to `finishing-a-development-branch`. Verification is always between them.

```
executing-plans / test-driven-development / subagent-driven-development / dispatching-parallel-agents
    |
    v (always, when work produces shippable code)
verification-before-completion (includes real-data validation)
    |
    v (pass only)
finishing-a-development-branch
```

**Exception:** Debugging and review flows that do not produce shippable changes
(e.g., investigation-only, requesting-code-review) do not require this gate.

## Real-Data Validation (part of verification)

Implements "Ground in Reality: post-implementation trigger." On fast-path, a quick
confirmation that the change works is sufficient; the full protocol below applies
at medium+ intensity.

When `verification-before-completion` runs, it MUST include real-data validation
in addition to test passing. Tests can pass against synthetic fixtures while the
real use case remains broken.

1. **After tests pass:** Run the implemented feature against actual data. Not a test
   fixture. Not a synthetic example. The real thing (or the closest available).

2. **Show the output.** Present it to the user. Ask: "Does this produce the result
   you expected?"

3. **If the output is wrong:** The implementation is wrong. Do not:
   - Suggest the user change their data (Adaptation Direction invariant)
   - Characterize broken output as "expected for Phase 1"
   - Propose "graceful degradation" for core functionality
   - Offer a workaround that shifts burden to the user

4. **If real data unavailable:** Trace through implementation logic by hand with
   the closest available example. Show expected behavior at each step.

### Anti-patterns (drift signals in verification)

| Anti-pattern | Correct response |
|--------------|-----------------|
| "Your data needs annotations" | Fix the parser |
| "This will work in Phase 2" | If it's core, it works now |
| "Falls back to scoring" | If text parsing is primary, make it work |
| "All tests pass!" (but no real data shown) | Show it working on actual data |
| "You could add markers to help" | The tool finds what's there |

## After Choosing

Invoke the chosen skill. The per-skill tier suggestions above are starting points
for the primary skill invocation. Pass `COMPLEXITY_TIER` from the conductor if
available; skills that spawn nested subagents use it for THOSE agent selections
(e.g., fast tier for trivial sub-tasks within a parallel dispatch).
Each Superpowers skill is self-contained with its own process and checkpoints.
