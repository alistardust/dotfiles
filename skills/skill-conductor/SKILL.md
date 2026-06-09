---
name: skill-conductor
description: >
  Lean workflow router with autopilot dispatch. Scores intent confidence, routes to
  the right layer (Context/Decision/Execution), and activates autopilot for multi-phase
  work. Quality gates fire at transitions. Efficiency-first: load only what you need.
---

# Skill Conductor

You are a workflow router. Detect intent, score confidence, route to one sub-skill.
For multi-phase work, activate autopilot. You do NOT do implementation work.

**Supersedes `using-superpowers`.** Do not also invoke using-superpowers.

## Efficiency Principles (apply everywhere)

These rules govern the entire skill-conductor system and all sub-skills:

1. **Load only what you need.** Do not invoke a sub-skill unless its logic is required.
   Simple routing does not need the autopilot skill. A spec review does not need the
   test gate. Only the quality layer invokes test-gate and review-gate.

2. **Parallel over sequential.** When two operations are independent and do not
   mutate shared state, run them in parallel (e.g., cross-ecosystem review dispatch,
   multiple reviewer agents within a tier). Exception: test-gate and review-gate run
   sequentially (test first) because review-gate's fix agent may modify source files.

3. **Incremental over full.** After a fix iteration, only re-review the changed
   chunks/files. Do not re-run the entire review on unchanged code. Cache results
   by content hash where possible.

4. **Early termination.** If a CRITICAL finding is detected, skip remaining reviewers
   and escalate immediately. Do not spend budget discovering more issues when the
   first one blocks everything.

5. **Proportional effort.** Standards are uniform (all findings block). Effort scales:
   - trivial: inline check, no subagents, no auto-fix loop
   - moderate: single-tier review, budget=2, single ecosystem
   - substantial: full gate, both tiers, cross-ecosystem, budget=5

6. **Cheapest correct model.** Use fast-tier models for pattern matching, checklists,
   mechanical fixes. Use reasoning-tier for analysis. Use frontier only for genuine
   ambiguity or creative decisions. Never use frontier for a task fast-tier handles.

7. **Skip redundant phases.** If context is already established (SESSION has recent
   context work), skip the CONTEXT phase in autopilot. If a plan already exists
   and is current, skip PLANNING. Do not re-do work that was done this session.

8. **Diff-scoped gates.** Quality gates scope to `changeset_scope` (files actually
   changed), not the entire repository. Review only what changed.

## When to Skip (do NOT route)

- Single-file edits, quick lookups, one-line fixes: just do them directly.
- User explicitly names a skill: invoke that skill directly, bypass conductor.
- You were dispatched as a subagent: skip entirely.
- Trivial complexity with no active workflow state: handle inline, no orchestration.

## Session Recovery (check on session start)

```sql
SELECT workflow_id, workflow_type, current_phase, status
FROM conductor_workflow WHERE status IN ('running', 'paused', 'stuck')
ORDER BY updated_at DESC LIMIT 1;
```

If active workflow found: present resume options via `ask_user`. Otherwise proceed.

## Complexity Assessment

| Tier | Signals | Action |
|------|---------|--------|
| **trivial** | Single file, config/docs, no new behavior | Handle inline. No routing. |
| **moderate** | Few files, bounded scope, extends patterns | Route to layer. Autopilot optional. |
| **substantial** | Many files, new architecture, cross-cutting | Route + activate autopilot. |

## Routing: Confidence-Scored Intent Detection

### Signal extraction

**Message signals:**
- Direct skill invocation (e.g., "gsd-plan-phase", "/code-audit"): confidence 1.0
- Strong layer verbs ("brainstorm", "audit" -> Decision; "build", "implement" -> Execution): 0.8
- Moderate verbs ("update", "change", "work on"): 0.5
- Ambiguous or compound requests: 0.3

**Environmental boosts (+/- 0.1 each):**
- Active feature branch: +0.1 Execution
- Uncommitted changes in git: +0.1 Execution
- Existing plan artifact: +0.1 Execution
- `.planning/` missing files: +0.1 Context
- Failing tests in recent output: +0.1 Execution (debug)
- Stale STATE.md (7+ days): +0.1 Context

### Threshold behavior

| Confidence | Action |
|------------|--------|
| >= 0.8 | Auto-route. One-line explanation, invoke sub-skill. |
| 0.5 - 0.79 | Propose route. Use `ask_user` for confirmation. |
| < 0.5 | Present options. Ask which layer. |

### Log routing decision

```sql
INSERT INTO routing_log (user_message_summary, detected_layer, confidence, routed_to, overridden)
VALUES (?, ?, ?, ?, 0);
```

If user overrides: update `overridden=1, corrected_to=?`

### Opt-out detection

"skip reviews", "no reviews", `--skip-reviews`, `--no-gate` in current message:
set `SKIP_GATES=true` for this invocation.

## Layer Routing Rules

### Priority 0: Custom Skills (confidence 1.0)

| Signal | Route to |
|--------|----------|
| "a11y review", "accessibility check" | `a11y-review` |
| "full a11y audit", "deep accessibility" | `a11y-review-deep` |
| "code audit", "audit this repo" | `code-audit` |

### Priority 1: Context Layer -> `skill-conductor-context`

ALL must be true:
- GSD repo (has `.planning/`)
- Missing/stale artifacts (no PROJECT.md, no REQUIREMENTS.md, STATE.md 7+ days)
- Setup intent (not review intent)

### Priority 2: Decision Layer -> `skill-conductor-decision`

ANY: "idea", "what if", "should I", "brainstorm", "review this", ambiguous, review intent

### Priority 3: Execution Layer -> `skill-conductor-execution`

ANY: "build", "implement", "fix", "ship", plan exists, default fallback

**GSD exception:** `.planning/*/PLAN.md` routes to Context (`gsd-execute-phase`)

### Multi-step detection -> `skill-conductor-autopilot`

Compound request ("brainstorm then build", "plan and implement X", "build from scratch"):
activate autopilot with detected workflow type.

## Conflict Resolution

1. Context wins if full predicate satisfied
2. Decision wins if ambiguous or review intent
3. Execution wins if plan exists and building intent
4. Ambiguous after scoring: ask user

## Autopilot Activation

Invoke `skill-conductor-autopilot` when:
- User explicitly requests ("autopilot", "end-to-end", "start to finish")
- Multi-step request detected
- Substantial tier with clear feature/hotfix/refactor intent
- User says "build X" where X requires multiple phases

Pass to autopilot: `COMPLEXITY_TIER`, `WORKFLOW_TYPE`, `SKIP_GATES`

## After Routing (single-phase, no autopilot)

1. State layer, confidence, and reason (one line)
2. Pass `COMPLEXITY_TIER` to sub-skill
3. Invoke sub-skill
4. **Quality gate (post-artifact):** When sub-skill produces an artifact AND
   `SKIP_GATES` is not set, invoke `skill-conductor-quality`:
   - trivial: lightweight mode (inline findings, no auto-fix)
   - moderate: budget=2, single-tier
   - substantial: full gate (test + review, both tiers, cross-ecosystem)
5. If `SKIP_GATES`: log and proceed

### Gate trigger mapping

| Transition | `gate_phase` | Key inputs |
|-----------|-------------|------------|
| Spec produced | `post-spec` | artifact paths, complexity |
| Plan produced | `post-plan` | artifact paths, complexity |
| Execution complete | `post-execution` | changeset, complexity, work_type, base_ref |
| MR opened | `mr` | changeset, complexity, base_ref, head_ref |

### Artifact detection

- **post-spec:** `docs/superpowers/specs/*`, `~/.gstack/projects/*`, explicit "spec"
- **post-plan:** `docs/superpowers/plans/*`, `plan.md`, `.planning/*/PLAN.md`
- **post-execution:** Execution sub-skill declares completion; code committed
- **mr:** `gh pr create` ran, or PR URL in output

## Anti-Recursion

If invoked BY a sub-skill, do NOT re-invoke the caller. Route and stop.

## Fallback

- Skill not installed: skip, suggest next-best.
- No signals, confidence < 0.5: ask user.
- User override always wins (confidence 1.0).

## Skill Registry (reference only)

### Layers

| Layer | Invoke | Key skills |
|-------|--------|-----------|
| Context | `skill-conductor-context` | gsd-new-project, gsd-map-codebase, gsd-discuss-phase, gsd-plan-phase, gsd-execute-phase |
| Decision | `skill-conductor-decision` | office-hours, brainstorming, plan-ceo/eng/design-review, autoplan, cso |
| Execution | `skill-conductor-execution` | writing-plans, executing-plans, TDD, verification, parallel-agents, debugging, ship |
| Quality | `skill-conductor-quality` | Wraps test-gate + review-gate. Zero-debt enforcement. |
| Autopilot | `skill-conductor-autopilot` | State machine, workflow templates, checkpoints, recovery |

### Model selection (cheapest correct)

| Task type | Suggested tier |
|-----------|---------------|
| Routing, search, checklists, mechanical fixes | fast |
| Security, architecture, judgment, plan writing | reasoning |
| Strategy, ambiguity, creativity | frontier |

Cross-ecosystem dispatch: substantial tier only, at blocking gates.

## Feedback Loop

On session start (after recovery check), analyze routing corrections to improve
future confidence scores:

```sql
SELECT detected_layer, corrected_to, COUNT(*) as corrections
FROM routing_log
WHERE overridden = 1
GROUP BY detected_layer, corrected_to
ORDER BY corrections DESC
LIMIT 10;
```

If corrections exist, apply routing bias adjustments:
- Frequent override pattern (3+ corrections for same detected->corrected pair):
  Reduce confidence for that detection pattern by 0.1
- If user consistently overrides a Priority 2 detection to Priority 3:
  Add that signal to the Execution layer's keyword set
- Log adjustment: "Routing bias: [pattern] confidence reduced based on [N] corrections"

This is advisory. The feedback loop does NOT auto-modify skill files; it adjusts
in-session routing weights only. Persistent changes require explicit skill updates.
