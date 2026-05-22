# Phase 6: Synthesis and Final Report
Purpose: Consolidate findings from all phases, deduplicate, prioritize, and produce the final report.

## Goal

This phase combines the outputs of all earlier phases into one final report. The
job is to reduce duplication, preserve the strongest evidence, rank the work, and
produce a report that makes clear what should be fixed first and why.

The final report should be useful to engineers, designers, reviewers, and future
maintainers. It must disclose gaps, skipped phases, and any limitations that
lower confidence.

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

Gather all available phase outputs:
- Phase 1: context
- Phase 2: standards
- Phase 3: inclusive
- Phase 4: personas, if available
- Phase 5: patterns, if available
- manifest status for every phase
- severity overrides from config, if present

Minimum viable synthesis:
- Phase 1 must exist
- at least one of Phase 2 or Phase 3 must exist

If later phases are missing, continue and disclose the gap near the top of the
report.

## Deduplication Rules

Apply these rules exactly:
- Same file:line + same population: merge into one finding; list all source phases
- Same root cause, different manifestations: group under one heading with sub-findings
- Severity precedence: highest severity wins when phases disagree
- Category precedence: Layer A for WCAG classification, Layer B for inclusive design classification

Additional guidance:
- keep the clearest wording
- keep the strongest citation
- merge population lists rather than duplicating the issue
- preserve systemic framing from Phase 5 when local findings roll up to one root

## Deduplication Workflow

Step 1: normalize findings
- standardize file paths
- standardize severity labels
- standardize population ids
- standardize issue names where useful

Step 2: merge exact duplicates
- same location or artifact
- same population impact
- same root issue

Step 3: group by root cause
- cluster findings caused by one component, token, rule, or convention
- keep sub-findings only when they add useful nuance

Step 4: resolve disagreement
- highest severity wins
- broader population list wins
- stronger evidence wording wins
- contradictions must be disclosed if they cannot be resolved

## Priority Ranking Algorithm

Rank issues in this exact order:
1. Severity (CRITICAL first)
2. Population breadth (affects more populations = higher priority)
3. Systemic scope (design-system-level > component > isolated)
4. Confidence (multiple phases found it > single phase)

Tie-break guidance:
- blocked core flows outrank non-blocking friction within the same severity band
- shared primitives outrank isolated pages when breadth is similar
- multi-phase confirmation outranks speculative single-phase findings

## Severity Overrides

If `.a11y-review.yml` defines severity_overrides, apply them after deduplication
and before final ranking.

Rules:
- only apply overrides to clearly matching issue classes
- do not hide clear blocker evidence
- if an override materially changes ranking, note that in the report

## Report Assembly

Use this exact structure:

```markdown
# Accessibility & Inclusive Design Review (Deep Audit)
Generated: YYYY-MM-DD HH:MM
Scope: [full codebase | component: X]
Platform: [detected]

## Executive Summary
- Critical: N | High: N | Medium: N | Low: N
- Populations affected: [list]
- Worst-affected population: [id] (N blocking issues)
- Phases completed: N/6 (list any skipped with reason)
- Systemic patterns found: N

## Layer A: Compliance Findings
### CRITICAL
| # | File:Line | Issue | WCAG | Population | Fix |
### HIGH
(same table)
### MEDIUM / LOW

## Layer B: Inclusive Design Findings
### CRITICAL
| # | File:Line | Issue | Category | Population | Recommendation |
### HIGH / MEDIUM / LOW

## Persona Simulation Results
### Summary Table
| Persona | Flows Tested | Pass | Friction | Blocked |
### Per-Persona Detail
(findings unique to persona simulation)

## Anti-Patterns Detected
| Pattern | Occurrences | Severity | Recommendation |

## Cross-Platform Issues (if multi-platform)
| Issue | Platforms | Root Cause | Fix Scope |

## Recommendations (Priority-Ranked)
1. [CRITICAL] Fix X because Y (affects: populations)
2. ...
```

## Final Report Frontmatter

The final report must begin with YAML frontmatter containing at least:
- tool
- version
- mode: deep
- platform
- scope
- severity_counts
- populations_affected

Keep the frontmatter accurate and machine-readable.

## Executive Summary Rules

The executive summary must quickly answer:
- how severe is the overall situation?
- which populations are most affected?
- how complete was the audit?
- are the worst issues isolated or systemic?
- what should be fixed first?

Required elements:
- severity counts
- affected population list
- worst-affected population with blocking issue count
- phase completion count with skipped-phase disclosure
- systemic pattern count

If platform support was partial, say so here.

## Layer Construction Rules

### Layer A
Use Layer A for standards and compliance findings such as:
- semantics
- accessible names
- headings and landmarks
- focus order and keyboard reachability
- text alternatives
- name-role-value exposure
- state and error announcement
- table semantics

### Layer B
Use Layer B for inclusive design findings such as:
- ambiguity
- interruption recovery
- timing pressure
- motion overload
- weak hierarchy
- unclear state
- resume difficulty
- inconsistent or surprising behavior

If a finding exists in both layers, keep the canonical classification in Layer A
and include a Layer B entry only if it adds distinct inclusive-design value.

## Persona Simulation Results Rules

Preserve what Phase 4 contributes uniquely.
Do not repeat every persona finding if it is already covered elsewhere unless the
persona perspective adds new blocker context.

Required content:
- summary table by persona
- skipped persona disclosure with reason
- blocked flow counts
- unique or especially vivid persona findings

## Anti-Patterns Section Rules

Summarize Phase 5 concisely.
For each pattern, include:
- pattern name
- occurrence count
- final severity
- recommendation focused on the root fix

If the pattern comes from a shared component, say so directly.

## Cross-Platform Issues Rules

Include this section only when relevant.
Use it for shared logic, tokens, or conventions that affect more than one
platform. Omit it entirely when not needed.

## Gap Detection

Run these checks explicitly:
- Which populations have ZERO findings? (suspicious)
- Which Layer B categories have ZERO findings? (may indicate shallow review)
- Were any phases skipped? Note impact on completeness.

Interpretation guidance:
- zero findings for a population may mean limited evidence, not clean coverage
- zero Layer B categories may indicate an overly compliance-only review
- skipped phases should lower confidence and be named directly

## The 4-Pass Loop Applied to Report Quality

Apply this exact loop:
- ANALYZE: Assemble report from phase outputs
- CRITIQUE: Is anything contradictory? Missing populations? Over-represented categories?
- REVISE: Fix contradictions, note gaps, adjust priority ranking
- VERIFY: All required sections present, severities consistent, no duplicates remain

### ANALYZE
- gather all findings
- normalize terminology
- map each finding to the correct layer
- compute counts and draft ranking

### CRITIQUE
- look for contradictions across phases
- look for missing populations
- look for duplicate entries across layers
- check whether the ranking reflects real user harm

### REVISE
- merge duplicates
- fix contradictions
- tighten wording
- add skipped-phase caveats
- rebalance recommendation order

### VERIFY
- all required sections are present
- severity counts match the tables
- population ids are canonical
- no duplicates remain
- output is ASCII-safe only
- no em-dashes appear

## Chat Summary Generation

After writing the final report, generate this chat summary:

```text
## A11y Deep Audit Summary

CRITICAL: N | HIGH: N | MEDIUM: N | LOW: N

Top Issues:
1. [CRITICAL] description (populations)
...

Systemic Patterns: N found (N in shared components)
Personas: N blocked flows, N friction points

Populations Most Affected: id (N issues), id (N issues)

Full report: <path>
```

Chat summary rules:
- keep it concise
- include skipped phases or personas if any
- mention partial platform support if relevant
- point to the final report path

## Cleanup Instructions

After writing the final report to `<session-folder>/files/`:
- Delete `<session-folder>/scratch/a11y-review/` directory
- The report in `files/` is the permanent artifact

Cleanup rules:
- verify the report exists before deleting scratch data
- do not delete scratch if report generation failed
- cleanup happens after report verification and chat summary generation

## Final Validation Checklist

Before declaring completion, confirm:
- final report exists in the session files directory
- required frontmatter is present
- executive summary is complete
- Layer A and Layer B are both present
- persona section is present or skipped clearly
- anti-pattern summary is present when Phase 5 ran
- cross-platform section is included only if relevant
- recommendations are priority-ranked
- gaps and skipped phases are disclosed
- output is ASCII-safe only
- no em-dashes appear
- severity labels are uppercase only

## Exit Condition

This phase is complete when the final report is written, deduplicated, ranked,
quality-checked, summarized for chat, and the scratch directory is removed only
after report verification succeeds.
