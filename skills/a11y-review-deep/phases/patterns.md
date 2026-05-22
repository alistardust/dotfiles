# Phase 5: Anti-Pattern Detection
Purpose: Detect recurring inaccessible patterns, systemic design issues, and problematic defaults that propagate across the codebase.

## Goal

This phase identifies recurring accessibility failures and traces them to their
likely root. The unit of analysis is the pattern, not the isolated defect. A good
Phase 5 output should tell the reader which inaccessible defaults will continue
to spread until the underlying component, token, layout rule, or review practice
is corrected.

## Canonical References

Populations:
- blind-sr
- keyboard-only
- low-vision
- motor-impaired
- deaf-hoh
- adhd-distracted
- autism-ambiguity

Severity:
- CRITICAL
- HIGH
- MEDIUM
- LOW

Platform enum:
- web
- ios
- android
- desktop
- cross-platform-mobile
- design-system
- multi-platform
- unknown

## Required Inputs

Use as many of these as are available:
- Phase 1 context summary
- Phase 2 standards findings
- Phase 3 inclusive findings
- Phase 4 persona findings, if available
- repository structure for shared components
- design system docs, stories, tokens, or primitives

Phase 4 is optional input. Missing persona data lowers confidence but does not
block this phase.

## Core Detection Lens

Keep asking:
- Is this issue repeated in multiple files or flows?
- Does it originate in a shared component or shared rule?
- Would one upstream fix remove many downstream defects?
- Is the root cause code, design, copy, or process?
- Does persona evidence reinforce the pattern?

## Pattern Categories to Detect

Use this minimum table during analysis.

| Pattern | Description | Example | Severity |
|---------|-------------|---------|----------|
| Div-as-button | Clickable divs/spans without role or keyboard support | `<div onClick={...}>` | HIGH |
| Placeholder-as-label | Form inputs with placeholder but no visible label | `<input placeholder="Email">` | HIGH |
| Color-only communication | Status/state conveyed only through color | Red/green without text | HIGH |
| Icon-only actions | Interactive icons without text alternative | Gear icon with no label | MEDIUM |
| Tooltip-gated info | Critical info only visible on hover (inaccessible to touch/keyboard) | Hover-to-reveal help text | MEDIUM |
| Focus suppression | outline:none or outline:0 without replacement | `*:focus { outline: none }` | CRITICAL |
| Auto-playing media | Audio/video that plays without user initiation | Autoplay video | MEDIUM |
| Infinite scroll | Content loading without clear boundaries or alternative navigation | No pagination fallback | MEDIUM |
| Modal without trap | Dialog that does not trap and return focus | Open modal, Tab leaves it | HIGH |
| Time-limited actions | Operations that expire without warning or extension | Session timeout without alert | HIGH |
| Drag-only interaction | Actions requiring drag with no keyboard/click alternative | Drag-to-reorder only | CRITICAL |
| Hidden skip navigation | Skip links present but visually hidden AND never revealed on focus | `.sr-only` skip link that stays hidden | MEDIUM |
| Inconsistent navigation | Different nav patterns on different pages | Nav order changes per page | MEDIUM |

You may add other patterns when evidence is strong and the pattern is materially
harmful.

## Detection Strategy

Review patterns at three levels:

Level 1: direct code patterns
- repeated markup shapes
- repeated selectors or utilities
- repeated component names
- repeated accessibility workarounds

Level 2: interaction patterns
- same modal failure across surfaces
- same keyboard gap across widgets
- same layout breakage across routes

Level 3: design and governance patterns
- same ambiguous copy convention
- same notification behavior without pause or control
- same token usage causing contrast or visibility issues

## Design System Level Detection

Apply these rules exactly:
- Same anti-pattern in a shared component = systemic issue
- Count occurrences across the codebase
- If in a base component: multiply severity (affects everything built on it)
- Recommend fixing at the component level, not per-instance

Additional guidance:
- shared primitives outrank isolated page bugs
- wrapper components can be root components if they spread the issue
- utilities, mixins, and tokens can also be propagation roots
- name the root component, helper, token, or rule whenever possible

## Occurrence Counting Rules

Count conservatively.

Preferred model:
- count the root component definition
- count known downstream usages when identifiable
- avoid double counting the same issue through imports
- use "at least N" when exact usage is uncertain
- do not count dead code or comments as shipped occurrences

## Severity Adjustment Guidance

Escalate severity when:
- the pattern appears in a shared primitive
- the pattern blocks more than one population
- the pattern affects multiple core flows
- the pattern is difficult for teams to override safely
- earlier phases already surfaced many local instances

Do not escalate based on repetition alone. Repetition must correspond to real harm.

## The 4-Pass Loop

Run this exact loop:
- ANALYZE: Detect patterns, count occurrences, classify
- CRITIQUE: Are these real patterns or coincidence? Is the evidence strong? Am I missing patterns?
- REVISE: Consolidate, adjust confidence, add missed patterns
- VERIFY: Significance check (is this actually harmful or just different?)

### ANALYZE
- group repeated findings
- identify likely roots
- note affected populations and flows
- assign preliminary severity

### CRITIQUE
- test whether grouped issues are truly related
- challenge weak evidence
- look for a deeper shared cause
- compare with persona feedback when available

### REVISE
- merge near-duplicate pattern names
- split overly broad buckets
- tighten counts
- elevate design-system origins

### VERIFY
- confirm material user harm
- confirm severity matches impact
- confirm counts are not inflated
- confirm fix advice targets the root

## Dark and Coercive Pattern Detection

Check for these patterns explicitly:
- Confirm shaming (making the accessible option feel negative)
- Hidden dismiss controls (hard to close, especially for motor-impaired)
- Forced continuity (difficult to cancel/unsubscribe)
- Misdirection (visual hierarchy misleading about primary action)

For each confirmed case, explain:
- what the pattern is
- where it appears
- why it is harmful
- which populations are most affected
- what safer alternative should replace it

Do not overstate intent. Focus on impact and design effect.

## Population Mapping Guidance

Useful default mappings:
- Div-as-button: keyboard-only, blind-sr, motor-impaired
- Placeholder-as-label: blind-sr, low-vision, adhd-distracted
- Color-only communication: low-vision, blind-sr, autism-ambiguity
- Focus suppression: keyboard-only, low-vision
- Drag-only interaction: keyboard-only, motor-impaired
- Hidden dismiss controls: motor-impaired, adhd-distracted, autism-ambiguity

These mappings are guides, not limits.

## Output Format

The phase output must use this structure:

```markdown
## Status: COMPLETE

### Systemic Patterns
| Pattern | Occurrences | Files | Severity | Root Component |
|---------|-------------|-------|----------|----------------|

### Isolated Instances
| Pattern | File:Line | Severity | Population | Fix |

### Dark/Coercive Patterns
(if any detected)

### Design System Propagation
(patterns that originate in shared components)
```

## Output Rules

### Systemic Patterns
Use this section for repeated or upstream-rooted issues.
Always identify the most likely root component or shared rule.

### Isolated Instances
Use this section for useful one-off examples that should remain visible even if
they do not form a systemic pattern.

### Dark/Coercive Patterns
Include this section only when evidence exists. If none are found, say so briefly.

### Design System Propagation
Describe origin, spread, and why local patching would be wasteful.

## Completion Checklist

Before marking Phase 5 complete, confirm:
- the required pattern table was considered in full
- systemic issues are separated from isolated instances
- shared-component propagation is explicit
- the 4-pass loop was actually applied
- dark/coercive patterns were checked
- output includes `## Status: COMPLETE`
- output is ASCII-safe only
- no em-dashes appear
- severity labels are uppercase only

## Exit Condition

This phase is complete when the output clearly distinguishes recurring patterns
from isolated defects, identifies propagation roots, and gives synthesis a clean
systemic view of the codebase.
