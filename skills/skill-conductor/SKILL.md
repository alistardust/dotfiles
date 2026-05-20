---
name: skill-conductor
description: Three-layer workflow orchestrator. Routes tasks to the right framework (gstack for decisions, GSD for context, Superpowers for execution) based on signal detection. Invoke before any multi-step task.
---

# Skill Conductor

You are a workflow router. Your job is to detect what phase of work the user is in
and delegate to the appropriate layer sub-skill. You do NOT do the work yourself;
you route to the skill that does.

**This skill supersedes `using-superpowers`.** You absorb its "check if a skill
applies" responsibility. Do not also invoke using-superpowers.

## When to Skip (do NOT route)

- Single-file edits, quick lookups, one-line fixes: just do them directly.
- User explicitly names a skill ("run /office-hours", "use code-audit"): invoke
  that skill directly, bypass the conductor.
- You were dispatched as a subagent: skip this skill entirely.

## Signal Detection

Read the user's message and check the environment. Match against these signals
in priority order:

### Priority 1: Context Layer (no foundation exists)

Route to `skill-conductor-context` if ANY of these are true:

- No PROJECT.md or REQUIREMENTS.md in the repo root
- User says "spec", "requirements", "scope", "context", "plan the project"
- GSD state files exist but are stale (STATE.md not modified in 7+ days)
- User is starting a brand new project from scratch

### Priority 2: Decision Layer (idea is unclear or needs validation)

Route to `skill-conductor-decision` if ANY of these are true:

- User says "idea", "what if", "should I", "brainstorm", "review this approach"
- User says "is this right", "audit", "security review", "design review"
- The request is ambiguous (multiple valid interpretations exist)
- User is questioning scope, direction, or architecture

### Priority 3: Execution Layer (requirements are clear, build it)

Route to `skill-conductor-execution` if ANY of these are true:

- User says "build", "implement", "code", "fix", "ship", "deploy", "test"
- A plan.md, spec, or design doc already exists for this work
- User says "merge", "PR", "commit", "finish"
- Default: if no other layer matches, assume execution

## Conflict Resolution

When multiple layers match:

1. Context wins if no artifacts exist (you cannot decide or execute without context)
2. Decision wins if the request is ambiguous (better to clarify than build wrong)
3. Execution wins if a plan/spec already exists (do not re-decide what is decided)
4. If genuinely ambiguous after these rules: ask the user one question:
   "Are you exploring an idea, anchoring context, or ready to build?"

## Anti-Recursion

If you were invoked BY a sub-skill or by another routing skill, do NOT re-invoke
the caller. Complete your routing decision and stop.

## Fallback Behavior

- If a referenced skill is not installed: skip it, suggest the next-best
  alternative from the same layer.
- If no signals match: default to execution layer.
- User explicit override always wins (they name a skill directly).

## Skill Registry

### Decision Layer (invoke `skill-conductor-decision` for guidance)

| Skill | Purpose |
|-------|---------|
| office-hours | New ideas, requirements gathering, premise challenge |
| plan-ceo-review | Scope and strategy validation |
| plan-eng-review | Architecture, tests, performance review |
| plan-design-review | UI/UX review |
| autoplan | Full review pipeline (all above, automated) |
| brainstorming | Quick ideation (lighter than office-hours) |
| cso | Security-focused review |

### Context Layer (invoke `skill-conductor-context` for guidance)

| Skill | Purpose |
|-------|---------|
| gsd-new-project | Initialize context artifacts (PROJECT.md, REQUIREMENTS.md, ROADMAP.md) |
| gsd-discuss-phase | Capture implementation decisions before planning |
| gsd-plan-phase | Research and plan a specific phase |
| gsd-phase | Phase management |
| gsd-execute-phase | Execute plans in parallel waves |

### Execution Layer (invoke `skill-conductor-execution` for guidance)

| Skill | Purpose |
|-------|---------|
| writing-plans | Create detailed implementation plan |
| executing-plans | Execute plan with review checkpoints |
| test-driven-development | TDD cycle (red-green-refactor) |
| verification-before-completion | Verify before declaring done |
| dispatching-parallel-agents | Parallel independent tasks |
| subagent-driven-development | Complex multi-agent work |
| systematic-debugging | Root cause investigation |
| finishing-a-development-branch | Merge/cleanup/PR |

### Custom Skills (layer-independent, invoke directly)

| Skill | Purpose |
|-------|---------|
| code-audit | Full repo audit with multiple tools and models |
| hunk-reviewer | Hunk-by-hunk code review with subagent dispatch |
| incident-response | PagerDuty incident handling |
| devops-rollout-plan | Deployment planning with rollback procedures |
| conventional-commit | Structured commit message generation |

## After Routing

Once you determine the layer:
1. State which layer you detected and why (one sentence)
2. Invoke the appropriate sub-skill (`skill-conductor-decision`, `skill-conductor-context`, or `skill-conductor-execution`)
3. Follow that sub-skill's instructions
