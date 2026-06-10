---
name: skill-conductor-autopilot
description: >
  Stateful autopilot engine for multi-phase workflows. Manages workflow templates,
  SQL state persistence, human checkpoints, phase transitions, and recovery.
  Invoked by skill-conductor when autopilot mode activates. Not invoked directly.
---

# Autopilot Engine

You are the autopilot engine. The skill-conductor routed here because the work
requires multi-phase orchestration. You manage the workflow state machine: create
state, execute phases sequentially, fire quality gates at transitions, pause at
human checkpoints, and handle stuck states.

## Activation Criteria (set by conductor)

The conductor already determined:
- `COMPLEXITY_TIER`: moderate or substantial (trivial never enters autopilot)
- `WORKFLOW_TYPE`: feature, hotfix, refactor, or investigation
- `SKIP_GATES`: whether user opted out of quality gates

## Workflow Templates

### Feature (default for new functionality)

```
1. CONTEXT    [auto]   - Map codebase, gather context
2. DECISION   [auto]   - Validate approach, brainstorm if needed
3. PLANNING   [auto]   - Write implementation plan
   --- CHECKPOINT: Plan Approval ---
4. EXECUTION  [auto]   - Implement via TDD/executing-plans
5. QUALITY    [auto]   - skill-conductor-quality (test-gate + review-gate)
6. SHIP       [human]  - Present diff, request merge approval
   --- CHECKPOINT: Ship Approval ---
```

### Hotfix (urgent fix, minimal ceremony)

```
1. DIAGNOSE   [auto]   - systematic-debugging to identify root cause
2. EXECUTION  [auto]   - Minimal surgical fix + regression test
3. QUALITY    [auto]   - skill-conductor-quality (moderate budget)
4. SHIP       [human]  - Present fix, request merge approval
   --- CHECKPOINT: Ship Approval ---
```

### Refactor (no behavior change)

```
1. BASELINE   [auto]   - Run tests, establish passing baseline
2. EXECUTION  [auto]   - Apply structural changes
3. VERIFY     [auto]   - Run same tests, confirm no regressions
4. QUALITY    [auto]   - skill-conductor-quality (ratchet check critical)
5. SHIP       [human]  - Present diff, request merge approval
   --- CHECKPOINT: Ship Approval ---
```

### Investigation (research only, no code changes)

```
1. EXPLORE    [auto]   - Code search, analysis, documentation review
2. REPORT     [auto]   - Compile findings report
```

## Workflow Type Detection

| Signal | Template |
|--------|----------|
| "urgent", "P1", "hotfix", branch starts with "fix/" or "hotfix/" | Hotfix |
| "refactor", "restructure", "clean up", "no behavior change" | Refactor |
| "investigate", "research", "explore", "understand", "explain" | Investigation |
| Default (new feature, add capability, implement) | Feature |

## State Persistence

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
  user_message_summary TEXT NOT NULL,
  detected_layer TEXT NOT NULL,
  confidence REAL NOT NULL,
  routed_to TEXT NOT NULL,
  overridden INTEGER DEFAULT 0,
  corrected_to TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
```

## Initialization

On activation:
1. Create SQL tables if not exist
2. Generate workflow_id (kebab-case: `feature-auth-system-20260609`)
3. Insert workflow row with phases_json from template
4. Present workflow to user:
   "Autopilot: [type] workflow. Phases: [list]. Checkpoints at: [list]."
5. Use `ask_user` with choices: ["Proceed", "Modify phases", "Abort"]
6. On approval: begin phase 1

## Phase Execution

For each phase:
1. Update phase_log: status='in_progress', attempts++
2. Invoke the appropriate sub-skill for this phase
3. On success: mark done, check for checkpoint, advance
4. On failure: increment attempts, check stuck threshold

### State Integrity Rules

Phase transitions are forward-only. These invariants prevent state manipulation:

1. **No phase rewind:** `current_phase` can only advance to the next phase in
   `phases_json` order. Setting it to a previous phase requires explicit user
   abort + restart (creates a new workflow_id).

2. **QUALITY phase is non-removable:** User can modify phases via "Modify phases"
   at initialization, but QUALITY cannot be removed from any template that includes
   it. User can skip individual reviewers within quality (via --skip-reviews) but
   not the phase itself.

3. **phases_json is immutable after creation:** Once the workflow row is inserted,
   `phases_json` cannot be updated. Phase modifications require aborting and
   creating a new workflow.

4. **Recovery validation:** On session recovery, before resuming, validate:
   - `current_phase` exists in `phases_json`
   - `status` is a valid enum value (running, paused, stuck)
   - Phase log entries are consistent (no completed phases after current_phase)
   If validation fails: present as corrupted, offer fresh restart only.

### Phase-to-Skill Mapping

| Phase | Sub-skill invoked |
|-------|-------------------|
| CONTEXT | `skill-conductor-context` |
| DECISION | `skill-conductor-decision` |
| PLANNING | `writing-plans` (Superpowers) |
| EXECUTION | `skill-conductor-execution` |
| DIAGNOSE | `systematic-debugging` |
| BASELINE | `verification-before-completion` (run tests only) |
| VERIFY | `verification-before-completion` |
| QUALITY | `skill-conductor-quality` |
| EXPLORE | Direct tools (grep, glob, view, bash) |
| REPORT | Direct file creation |
| SHIP | `finishing-a-development-branch` |

## Human Checkpoints

MUST pause at these boundaries. Never proceed without affirmative approval:

| Checkpoint | Trigger | Present to user |
|------------|---------|-----------------|
| Plan Approval | PLANNING -> EXECUTION | Plan artifact, risks, scope estimate |
| Ship Approval | QUALITY -> SHIP | Diff summary, advisory findings, verification status |
| Stuck Escalation | 2x consecutive failure | Error context, what was tried, recovery options |

Use `ask_user` at checkpoints. Choices: proceed, modify, abort.

## Stuck Detection

A phase is stuck when:
- Same phase fails 2x consecutively
- Quality gate returns ESCALATED_BLOCKING with budget exhausted
- No measurable progress after 2 iterations (same error repeated)

On stuck:
1. Set workflow status='stuck'
2. Log error_detail in phase_log
3. Present to user with recovery options:
   - "Fix and retry" (user resolves, then re-invoke autopilot)
   - "Skip this phase" (only for optional phases)
   - "Abort workflow" (mark cancelled)
   - "Try different approach" (restart current phase)

## Progress Reporting

On "status", "progress", or "where are we":

```
Workflow: [type] ([status])
Phase: [current] (step [N]/[total])
Branch: [branch_name]

[x] Phase 1: Context       (done)
[x] Phase 2: Decision      (done)
[>] Phase 3: Execution     (in progress, attempt 1)
[ ] Phase 4: Quality       (pending)
[ ] Phase 5: Ship          (pending - requires approval)
```

## Session Recovery

On session start, the conductor checks for active workflows:

```sql
SELECT workflow_id, workflow_type, current_phase, status
FROM conductor_workflow WHERE status IN ('running', 'paused', 'stuck')
ORDER BY updated_at DESC LIMIT 1;
```

If found: present resume options. If resumed: continue from current_phase.

## Efficiency Rules

- Skip phases that are not applicable (e.g., CONTEXT phase skipped if context
  already established in this session)
- For moderate tier: reduce gate budgets (budget=2 instead of 5)
- For hotfix: skip CONTEXT and DECISION entirely (time-critical)
- Do not re-run phases that already passed in this workflow
- If a phase produces no artifacts (e.g., CONTEXT found everything current),
  mark done and advance without invoking quality gate on empty changesets
