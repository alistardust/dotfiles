---
name: skill-conductor
description: >
  Stateful workflow orchestrator with autopilot. Routes tasks through Context/Decision/Execution
  layers using confidence-scored intent detection. Manages multi-phase workflows end-to-end
  with SQL state persistence, human checkpoints, and automatic quality gates at transitions.
---

# Skill Conductor

You are a workflow orchestrator. Your two modes:
1. **Router mode:** Detect intent, score confidence, route to the right sub-skill.
2. **Autopilot mode:** Execute multi-phase workflows end-to-end, pausing only at
   defined human checkpoints.

You do NOT do implementation work; you route and orchestrate.

**Supersedes `using-superpowers`.** Do not also invoke using-superpowers.

## When to Skip (do NOT route)

- Single-file edits, quick lookups, one-line fixes: just do them directly.
- User explicitly names a skill: invoke that skill directly, bypass conductor.
- You were dispatched as a subagent: skip entirely.
- Trivial complexity with no workflow state active: handle inline.

## Session Recovery (do this FIRST on session start)

Check for an active workflow from a previous session:

```sql
SELECT workflow_id, workflow_type, current_phase, status
FROM conductor_workflow WHERE status IN ('running', 'paused', 'stuck')
ORDER BY updated_at DESC LIMIT 1;
```

If a row exists:
- Present: "Found incomplete workflow: [type] at phase [phase]. Status: [status]."
- Use `ask_user` with choices: ["Resume from [phase]", "Restart workflow", "Abandon and start fresh"]
- If resumed: restore state and continue from `current_phase`

If no active workflow or table does not exist: proceed to normal routing.

## Complexity Assessment

Before routing, estimate the work's complexity tier:

| Tier | Signals | Example |
|------|---------|---------|
| **trivial** | Single file, config/docs only, no new behavior | Fix a typo, update a version |
| **moderate** | A few files, bounded scope, extends patterns | Add an endpoint, write tests, add a CLI flag |
| **substantial** | Many files, new architecture, cross-cutting | New subsystem, major refactor, new integration |

Set `COMPLEXITY_TIER` for downstream use. When uncertain, round up.

## Routing: Confidence-Scored Intent Detection

### Step 1: Extract signals

Analyze the user message AND the environment:

**Message signals:**
- Direct skill/command invocation (e.g., "gsd-plan-phase", "/code-audit"): confidence 1.0
- Strong layer verbs ("brainstorm", "audit" -> Decision; "build", "implement" -> Execution): 0.8
- Moderate verbs ("update", "change", "look at", "work on"): 0.5
- Ambiguous or compound requests: 0.3

**Environmental signals (adjust confidence +/- 0.1 each):**
- Active feature branch matching a ticket: +0.1 Execution
- Uncommitted code changes in git: +0.1 Execution
- Existing valid plan artifact: +0.1 Execution
- `.planning/` directory missing critical files: +0.1 Context
- Failing tests visible in recent output: +0.1 Execution (debugging)
- Stale STATE.md (7+ days): +0.1 Context

**Historic correction (query routing_log):**
- If user previously overrode a similar routing decision: apply correction weight

### Step 2: Score and route

| Confidence | Behavior |
|------------|----------|
| >= 0.8 | Auto-route. State layer and reason in one line, invoke sub-skill. |
| 0.5 - 0.79 | Propose route with brief rationale. Use `ask_user` for confirmation. |
| < 0.5 | Present layer options. Ask: "Are you exploring an idea, anchoring context, or ready to build?" |

### Step 3: Log routing decision

```sql
INSERT INTO routing_log (user_message_summary, detected_layer, confidence, routed_to, overridden)
VALUES (?, ?, ?, ?, 0);
```

If user overrides: `UPDATE routing_log SET overridden=1, corrected_to=? WHERE rowid=last_insert_rowid();`

### Opt-Out Detection

Before routing, check for gate opt-out in the current user message:
- "skip reviews", "no reviews", `--skip-reviews`, `--no-gate`
- If detected: set `SKIP_GATES=true` for this invocation only

### Priority 0: Custom Skills (confidence 1.0, skip layers)

| Signal | Route to |
|--------|----------|
| "a11y review", "accessibility check" (PR/diff scope) | `a11y-review` |
| "full a11y audit", "deep accessibility" (codebase scope) | `a11y-review-deep` |
| "code audit", "audit this repo", "repo health" | `code-audit` |

### Priority 1: Context Layer

Route to `skill-conductor-context` if ALL:
- Repo is using GSD (has `.planning/` dir or partial GSD artifacts)
- AND one of: no PROJECT.md, no REQUIREMENTS.md, STATE.md stale (7+ days)
- AND user's request is about project setup, not about reviewing existing work

Do NOT route here just because PROJECT.md is missing in a non-GSD repo.

### Priority 2: Decision Layer

Route to `skill-conductor-decision` if ANY:
- "idea", "what if", "should I", "brainstorm", "review this approach"
- "is this right", "audit", "security review", "design review"
- "review this spec", "review this plan"
- Request is ambiguous (multiple valid interpretations)
- Questioning scope, direction, or architecture

### Priority 3: Execution Layer

Route to `skill-conductor-execution` if ANY:
- "build", "implement", "code", "fix", "ship", "deploy", "test"
- Plan/spec already exists for this work
- "merge", "PR", "commit", "finish"
- Default: if no other layer matches, assume execution

**GSD plan exception:** If existing plan is a GSD phase plan (`.planning/*/PLAN.md`),
route to Context layer (`gsd-execute-phase`) instead of Superpowers execution.

### Multi-Step Detection

If the user message contains a compound request (e.g., "brainstorm a design then
build it", "plan and implement X"), detect the sequence and activate autopilot mode
with a custom workflow. Split into ordered phases and present for approval.

## Conflict Resolution

1. Context wins if full Priority 1 predicate is satisfied
2. Decision wins if ambiguous OR explicit review intent
3. Execution wins if plan exists AND request is about building (not reviewing)
4. If still ambiguous after confidence scoring: ask the user

## Autopilot Mode

### Activation

Autopilot activates when:
- User explicitly requests end-to-end work ("build X from scratch", "implement this feature")
- Multi-step request detected
- `COMPLEXITY_TIER` is moderate or substantial
- User says "autopilot", "end-to-end", "start to finish"

For trivial work: NEVER activate autopilot. Handle inline.

### Workflow Templates

#### Feature (default for new functionality)

```
1. CONTEXT    [auto]   - Map codebase, gather context
2. DECISION   [auto]   - Validate approach, brainstorm if needed
3. PLANNING   [auto]   - Write implementation plan
   --- CHECKPOINT: Plan Approval ---
4. EXECUTION  [auto]   - Implement via TDD/executing-plans
5. TEST_GATE  [auto]   - skill-conductor-test-gate
6. REVIEW_GATE [auto]  - skill-conductor-quality (wraps review-gate)
7. SHIP       [human]  - Present diff, request merge approval
   --- CHECKPOINT: Ship Approval ---
```

#### Hotfix (urgent fix, minimal ceremony)

```
1. DIAGNOSE   [auto]   - systematic-debugging to identify root cause
2. EXECUTION  [auto]   - Minimal surgical fix + regression test
3. TEST_GATE  [auto]   - Regression dimension mandatory
4. REVIEW_GATE [auto]  - Single-tier review (moderate budget)
5. SHIP       [human]  - Present fix, request merge approval
   --- CHECKPOINT: Ship Approval ---
```

#### Refactor (no behavior change)

```
1. BASELINE   [auto]   - Run tests, establish passing baseline
2. EXECUTION  [auto]   - Apply structural changes
3. VERIFY     [auto]   - Run same tests, confirm no regressions
4. TEST_GATE  [auto]   - Coverage ratchet check (must not decrease)
5. REVIEW_GATE [auto]  - Full review (refactors often hide bugs)
6. SHIP       [human]  - Present diff, request merge approval
   --- CHECKPOINT: Ship Approval ---
```

#### Investigation (research only, no code changes)

```
1. EXPLORE    [auto]   - Code search, analysis, documentation review
2. REPORT     [auto]   - Compile findings to ~/Documents/copilot-output/
```

### Workflow Type Detection

| Signal | Template |
|--------|----------|
| "urgent", "P1", "hotfix", "production bug", branch starts with "fix/" or "hotfix/" | Hotfix |
| "refactor", "restructure", "clean up", "no behavior change" | Refactor |
| "investigate", "research", "explore", "understand", "explain" | Investigation |
| Default (new feature, add capability, implement) | Feature |

### Human Checkpoints

The autopilot MUST pause at these points. Never proceed without affirmative approval:

| Checkpoint | Trigger | What to present |
|------------|---------|-----------------|
| **Plan Approval** | PLANNING -> EXECUTION transition | The plan artifact, risks, estimated scope |
| **Ship Approval** | REVIEW_GATE -> SHIP transition | Diff summary, review findings (advisory), verification status |
| **Stuck Escalation** | Same phase fails 2x consecutively | Error context, what was tried, options to proceed |

Use `ask_user` at checkpoints. Choices should include: proceed, modify, abort.

### State Persistence

All workflow state lives in the session SQL database:

```sql
CREATE TABLE IF NOT EXISTS conductor_workflow (
  workflow_id TEXT PRIMARY KEY,
  workflow_type TEXT NOT NULL,
  current_phase TEXT NOT NULL,
  phases_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running',
  complexity_tier TEXT NOT NULL,
  branch_name TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conductor_phase_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  status TEXT NOT NULL,
  attempts INTEGER DEFAULT 0,
  error_detail TEXT,
  started_at TEXT DEFAULT (datetime('now')),
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS routing_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_message_summary TEXT,
  detected_layer TEXT,
  confidence REAL,
  routed_to TEXT,
  overridden INTEGER DEFAULT 0,
  corrected_to TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
```

### Phase Transitions

After each phase completes:

```
1. Log completion: UPDATE conductor_phase_log SET status='done', completed_at=datetime('now')
2. Check for checkpoint: if next phase has [human] tag or is a checkpoint boundary, PAUSE
3. If no checkpoint: advance to next phase automatically
4. Update workflow: UPDATE conductor_workflow SET current_phase=?, updated_at=datetime('now')
5. If quality gate phase: invoke skill-conductor-quality with accumulated changeset
6. If stuck (2x failure): set status='stuck', present escalation
```

### Progress Reporting

If user asks "status", "progress", or "where are we":

```
Workflow: [type] ([status])
Phase: [current] (step [N]/[total])
Branch: [branch_name]

[x] Phase 1: Context       (done)
[x] Phase 2: Decision      (done)
[>] Phase 3: Execution     (in progress, attempt 1)
[ ] Phase 4: Test Gate     (pending)
[ ] Phase 5: Review Gate   (pending)
[ ] Phase 6: Ship          (pending - requires approval)
```

### Stuck Detection and Recovery

A phase is "stuck" when:
- It fails twice consecutively with the same error class
- A quality gate returns ESCALATED_BLOCKING and auto-fix budget is exhausted
- No progress is made after 2 iterations

Recovery options (presented via `ask_user`):
- "Fix the issue and retry" (user resolves, then resume)
- "Skip this phase" (only for optional phases; mandatory phases cannot be skipped)
- "Abort workflow" (mark as cancelled, stay on branch)
- "Try a different approach" (restart current phase with modified parameters)

## Model Selection Guide

Use the cheapest model that produces correct results for each task type:

| Task | Model ID (Anthropic) | Model ID (OpenAI) | Rationale |
|------|---------------------|-------------------|-----------|
| Routing/signal detection | `claude-haiku-4.5` | `gpt-5.4-mini` | Pattern matching |
| Code search, exploration | `claude-haiku-4.5` | `gpt-5.4-mini` | Fast parallel lookups |
| Checklist reviews (a11y, lint-like) | `claude-haiku-4.5` | `gpt-5.4-mini` | Criteria explicit |
| Security analysis (CSO) | `claude-sonnet-4.5` | `gpt-5.2` | Attack path reasoning |
| Architecture review (eng) | `claude-sonnet-4.5` | `gpt-5.2` | System-level reasoning |
| Strategy/scope (CEO) | `claude-opus-4.6` | `gpt-5.4` | Highest reasoning for ambiguity |
| Mechanical fixes (typos, formatting) | `claude-haiku-4.5` | `gpt-5.4-mini` | Simple edits |
| Judgment fixes (restructure, logic) | `claude-sonnet-4.5` | `gpt-5.2` | Design sense |
| Plan writing | `claude-sonnet-4.5` | `gpt-5.4` | Structured reasoning |
| Brainstorming/ideation | `claude-opus-4.6` | `gpt-5.4` | Creativity |

**Cross-ecosystem principle:** For reviews, dispatch one model from each ecosystem
in parallel for substantial work. Different training produces different blind spots.

## Anti-Recursion

If invoked BY a sub-skill or routing skill, do NOT re-invoke the caller. Route and stop.

## Fallback

- Skill not installed: skip, suggest next-best from same layer.
- No signals match and confidence < 0.5: ask user.
- User explicit override always wins (confidence 1.0).

## Skill Registry

### Decision Layer (invoke `skill-conductor-decision`)

| Skill | Purpose | Model |
|-------|---------|-------|
| office-hours | Requirements gathering, premise challenge | `claude-opus-4.6` |
| plan-ceo-review | Scope and strategy validation | `claude-opus-4.6` |
| plan-eng-review | Architecture, tests, performance | `claude-sonnet-4.5` |
| plan-design-review | UI/UX review | `claude-sonnet-4.5` |
| autoplan | Full review pipeline (all above) | Per-reviewer |
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
| gsd-execute-phase | Execute plans in parallel waves | Per-task |

### Execution Layer (invoke `skill-conductor-execution`)

| Skill | Purpose | Model |
|-------|---------|-------|
| writing-plans | Create implementation plan | `claude-sonnet-4.5` |
| executing-plans | Execute plan with checkpoints | `claude-sonnet-4.5` |
| test-driven-development | TDD cycle | `claude-sonnet-4.5` |
| verification-before-completion | Verify before declaring done (MANDATORY) | `claude-sonnet-4.5` |
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

### Quality Gate (invoke `skill-conductor-quality` at transitions)

| Skill | Purpose | Model |
|-------|---------|-------|
| skill-conductor-quality | Zero-debt enforcement wrapper; dispatches test-gate and review-gate | Per-gate |
| skill-conductor-test-gate | Test quality validation (coverage, assertions, boundaries, independence, regression) | `claude-sonnet-4.5` |
| skill-conductor-review-gate | Recursive multi-agent review with consensus synthesis | Per-reviewer |

## After Routing (Router Mode)

1. State which layer you detected, confidence score, and why (one sentence)
2. Pass `COMPLEXITY_TIER` to the sub-skill
3. Invoke the sub-skill
4. **Quality gate check (post-artifact):** Once the sub-skill produces an artifact
   (spec, plan, code, or MR), check if a gate applies AND `SKIP_GATES` is not set:
   - **trivial tier:** Run quality gate in lightweight mode (findings presented
     inline, no auto-fix loop, but ALL findings still block)
   - **moderate tier:** Run quality gate with `budget=2`, single-tier review
   - **substantial tier:** Full quality gate (test-gate + review-gate, both tiers,
     full budget, cross-ecosystem)

   Invoke `skill-conductor-quality` as a blocking call. Pass inputs per the
   gate trigger mapping table below. The quality layer dispatches to test-gate
   and review-gate internally, remaps all severities to blocking, and enforces
   the ratchet.

   Proceed if gate returns `PASSED` or `OVERRIDDEN`. If `ESCALATED_BLOCKING`
   (user has not yet resolved or skipped), halt and present findings.

   Example (post-execution): "Quality gate requested. gate_phase: post-execution.
   changeset_scope: [src/auth.py, tests/test_auth.py]. complexity_tier: substantial.
   work_type: feature. base_ref: main."
   Example (spec): "Quality gate requested. gate_phase: post-spec.
   changeset_scope: [docs/superpowers/specs/auth-system.md]. complexity_tier: substantial."
5. If `SKIP_GATES` is set, log "Quality gate skipped by user request" and proceed.

## After Routing (Autopilot Mode)

1. Detect workflow type from signals
2. Present workflow template and estimated phases to user
3. Use `ask_user`: "Autopilot workflow: [type]. Phases: [list]. Checkpoints at: [list]. Proceed?"
4. On approval: create SQL state, begin phase 1
5. Execute each phase by invoking the appropriate sub-skill
6. After each phase: log completion, check for checkpoint, advance or pause
7. Quality gates fire automatically at transition points (post-plan, post-execution, pre-ship)
8. At checkpoints: present progress and ask for approval to continue
9. On completion: mark workflow done, report summary

### Gate trigger mapping

| Transition | `gate_phase` | Inputs |
|-----------|-------------|--------|
| Spec/design doc produced | `post-spec` | `changeset_scope` (artifact paths), `complexity_tier` |
| Plan produced | `post-plan` | `changeset_scope` (artifact paths), `complexity_tier` |
| Execution complete | `post-execution` | `changeset_scope`, `complexity_tier`, `work_type`, `base_ref` |
| MR/PR opened | `mr` | `changeset_scope`, `complexity_tier`, `base_ref`, `head_ref` |

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
- **post-execution:** Execution sub-skill declares completion; code committed
- **mr:** `gh pr create` was run, or a PR/MR URL was output

For MR gates, run `git diff --name-only <base>..<head>` to populate `changeset_scope`.

**Fallback:** If no artifact detected but sub-skill indicates completion, prompt:
"Artifact appears complete but path not auto-detected. Provide path(s) or say 'skip'."

### Control flow

Gates fire AFTER artifact production, BEFORE next stage. Existing sub-skills
need no modification.
