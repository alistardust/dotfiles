---
name: skill-conductor
description: Three-layer workflow orchestrator. Routes tasks to the right framework (gstack for decisions, GSD for context, Superpowers for execution) based on signal detection. Invoke before any multi-step task.
---

# Skill Conductor

You are a workflow router. Detect what phase of work the user is in and delegate
to the appropriate sub-skill. You do NOT do the work; you route to the skill that does.

**Supersedes `using-superpowers`.** Do not also invoke using-superpowers.

## When to Skip (do NOT route)

- Single-file edits, quick lookups, one-line fixes: just do them directly.
- User explicitly names a skill: invoke that skill directly, bypass conductor.
- You were dispatched as a subagent: skip entirely.

## Complexity Assessment (do this FIRST)

Before routing, estimate the work's complexity tier based on the request's apparent
scope. This determines model selection and review depth throughout the workflow:

| Tier | Signals (estimated, not measured) | Example |
|------|-----------------------------------|---------|
| **trivial** | Single file, config/docs only, no new behavior, quick fix | Fix a typo, update a version, tweak a config value |
| **moderate** | A few files, clear bounded scope, extends existing patterns | Add a new endpoint, write a test suite, add a CLI flag |
| **substantial** | Many files, new architecture, cross-cutting concerns, design decisions | New subsystem, major refactor, new integration |

Set `COMPLEXITY_TIER` for downstream use. When uncertain, round up.
This is a pre-work estimate; you cannot know exact line counts yet.

## Model Selection Guide

Use the cheapest model that produces correct results for each task type:

| Task | Model ID (Anthropic) | Model ID (OpenAI) | Rationale |
|------|---------------------|-------------------|-----------|
| Routing/signal detection | `claude-haiku-4.5` | `gpt-5.4-mini` | Pattern matching; no reasoning needed |
| Code search, exploration | `claude-haiku-4.5` | `gpt-5.4-mini` | Fast parallel lookups |
| Checklist reviews (a11y, lint-like) | `claude-haiku-4.5` | `gpt-5.4-mini` | Criteria are explicit |
| Security analysis (CSO) | `claude-sonnet-4.5` | `gpt-5.2` | Needs reasoning about attack paths |
| Architecture review (eng) | `claude-sonnet-4.5` | `gpt-5.2` | Needs system-level reasoning |
| Strategy/scope (CEO) | `claude-opus-4.6` | `gpt-5.4` | Highest reasoning for ambiguity |
| Mechanical fixes (typos, formatting) | `claude-haiku-4.5` | `gpt-5.4-mini` | Simple edits |
| Judgment fixes (restructure, logic) | `claude-sonnet-4.5` | `gpt-5.2` | Needs design sense |
| Plan writing | `claude-sonnet-4.5` | `gpt-5.4` | Needs structured reasoning |
| Brainstorming/ideation | `claude-opus-4.6` | `gpt-5.4` | Creativity benefits from strongest model |

**Cross-ecosystem principle:** For reviews, dispatching one lightweight model from
each ecosystem (e.g., `claude-haiku-4.5` + `gpt-5.4-mini` in parallel) often catches
more than one expensive model alone. Different training produces different blind spots.
Use cross-ecosystem dispatch when:
- `COMPLEXITY_TIER` is substantial
- The review is a blocking gate (post-spec, post-plan, MR)
- Time budget allows parallel dispatch (always prefer parallel over sequential)

Cross-ecosystem is optional for trivial/moderate tiers.

## Signal Detection

Read the user's message and check the environment. Match in priority order:

### Opt-Out Detection

Before routing, check for review gate opt-out in the **current user message**:
- "skip reviews", "no reviews", `--skip-reviews`, `--no-gate`
- Must be explicit in current message; do not infer from prior context
- If detected: set `SKIP_GATES=true`, bypass all gate invocations this routing
- Per-invocation only; does not persist

### Priority 0: Custom Skills (direct match, skip layers)

| Signal | Route to |
|--------|----------|
| "a11y review", "accessibility check" (PR/diff scope) | `a11y-review` |
| "full a11y audit", "deep accessibility" (codebase scope) | `a11y-review-deep` |
| "code audit", "audit this repo", "repo health" | `code-audit` |

### Priority 1: Context Layer (no foundation exists)

Route to `skill-conductor-context` if ALL of these are true:
- Repo is already using GSD (has `.planning/` dir or partial GSD artifacts)
- AND one of: no PROJECT.md, no REQUIREMENTS.md, `.planning/STATE.md` stale (7+ days)
- AND user's request is about project setup, not about reviewing existing work

Do NOT route here just because PROJECT.md is missing in a non-GSD repo.
If the user's request is clearly about implementation or review, respect that intent.

### Priority 2: Decision Layer (unclear or needs validation)

Route to `skill-conductor-decision` if ANY:
- "idea", "what if", "should I", "brainstorm", "review this approach"
- "is this right", "audit", "security review", "design review"
- "review this spec", "review this plan" (existing artifact needs validation)
- Request is ambiguous (multiple valid interpretations)
- Questioning scope, direction, or architecture

**Note:** "review this spec" routes here (Decision), not to Context. The word
"spec" alone without review intent routes to Context only in GSD repos.

### Priority 3: Execution Layer (requirements clear, build it)

Route to `skill-conductor-execution` if ANY:
- "build", "implement", "code", "fix", "ship", "deploy", "test"
- Plan/spec already exists for this work (but see GSD exception below)
- "merge", "PR", "commit", "finish"
- Default: if no other layer matches, assume execution

**GSD plan exception:** If the existing plan is a GSD phase plan (`.planning/*/PLAN.md`),
route to Context layer (`gsd-execute-phase`) instead of Superpowers execution. GSD
plans use their own execution engine with wave-based parallelization.

## Conflict Resolution

1. Context wins if the full Priority 1 predicate is satisfied (GSD repo + missing artifacts + setup intent)
2. Decision wins if request is ambiguous OR contains explicit review intent (even if artifacts exist)
3. Execution wins if plan/spec already exists AND request is about building (not reviewing).
   Exception: GSD phase plans (`.planning/*/PLAN.md`) route to Context layer regardless.
4. If still ambiguous: ask "Are you exploring an idea, anchoring context, or ready to build?"

## Anti-Recursion

If invoked BY a sub-skill or routing skill, do NOT re-invoke the caller. Route and stop.

## Fallback

- Skill not installed: skip, suggest next-best from same layer.
- No signals match: default to execution.
- User explicit override always wins.

## Skill Registry

### Decision Layer (invoke `skill-conductor-decision`)

| Skill | Purpose | Model |
|-------|---------|-------|
| office-hours | Requirements gathering, premise challenge | `claude-opus-4.6` |
| plan-ceo-review | Scope and strategy validation | `claude-opus-4.6` |
| plan-eng-review | Architecture, tests, performance | `claude-sonnet-4.5` |
| plan-design-review | UI/UX review | `claude-sonnet-4.5` |
| autoplan | Full review pipeline (all above) | Per-reviewer (see dispatch table) |
| brainstorming | Ideation, design exploration | `claude-opus-4.6` |
| cso | Security-focused audit | `claude-sonnet-4.5` |

### Context Layer (invoke `skill-conductor-context`)

| Skill | Purpose | Model |
|-------|---------|-------|
| gsd-new-project | Initialize PROJECT.md, REQUIREMENTS.md, ROADMAP.md | `claude-sonnet-4.5` |
| gsd-map-codebase | Discover and document existing code | `claude-haiku-4.5` |
| gsd-discuss-phase | Capture implementation decisions | `claude-sonnet-4.5` |
| gsd-plan-phase | Research and plan a phase | `claude-sonnet-4.5` |
| gsd-phase | Phase lifecycle management | `claude-haiku-4.5` |
| gsd-execute-phase | Execute plans in parallel waves | Per-task (see GSD docs) |

### Execution Layer (invoke `skill-conductor-execution`)

| Skill | Purpose | Model |
|-------|---------|-------|
| writing-plans | Create implementation plan | `claude-sonnet-4.5` |
| executing-plans | Execute plan with checkpoints | `claude-sonnet-4.5` |
| test-driven-development | TDD cycle | `claude-sonnet-4.5` |
| verification-before-completion | Verify before declaring done | `claude-sonnet-4.5` |
| dispatching-parallel-agents | Parallel independent tasks | `claude-haiku-4.5` (per-agent) |
| subagent-driven-development | Complex multi-agent work | `claude-sonnet-4.5` (orchestrator) |
| systematic-debugging | Root cause investigation | `claude-sonnet-4.5` |
| requesting-code-review | Prepare review request | `claude-haiku-4.5` |
| receiving-code-review | Address review feedback | `claude-sonnet-4.5` |
| finishing-a-development-branch | Merge/cleanup/PR | `claude-haiku-4.5` |

### Custom Skills (layer-independent, invoke directly)

| Skill | Purpose | Model |
|-------|---------|-------|
| code-audit | Full repo audit | `claude-haiku-4.5` + `claude-sonnet-4.5` |
| a11y-review | PR accessibility review (lite) | `claude-haiku-4.5` |
| a11y-review-deep | Full accessibility audit | `claude-sonnet-4.5` |
| hunk-reviewer | Per-hunk code review | `claude-haiku-4.5` |
| incident-response | PagerDuty incident handling | `claude-sonnet-4.5` |
| devops-rollout-plan | Deployment planning | `claude-sonnet-4.5` |
| conventional-commit | Commit message generation | `claude-haiku-4.5` |

### Review Gate (invoke `skill-conductor-review-gate` at transitions)

| Skill | Purpose | Model |
|-------|---------|-------|
| skill-conductor-review-gate | Recursive multi-agent review at transitions | Per-reviewer (see gate skill) |

## After Routing

1. State which layer you detected and why (one sentence)
2. Pass `COMPLEXITY_TIER` to the sub-skill
3. Invoke the sub-skill
4. **Review gate check (post-artifact):** Once the sub-skill produces an artifact
   (spec, plan, or MR), check if a gate applies AND `SKIP_GATES` is not set:
   - **trivial tier:** Skip gates entirely (log "Gate skipped: trivial change")
   - **moderate tier:** Run gates with `budget=2`, single-tier only
   - **substantial tier:** Full gate protocol (both tiers, full budget)

   Invoke `skill-conductor-review-gate` as a blocking call. Pass inputs per the
   gate trigger mapping table below (different inputs for MR vs spec/plan gates).
   Proceed if gate returns `PASSED` or `OVERRIDDEN`. If `ESCALATED_BLOCKING`
   (user has not yet resolved or skipped), halt and present findings.

   Example (spec): "Review gate requested. gate_id: post-spec. artifact_paths:
   [docs/superpowers/specs/auth-system.md]. complexity_tier: substantial. overrides: none."
   Example (MR): "Review gate requested. gate_id: mr. changeset_scope: [src/auth.ts, ...].
   base_ref: main. head_ref: feature/auth. complexity_tier: substantial. overrides: none."
5. If `SKIP_GATES` is set, log "Review gate skipped by user request" and proceed.

### Gate trigger mapping

| Transition | Gate | Inputs |
|-----------|------|--------|
| Spec/design doc produced | post-spec | `gate_id`, `artifact_paths`, `complexity_tier` |
| Plan produced | post-plan | `gate_id`, `artifact_paths`, `complexity_tier` |
| MR/PR opened | mr | `gate_id`, `changeset_scope`, `base_ref`, `head_ref`, `complexity_tier` |

### Artifact detection

Monitor the conversation for creation signals (observational, not contractual):
- **post-spec:** File created/edited matching ANY of:
  - `docs/superpowers/specs/*` (brainstorming output)
  - `~/.gstack/projects/*` (office-hours output)
  - Any file explicitly called a "spec" or "design doc" by the sub-skill
- **post-plan:** File created/edited matching ANY of:
  - `docs/superpowers/plans/*` (writing-plans output)
  - `plan.md` in session or repo root (writing-plans output)
  - `.planning/*/PLAN.md` (GSD plan output)
  - Any file explicitly called a "plan" by the sub-skill
- **mr:** `gh pr create` was run, or a PR/MR URL was output

For MR gates, run `git diff --name-only <base>..<head>` to populate `changeset_scope`.

**Fallback:** If no artifact detected but sub-skill indicates completion, prompt:
"Artifact appears complete but path not auto-detected. Provide path(s) or say 'skip'."

### Control flow

Gates fire AFTER artifact production, BEFORE next stage. Existing sub-skills
need no modification.
