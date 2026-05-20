---
name: skill-conductor-decision
description: Decision layer guidance for the skill conductor. Helps choose the right gstack decision skill based on what kind of thinking is needed.
---

# Decision Layer: Choosing the Right Thinking Tool

You were routed here because the user needs to DECIDE something before building.
Your job: pick the right decision skill and invoke it.

## Decision Tree

```
Is this a brand new idea or feature?
  YES --> Is it a startup/product idea?
            YES --> invoke office-hours
            NO  --> invoke brainstorming
  NO  --> Is there an existing plan/design doc to review?
            YES --> What kind of review?
                      Scope/strategy    --> invoke plan-ceo-review
                      Architecture/code --> invoke plan-eng-review
                      UI/UX/visual      --> invoke plan-design-review
                      Security          --> invoke cso
                      All of the above  --> invoke autoplan
            NO  --> Is the user unsure what to build?
                      YES --> invoke office-hours
                      NO  --> invoke brainstorming
```

## Skill Descriptions

### office-hours
**When:** New ideas, unclear requirements, need to stress-test assumptions.
**What it does:** YC-style questioning (6 forcing questions for startups, generative
questions for builders). Produces a design doc with premises, approaches, and
recommended path.
**Token cost:** High (~2000+ tokens loaded, multi-turn conversation)
**Output:** Design doc in ~/.gstack/projects/

### brainstorming (Superpowers)
**When:** Lighter ideation, refining an existing concept, exploring options.
**What it does:** Explores intent, proposes approaches, presents design for approval.
**Token cost:** Medium (~800 tokens)
**Output:** Design spec in docs/superpowers/specs/

### plan-ceo-review
**When:** Existing plan needs scope/strategy validation. "Is this ambitious enough?"
**What it does:** Challenges premises, proposes scope expansion or reduction,
finds the 10-star product version.
**Token cost:** High (~1500 tokens)
**Output:** Review log, plan file updates

### plan-eng-review
**When:** Existing plan needs architecture, test coverage, performance review.
**What it does:** Reviews architecture, code quality, test gaps, performance.
Interactive: one issue at a time with recommendations.
**Token cost:** High (~2000 tokens)
**Output:** Review log, test plan, coverage diagram

### plan-design-review
**When:** Plan has UI/UX components that need visual/interaction review.
**What it does:** Rates design dimensions, proposes improvements.
**Token cost:** Medium (~1000 tokens)
**Output:** Review log, design scores

### autoplan
**When:** Want the full review gauntlet without answering 15-30 intermediate questions.
**What it does:** Runs CEO, eng, and design reviews sequentially with auto-decisions.
**Token cost:** Very high (sum of all above)
**Output:** All review logs, unified report

### cso
**When:** Security-focused review needed (secrets, supply chain, OWASP, STRIDE).
**What it does:** Infrastructure-first security audit with active verification.
**Token cost:** High (~1500 tokens)
**Output:** Security report with findings

## After Choosing

Invoke the chosen skill using the Skill tool. The skill will take over from here.
Do not provide additional routing guidance; let the skill run its own flow.
