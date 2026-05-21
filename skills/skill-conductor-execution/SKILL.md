---
name: skill-conductor-execution
description: Execution layer guidance for the skill conductor. Helps choose the right Superpowers execution skill for the current phase of implementation work.
---

# Execution Layer: Building with Superpowers

You were routed here because requirements are clear and it is time to build.
Superpowers provides a disciplined execution loop: plan, implement (TDD),
verify, ship.

## Decision Tree

```
What phase of execution are you in?
  PLANNING (need implementation plan)
    --> invoke writing-plans
  IMPLEMENTING (plan exists, building features)
    --> Is TDD appropriate (new behavior, not config/docs)?
          YES --> invoke test-driven-development
          NO  --> invoke executing-plans
    --> Are there 2+ independent tasks?
          YES --> invoke dispatching-parallel-agents
    --> Is it complex multi-step with shared state?
          YES --> invoke subagent-driven-development
  DEBUGGING (something is broken)
    --> invoke systematic-debugging
  REVIEWING (code is written, needs review)
    --> invoke requesting-code-review (for others to review you)
    --> invoke receiving-code-review (responding to review feedback)
  VERIFYING (think you are done)
    --> invoke verification-before-completion
  SHIPPING (verified, ready to merge)
    --> invoke finishing-a-development-branch
```

## Skill Descriptions

### writing-plans
**When:** Requirements are clear, need a step-by-step implementation plan.
**What it does:** Creates a detailed plan with phases, dependencies, and
acceptance criteria. Saves to plan.md.
**Follows:** Decision layer (office-hours/brainstorming produced a design)
**Output:** plan.md with numbered steps

### executing-plans
**When:** Plan exists, time to build step by step.
**What it does:** Executes plan with review checkpoints. Marks steps complete.
**Prerequisite:** plan.md must exist
**Output:** Implemented code, updated plan status

### test-driven-development
**When:** Building new behavior where tests should drive the design.
**What it does:** RED (write failing test) -> GREEN (make it pass) -> REFACTOR.
Strict cycle enforcement.
**Best for:** New functions, services, APIs, business logic
**Not for:** Config changes, documentation, scaffolding

### dispatching-parallel-agents
**When:** 2+ independent tasks that can run simultaneously.
**What it does:** Launches multiple agents in parallel, each with a focused task.
Collects results.
**Best for:** Multiple file edits, independent modules, research threads

### subagent-driven-development
**When:** Complex multi-step work requiring coordination.
**What it does:** Manages a team of subagents with shared context and handoffs.
**Best for:** Large features spanning many files/modules

### systematic-debugging
**When:** Something is broken and the cause is not obvious.
**What it does:** Four phases: investigate, analyze, hypothesize, implement.
Iron rule: no fixes without root cause.
**Best for:** Intermittent bugs, mysterious failures, regression hunting

### requesting-code-review
**When:** Code is written, want feedback before merging.
**What it does:** Prepares a structured review request with context.

### receiving-code-review
**When:** Review feedback received, need to address it.
**What it does:** Guides systematic response to each review comment.

### verification-before-completion
**When:** Implementation seems done, need to confirm.
**What it does:** Checks that all acceptance criteria are met, tests pass,
no regressions introduced.
**Output:** Verification report

### finishing-a-development-branch
**When:** Verified, ready to merge/ship.
**What it does:** Guides PR creation, merge strategy, cleanup.
**Output:** Merged branch, cleaned up

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

Invoke the chosen skill. Let it run its own flow. Each Superpowers skill is
self-contained with its own process and checkpoints.
