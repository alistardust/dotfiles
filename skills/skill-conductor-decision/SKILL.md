---
name: skill-conductor-decision
description: Decision layer guidance for the skill conductor. Helps choose the right gstack decision skill based on what kind of thinking is needed.
---

# Decision Layer: Choosing the Right Thinking Tool

You were routed here because the user needs to DECIDE something before building.
Your job: ground in reality first, then pick the right decision skill and invoke it.

## Reality Grounding Gate (before choosing a skill)

Before invoking any decision skill, apply the "Ground in Reality" pre-decision trigger.
(On fast-path per the main conductor, this reduces to a quick pattern check.)

1. **Find real data.** If the task involves processing or transforming existing content,
   locate a representative real example. Search the codebase, project files, test
   fixtures (preferring real over synthetic). This is the system's job first; ask the
   user only if you genuinely cannot find appropriate data.

2. **Present it.** Show the user the actual data that will be processed. Anchor the
   conversation in what exists, not what's imagined.

3. **Validate against it.** Every design proposal must be checked: "Does this handle
   the real case?" If it doesn't: the design is wrong, not the data.

4. **Flag new formats.** If the design introduces ANY new syntax or structure the real
   data doesn't already use, flag it per the Adaptation Direction invariant.

If no existing data (greenfield): research analogous real-world examples. If none
found: surface that the design is ungrounded. Do not design against imagined inputs.

## Decision Tree

```
Is this a brand new idea or feature?
  YES --> Is it a startup/product idea?
            YES --> invoke office-hours
            NO  --> invoke brainstorming
  NO  --> Is there an existing plan/design doc to review?
            YES --> What kind of review?
                      Scope/strategy only     --> invoke plan-ceo-review
                      Architecture/code only  --> invoke plan-eng-review
                      UI/UX/visual only       --> invoke plan-design-review
                      Security only           --> invoke cso
                      2+ review types needed  --> invoke autoplan
                      All / comprehensive     --> invoke autoplan
            NO  --> Is the user unsure what to build?
                      YES --> invoke office-hours
                      NO  --> invoke brainstorming
```

**Multi-axis rule:** If the request mentions two or more review dimensions
(e.g., "security and architecture review"), invoke `autoplan` rather than
picking one reviewer. Autoplan runs all relevant reviewers sequentially.

## Skill Descriptions

### office-hours
**When:** New ideas, unclear requirements, stress-test assumptions.
**Suggested tier:** frontier (creative reasoning, multi-turn Socratic questioning)
**Output:** Design doc in ~/.gstack/projects/

### brainstorming (Superpowers)
**When:** Lighter ideation, refining existing concept, exploring options.
**Suggested tier:** frontier (creativity benefits from strongest available model)
**Output:** Design spec in docs/superpowers/specs/

### plan-ceo-review
**When:** Plan needs scope/strategy validation. "Is this ambitious enough?"
**Suggested tier:** frontier (ambiguity, strategy, 10-star thinking)
**Output:** Review log, plan updates

### plan-eng-review
**When:** Plan needs architecture, test coverage, performance review.
**Suggested tier:** reasoning (system-level reasoning, interactive)
**Output:** Review log, test plan

### plan-design-review
**When:** Plan has UI/UX components needing visual/interaction review.
**Suggested tier:** reasoning (design judgment)
**Output:** Review log, design scores

### autoplan
**When:** Full review gauntlet without intermediate questions.
**Suggested tier:** Per-reviewer (each uses its own tier from the review-gate Model Dispatch Table)
**Output:** Unified review report

### cso
**When:** Security-focused review (secrets, supply chain, OWASP, STRIDE).
**Suggested tier:** reasoning (attack path reasoning; fast tier misses subtle chains)
**Output:** Security report with findings

## After Choosing

Invoke the chosen skill using the Skill tool. Pass `COMPLEXITY_TIER` from the
conductor if available; it informs model selection for subagents the skill may
dispatch. Let the skill run its own flow.
