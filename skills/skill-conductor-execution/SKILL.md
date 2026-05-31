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
**Model:** `claude-sonnet-4.5` (structured reasoning, dependency analysis)
**Output:** plan.md with numbered steps

### executing-plans
**When:** Plan exists, time to build step by step.
**Model:** `claude-sonnet-4.5` (precision, follows plan faithfully)
**Prerequisite:** A plan artifact must exist (`plan.md`, `docs/superpowers/plans/*`,
or `.planning/*/PLAN.md`). For GSD plans (`.planning/`), prefer `gsd-execute-phase`
via the Context layer instead.
**Output:** Implemented code, updated plan status

### test-driven-development
**When:** Building new behavior where tests should drive design.
**Model:** `claude-sonnet-4.5` (TDD requires disciplined cycle adherence)
**Best for:** Functions, services, APIs, business logic
**Not for:** Config, docs, scaffolding

### dispatching-parallel-agents
**When:** 2+ independent tasks that can run simultaneously.
**Model:** `claude-haiku-4.5` per agent; `claude-sonnet-4.5` for orchestrator
**Best for:** Multiple file edits, independent modules, research

### subagent-driven-development
**When:** Complex multi-step work requiring coordination.
**Model:** `claude-sonnet-4.5` orchestrator; per-agent model depends on task complexity
**Best for:** Large features spanning many files/modules

### systematic-debugging
**When:** Something broken, cause not obvious.
**Model:** `claude-sonnet-4.5` (hypothesis generation, root cause analysis)
**Best for:** Intermittent bugs, mysterious failures, regressions

### requesting-code-review
**When:** Code written, want feedback before merging.
**Model:** `claude-haiku-4.5` (preparing review request is mechanical)

### receiving-code-review
**When:** Review feedback received, need to address it.
**Model:** `claude-sonnet-4.5` (judgment needed for non-trivial feedback)

### verification-before-completion
**When:** Implementation seems done, need to confirm.
**Model:** `claude-sonnet-4.5` (needs to reason about acceptance criteria)
**Output:** Verification report

### finishing-a-development-branch
**When:** Verified, ready to merge/ship.
**Model:** `claude-haiku-4.5` (mechanical: PR creation, cleanup)
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
| "Ship it" | finishing-a-development-branch |

## After Choosing

Invoke the chosen skill. The per-skill model recommendations above are authoritative
for the primary skill invocation. Pass `COMPLEXITY_TIER` from the conductor if
available; skills that spawn nested subagents use it for THOSE agent selections
(e.g., `claude-haiku-4.5` for trivial sub-tasks within a parallel dispatch).
Each Superpowers skill is self-contained with its own process and checkpoints.
