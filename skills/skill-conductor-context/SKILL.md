---
name: skill-conductor-context
description: Context layer guidance for the skill conductor. Helps establish and maintain project context using GSD artifacts to prevent context rot.
---

# Context Layer: Anchoring Project Context with GSD

You were routed here because the project needs context anchoring before work
can proceed effectively. Context rot (quality degradation as context windows
fill) is the problem GSD solves.

## When Context Work Is Needed

- **New project:** No PROJECT.md, REQUIREMENTS.md, or ROADMAP.md exists
- **Stale context:** STATE.md not updated in 7+ days
- **Session boundary:** Starting a new session on existing work
- **Scope shift:** Requirements changed, need to re-anchor
- **Long chain:** Multiple sessions of work, context drifting

## Decision Tree

```
Does the project have GSD artifacts (PROJECT.md, REQUIREMENTS.md, ROADMAP.md)?
  NO  --> Is there existing code?
            YES --> invoke gsd-map-codebase, then gsd-new-project
            NO  --> invoke gsd-new-project
  YES --> Is there a specific phase being worked on?
            YES --> Is the phase planned?
                      NO  --> invoke gsd-discuss-phase, then gsd-plan-phase
                      YES --> invoke gsd-execute-phase
            NO  --> Are decisions needed before planning?
                      YES --> invoke gsd-discuss-phase
                      NO  --> invoke gsd-plan-phase
```

## GSD Core Skills

### gsd-new-project
**When:** Starting fresh. No GSD artifacts exist yet.
**What it does:** Questions you about the project, researches context, produces
REQUIREMENTS.md and ROADMAP.md. You approve, then you are ready to build.
**Prerequisite:** If code exists, run gsd-map-codebase first.
**Output:** PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md

### gsd-discuss-phase [N]
**When:** A phase exists in the roadmap but implementation details are unclear.
**What it does:** Captures your decisions about layouts, API shapes, error handling,
data structures. Feeds directly into planning.
**Output:** CONTEXT.md (per-phase implementation decisions)

### gsd-plan-phase [N]
**When:** Phase is discussed, ready to be planned for execution.
**What it does:** Research, plan, and verify in a loop until plans pass.
Each plan is small enough to execute in a fresh context window.
**Output:** Phase plan files

### gsd-execute-phase [N]
**When:** Phase is planned, ready to build.
**What it does:** Executes plans in parallel waves. Each executor gets fresh context.
Each task gets its own atomic commit.
**Output:** Implemented code with clean git history

### gsd-phase
**When:** Need to manage phase state (advance, check status).
**What it does:** Phase lifecycle management.

## Context Artifacts (what GSD maintains)

| File | Purpose | Created by |
|------|---------|-----------|
| PROJECT.md | What the project is (vision, goals) | gsd-new-project |
| REQUIREMENTS.md | Scope (what to build, what not to) | gsd-new-project |
| ROADMAP.md | Where you are going (phased plan) | gsd-new-project |
| STATE.md | Current position, active decisions | Updated continuously |
| CONTEXT.md | Per-phase implementation decisions | gsd-discuss-phase |

## Integration with Other Layers

After context is anchored:
- **If requirements are clear:** Route to execution layer (Superpowers)
- **If approach needs validation:** Route to decision layer (gstack reviews)
- **If both:** Decision first (validate approach), then execution

## After Choosing

Invoke the chosen GSD skill. Let it run its own flow. GSD skills are
self-contained and will guide the conversation from here.
