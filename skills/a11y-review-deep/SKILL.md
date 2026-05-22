---
name: a11y-review-deep
version: "1.0.0"
description: >
  Comprehensive read-only accessibility audit orchestrator for full applications, codebases, and design systems. Runs six phases by loading internal phase docs from its own phases/ directory, tracks state in a session manifest, and writes a consolidated report to the session files folder.
---

# A11y Review Deep

Comprehensive read-only accessibility audit for a full codebase, application, or component library. This skill orchestrates six phases, loads one internal phase document at a time, maintains resumable state in a manifest file, and produces a single deep accessibility report in the session workspace.

## When to Use This Skill

Use this skill when the request involves:
- Auditing a full application or major frontend subsystem for accessibility
- Performing a comprehensive accessibility review across many screens or flows
- Auditing a design system, component library, or shared UI primitives
- Assessing inclusive UX risks, keyboard support, semantics, and assistive tech fit
- Producing a deep accessibility report for a repository, not just a diff
- Any request like "audit this app for accessibility", "deep a11y review", "full accessibility audit", or "design system accessibility review"

Do NOT use this skill for:
- Reviewing a PR or diff; use the a11y-review lite path instead
- Repositories with no meaningful UI surface or user interaction model
- Backend-only, CLI-only, library-only, or infrastructure-only codebases
- Quick spot checks where a broad deep audit would be disproportionate

## Read-Only Contract

This skill never modifies the target repository. Specifically:
- It does NOT edit source files, config files, dependencies, or git state
- It does NOT create artifacts inside the target repository
- It writes working state to the session scratch folder only
- It writes the final report to the session files folder only
- It may read repository files, configs, and docs needed for analysis
- It always prefers a partial report over no report

## V1 Platform Scope

Fully supported:
- `web`
- `design-system`

All other detected or configured platform values produce a shared-logic-only review. In that mode, the audit may assess content structure, semantics in source, tokens, shared patterns, and design system risks, but must not imply full runtime accessibility coverage.

Multi-platform per-platform segmentation (running Phases 2-5 once per detected platform) is deferred to V2. In V1, the audit runs a single pass regardless of how many platforms are detected; findings are tagged with the relevant platform but phases are not repeated.

## Early Exit: No Reviewable UI Surfaces

If Phase 1 determines there are no UI-relevant files in scope (e.g., the target contains only backend code, CLI utilities, or infrastructure), write a short report explaining why, skip remaining phases, and produce a partial report noting: "No reviewable UI surfaces found in scope. This skill is designed for code with user-facing interfaces. Consider narrowing scope or using a different review tool."

## Internal Architecture

This skill is an orchestrator. It resolves its own install location, then reads internal phase docs from `phases/` on demand.

Required internal phase docs:
- `phases/context.md`
- `phases/standards.md`
- `phases/inclusive.md`
- `phases/personas.md`
- `phases/patterns.md`
- `phases/synthesis.md`

Rules:
- These docs are internal, not independently installable skills
- Users do not invoke them directly
- The orchestrator loads phase docs one at a time
- It must NOT preload all phase docs into context at once

## Phase Execution Model

```text
Phase 1 (Context)     --sequential-->
Phase 2 (Standards)   --sequential-->
Phase 3 (Inclusive)   --sequential-->
Phase 4 (Personas)    --parallel subagents-->
Phase 5 (Patterns)    --sequential-->
Phase 6 (Synthesis)   --sequential--> REPORT
```

Operational rules:
- Phases 1, 2, 3, 5, and 6 execute sequentially
- Phase 4 runs after Phase 3 and dispatches persona subagents in parallel
- Phase 4 results are optional for later phases, not required
- Every phase updates the manifest before start and after finish
- If a phase fails, retry exactly once before marking it skipped

## Invocation

Input:
- Optional target path or audit scope
- Everything else is auto-detected or read from config

Output:
- `<session-folder>/files/a11y-review-deep-<repo>-<target-slug>-<date>.md`

Resolve `<session-folder>` from the `<session_context>` system block. Do not guess or hardcode it.

Filename parts:
- `<repo>`: repository basename
- `<target-slug>`: sanitized scope or target path label
- `<date>`: `YYYY-MM-DD`

If no narrower scope was provided, use the repository root and a slug such as `repo-root`.

## State Management

All state lives under:

```text
<session-folder>/scratch/a11y-review/
```

Create and maintain:
- `manifest.json`
- phase output files
- persona output files as needed

### Manifest Contract

Create `manifest.json` at audit start with this exact shape:

```json
{
  "version": "1.0.0",
  "started_at": "ISO8601",
  "platform": "web",
  "scope": "codebase",
  "phases": {
    "context": { "status": "pending", "output": null },
    "standards": { "status": "pending", "output": null },
    "inclusive": { "status": "pending", "output": null },
    "personas": { "status": "pending", "output": null },
    "patterns": { "status": "pending", "output": null },
    "synthesis": { "status": "pending", "output": null }
  }
}
```

Allowed phase statuses:
- `pending`
- `running`
- `complete`
- `failed`
- `skipped`

Recommended phase output files:
- `phase-1-context.md`
- `phase-2-standards.md`
- `phase-3-inclusive.md`
- `phase-4-personas/` (directory with per-persona files)
- `phase-5-patterns.md`
- `phase-6-synthesis.md`

Recommended persona output files (inside `phase-4-personas/`):
- `blind-sr.md`
- `keyboard-only.md`
- `low-vision.md`
- `motor-impaired.md`
- `deaf-hoh.md`
- `adhd-distracted.md`
- `autism-ambiguity.md`

Manifest rules:
- Set phase status to `running` immediately before execution
- Set phase status to `complete` only after its output file exists
- Set phase status to `failed` when an attempt fails
- Set phase status to `skipped` after the second failed attempt, or when a phase cannot proceed safely and later phases can still produce value
- Keep `output` as the phase output path when available, else `null`

## Optional Repository Configuration

Before Phase 1, check for `.a11y-review.yml` in the repository root.

Supported config:

```yaml
platform: web
standard: WCAG-2.2-AA
ignore: ["vendor/**"]
populations_focus: [blind-sr, adhd-distracted]
severity_overrides:
  missing_alt_text: CRITICAL
```

Config rules:
- `platform` defaults to `auto`
- `standard` defaults to `WCAG-2.2-AA`
- `ignore` extends the run's exclusion list
- `populations_focus` defaults to all seven canonical populations
- `severity_overrides` remaps named issue classes during synthesis

If config is missing or partial, continue with defaults.

## Canonical Populations

Use exactly these identifiers:
- `blind-sr`
- `keyboard-only`
- `low-vision`
- `motor-impaired`
- `deaf-hoh`
- `adhd-distracted`
- `autism-ambiguity`

If `populations_focus` is configured, dispatch only those personas. Others are not-run, not passed.

## Canonical Severity

Use uppercase severity labels only:
- `CRITICAL`
- `HIGH`
- `MEDIUM`
- `LOW`

Do not invent additional severity levels. Do not use icons, emoji, or color-only signals anywhere in outputs.

## Prerequisite Validation

Validate prerequisites before each phase.

Rules:
- Phase 2 and later require `phase-1-context.md`
- Phase 5 requires both Phase 2 and Phase 3 outputs
- Phase 4 is optional for Phase 5
- Phase 6 requires at least Phase 1 and one of Phase 2 or Phase 3

Handling:
- If a required prerequisite is missing, attempt the prerequisite phase if possible
- If the prerequisite already failed twice, mark the blocked phase `skipped`
- Continue when later phases still have enough input to add value
- Phase 6 must explicitly note skipped and failed phases

## Failure Handling

Partial reports are always better than no report.

Global rules:
- Retry each failed phase exactly once
- If the retry also fails, mark the phase `skipped` and continue
- Capture the reason for failure or skip in the phase output when possible
- Never represent a skipped phase as clean or issue-free

Phase 4 persona timeout rules:
- Each persona subagent gets a 30 second timeout
- If a persona times out, mark that persona as `skipped`
- Collect successful persona outputs without waiting indefinitely on stragglers
- Aggregate completed, failed, and skipped persona results in Phase 4 output

## Orchestration Algorithm

Follow this algorithm exactly:
1. Resolve the session folder from `<session_context>`
2. Create `<session-folder>/scratch/a11y-review/`
3. Initialize `manifest.json`
4. Detect repository root and target scope
5. Check for `.a11y-review.yml`
6. Resolve the skill install location and confirm `phases/` exists
7. Read `phases/context.md`, execute Phase 1, write `phase-1-context.md`
8. Update manifest
9. Read `phases/standards.md`, execute Phase 2, write `phase-2-standards.md`
10. Update manifest
11. Read `phases/inclusive.md`, execute Phase 3, write `phase-3-inclusive.md`
12. Update manifest
13. Read `phases/personas.md`, execute Phase 4 via parallel subagents
14. Write persona outputs and aggregate `phase-4-personas.md`
15. Update manifest
16. Read `phases/patterns.md`, execute Phase 5, write `phase-5-patterns.md`
17. Update manifest
18. Read `phases/synthesis.md`, execute Phase 6, write `phase-6-synthesis.md`
19. Write the final report to `files/`
20. Display the chat summary
21. Confirm the final report exists
22. Delete `scratch/a11y-review/`

The orchestrator must load phase docs one at a time and never read all phase docs in advance.

## Scope Resolution Guidance

The orchestrator should resolve or infer:
- Repository root
- Target path or subdirectory, if the user scoped the audit
- Platform: configured, detected, or `auto`
- Scope: `codebase`, `subtree`, `app`, `design-system`, or similar run label
- Relevant UI surfaces, routes, components, tokens, and flows

Detection guidance:
- If component stories, tokens, primitives, and shared components dominate, prefer `design-system`
- If routed pages, app shell, forms, and user flows dominate, prefer `web`
- Otherwise keep the detected platform conservative and document limitations

## Phase 1: Context

Before Phase 1:
- Set `manifest.phases.context.status = "running"`
- Read only `phases/context.md`

Objectives:
- Determine platform and scope
- Inventory UI surfaces, flows, and major component groups
- Detect form flows, navigation models, modal usage, tables, media, theming, and shared tokens where available
- Record exclusions from config and obvious generated or vendor paths
- Establish assumptions and known blind spots

Output contract:
- Write `phase-1-context.md`
- Include detected platform, scope, candidate user journeys, target directories, exclusions, and audit limitations
- Mark the phase complete only after the file exists

## Phase 2: Standards

Before Phase 2:
- Confirm `phase-1-context.md` exists
- Set `manifest.phases.standards.status = "running"`
- Read only `phases/standards.md`

Objectives:
- Produce Layer A findings grounded in standards conformance
- Evaluate semantics, landmarks, forms, focus order, keyboard reachability, text alternatives, name-role-value, headings, tables, and state exposure
- Apply the configured standard, defaulting to `WCAG-2.2-AA`
- Use explicit evidence with file references where possible

Output contract:
- Write `phase-2-standards.md`
- Organize findings by severity and issue class
- Note unsupported areas rather than guessing

## Phase 3: Inclusive

Before Phase 3:
- Confirm `phase-1-context.md` exists
- Set `manifest.phases.inclusive.status = "running"`
- Read only `phases/inclusive.md`

Objectives:
- Produce Layer B findings focused on inclusive UX and cognitive load
- Evaluate ambiguity, interruptions, timing pressure, consistency, validation tone, recovery affordances, motion sensitivity, content chunking, and signal clarity
- Identify harms not captured by pure standards conformance
- Surface cross-cutting design concerns that affect multiple populations

Output contract:
- Write `phase-3-inclusive.md`
- Separate standards-adjacent and broader inclusion findings where helpful
- Identify affected populations for each finding when possible

## Phase 4: Personas

Before Phase 4:
- Confirm `phase-1-context.md` exists
- Set `manifest.phases.personas.status = "running"`
- Read only `phases/personas.md`

Execution model:
- Dispatch parallel explore subagents, one per in-scope population
- Use `populations_focus` from config when present
- Pass Phase 1 context and helpful excerpts from Phases 2 and 3
- Timeout each persona after 30 seconds

Each persona prompt must instruct the subagent to:
- Simulate realistic journeys through identified flows
- Reason only from that population's perspective
- Identify blockers, friction, ambiguity, recovery gaps, and misleading cues
- Return structured findings with severity and cited evidence
- Avoid claiming runtime facts not observable in source or docs

Aggregation rules:
- Save each persona result to its own scratch file
- Mark timed-out personas as `skipped`
- Mark execution errors as `failed`
- Aggregate successful and skipped personas into `phase-4-personas.md`
- Do not fail the whole audit because one or more personas did not complete

## Phase 5: Patterns

Before Phase 5:
- Confirm both `phase-2-standards.md` and `phase-3-inclusive.md` exist
- Treat Phase 4 as optional input if available
- Set `manifest.phases.patterns.status = "running"`
- Read only `phases/patterns.md`

Objectives:
- Detect recurring anti-patterns and systemic accessibility risks
- Consolidate repeated defects into design, component, or governance patterns
- Distinguish local defects from shared-system issues
- Note whether persona data reinforced or contradicted the pattern analysis

Output contract:
- Write `phase-5-patterns.md`
- Group findings into anti-pattern families with evidence counts

## Phase 6: Synthesis

Before Phase 6:
- Confirm `phase-1-context.md` exists
- Confirm at least one of `phase-2-standards.md` or `phase-3-inclusive.md` exists
- Set `manifest.phases.synthesis.status = "running"`
- Read only `phases/synthesis.md`

Objectives:
- Consolidate, deduplicate, and rank findings across available phase outputs
- Apply severity overrides from config when specified
- Count severities and affected populations
- Build the final report structure and executive summary
- Explicitly note skipped, failed, or partially completed phases

Deduplication rules:
- Prefer the clearest, most actionable wording for overlapping findings
- Keep the strongest available evidence citation
- Merge population impact lists instead of duplicating the issue
- Preserve systemic anti-pattern framing from Phase 5 where useful

## Final Report Format

Write the final report to:

```text
<session-folder>/files/a11y-review-deep-<repo>-<target-slug>-<date>.md
```

The report must begin with YAML frontmatter containing:
- `tool`
- `version`
- `mode: deep`
- `platform`
- `scope`
- `severity_counts`
- `populations_affected`

Then include these sections in order:
1. `Executive Summary`
2. `Layer A Findings`
3. `Layer B Findings`
4. `Persona Simulation Results`
5. `Cross-Platform Issues`
6. `Anti-Patterns`
7. `Recommendations`

Report rules:
- Use ASCII-safe encoding only
- No emoji
- No color-only indicators
- Use explicit severity labels in text
- If platform support is partial, say so in the summary
- If phases were skipped, note that near the top of the report

## Chat Summary

After writing the report, provide a concise chat summary using the same format as the lite path, plus a persona summary section.

Chat summary structure:
- Scope and platform
- Severity counts
- Top findings
- Persona summary
- Skipped phases or personas
- Final report path

## Cleanup

Cleanup happens only after the final report is successfully written and verified.

Steps:
- Verify the report file exists in `files/`
- Delete `<session-folder>/scratch/a11y-review/`
- Do not delete scratch data if report writing failed

## Output Quality Rules

Always follow these rules:
- ASCII-safe encoding only
- No Unicode above U+007F
- No emoji
- No em-dashes
- No color-only indicators
- No unsupported certainty claims
- No silent downgrade from failed phase to clean result

## Completion Condition

The audit is complete only when all of the following are true:
- Phase execution has reached Phase 6
- A final report has been written to the session `files/` directory
- The chat summary has been produced
- Scratch state has been cleaned up after report verification

If some phases were skipped but the report was produced and clearly labeled, the run still counts as complete.
