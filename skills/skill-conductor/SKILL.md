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

### Opt-Out Detection

Before routing, check for review gate opt-out signals in the **current user message**:
- User says "skip reviews", "no reviews", or passes `--skip-reviews` / `--no-gate`
- Signal must be explicit in the current message; do not infer from prior context
- If detected: set `SKIP_GATES=true` and bypass all gate invocations for this routing
- Opt-out is per-invocation only; does not persist across messages

### Priority 0: Custom Skills (direct invocation, skip layers)

Route directly to a custom skill if the request clearly matches:

- User says "accessibility review", "a11y review", "check accessibility",
  "accessibility check" on a PR/diff or small scope: invoke `a11y-review`
- User says "full accessibility audit", "deep a11y", "inclusive design review",
  "accessibility audit" on a full codebase/app: invoke `a11y-review-deep`
- User says "code audit", "audit this repo", "repo health check": invoke `code-audit`

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
| gsd-map-codebase | Discover and document existing code before project setup |
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
| a11y-review | PR/diff accessibility and inclusive design review (lite) |
| a11y-review-deep | Full accessibility audit with persona simulation |
| hunk-reviewer | Hunk-by-hunk code review with subagent dispatch |
| incident-response | PagerDuty incident handling |
| devops-rollout-plan | Deployment planning with rollback procedures |
| conventional-commit | Structured commit message generation |

### Review Gate (invoke `skill-conductor-review-gate` at transitions)

| Skill | Purpose |
|-------|---------|
| skill-conductor-review-gate | Recursive multi-agent review at workflow transitions |

## After Routing

Once you determine the layer:
1. State which layer you detected and why (one sentence)
2. Invoke the appropriate sub-skill (`skill-conductor-decision`,
   `skill-conductor-context`, or `skill-conductor-execution`)
3. Follow that sub-skill's instructions until it produces its artifact
4. **Review gate check (post-artifact):** Once the sub-skill produces an artifact
   (spec, plan, or MR), check whether a gate applies to this transition AND
   `SKIP_GATES` is not set. If so, invoke `skill-conductor-review-gate` with
   the gate ID and artifact paths. Proceed to the next workflow stage only if
   the gate returns `PASSED`. If the gate returns `ESCALATED_BLOCKING`, halt
   and present findings to the user.
5. If `SKIP_GATES` is set, log "Review gate skipped by user request" at the
   conductor level and proceed to the next workflow stage immediately.

### Gate trigger mapping

| Transition | Gate | Inputs to pass |
|-----------|------|----------------|
| Sub-skill produces spec/design doc | post-spec | `gate_id=post-spec`, `artifact_paths=[path to spec]` |
| Sub-skill produces plan | post-plan | `gate_id=post-plan`, `artifact_paths=[path to plan]` |
| Sub-skill opens MR/PR | mr | `gate_id=mr`, `artifact_paths=[changed files]`, `changeset_scope=[list of diff files]`, `base_ref=<target branch>`, `head_ref=<source branch>` |

### Artifact detection

The conductor does NOT require sub-skills to return structured data. It monitors
the conversation for artifact creation signals:
- **post-spec:** A file was created/edited under `docs/superpowers/specs/` or a
  spec/design document path was mentioned as complete
- **post-plan:** A file was created/edited under `docs/superpowers/plans/` or a
  plan document path was mentioned as complete
- **mr:** `gh pr create` was run, or a PR/MR URL was output

For MR gates, run `git diff --name-only <base>..<head>` to populate
`changeset_scope`, and read the PR's base/head refs.

### Control flow

Gates fire AFTER a sub-skill produces its artifact, BEFORE the next workflow
stage begins. This is observational, not contractual: existing sub-skills do
not need modification.
