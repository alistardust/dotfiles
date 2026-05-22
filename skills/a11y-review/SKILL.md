---
name: a11y-review
version: "1.0.0"
description: >
  Lite read-only accessibility review for PR diffs, UI files, and components.
  Evaluates WCAG-aligned compliance risks and inclusive design exclusion risks,
  then writes a concise report to the session files directory.
---

# A11y Review

Lite accessibility review for quick PR and diff checks. This skill is intentionally narrower than a full audit. It is optimized for changed UI code and always evaluates two layers: Layer A for compliance and standards alignment, and Layer B for inclusive design and exclusion risk.

## When to Use This Skill

Use this skill when the request involves a PR or diff review, a component review, a quick accessibility check on a UI file or small cluster of files, a page, modal, form, table, menu, navigation flow, or a design-system token or component API change that may affect accessibility.

Typical requests:
- "review this PR for accessibility"
- "quick a11y pass on this diff"
- "check this component for a11y issues"
- "scan these frontend files for obvious accessibility problems"

## When NOT to Use This Skill

Do NOT use this skill for a full codebase audit; use `a11y-review-deep` instead. Do NOT use it for pure backend or non-UI code with no user-facing behavior. It is not a replacement for automated tools such as axe, eslint, Storybook a11y, or pa11y. It is also not for pixel-accurate visual verification that requires running the app, for mobile-native platform audits unless a shared-logic-only review is explicitly acceptable, or for legal or compliance signoff.

If the target is mostly non-UI code, produce a limited report that says the review scope is `shared-logic-only` and note that UI-specific conclusions are constrained by missing rendered evidence.

## Read-Only Contract

This skill never modifies the target repository.
- It does NOT edit source files, config files, tests, snapshots, or fixtures.
- It does NOT change git state.
- It does NOT auto-fix findings.
- It may inspect diffs, files, and repository configuration only.
- It writes its report to the session files directory, outside the repo.
- It may read optional repo config from `.a11y-review.yml`.
- It must clearly label assumptions and evidence limits.

If asked to fix code, complete the review first and then hand findings to a separate implementation workflow.

## Invocation

**Input:** a target that resolves to a PR diff, file path, component path, or small directory of related UI files. If no explicit target is provided, default to the current working diff or the smallest obvious UI-focused scope available from context.

**Output path:** `<session-folder>/files/a11y-review-<repo>-<branch-slug>-<date>.md`

Filename fields:
- `<session-folder>`: resolve from the `<session_context>` system block
- `<repo>`: repository name
- `<branch-slug>`: first useful words from the current branch after any prefix
- `<date>`: YYYY-MM-DD

Examples:
- `.../files/a11y-review-dotfiles-main-2026-05-22.md`
- `.../files/a11y-review-webapp-checkout-form-2026-05-22.md`

For same-day reruns of the same repo and branch, overwrite the existing report. The latest run is authoritative. If the user provides a custom output path, use that instead. When invoked, proceed to Phase 1.

## Core Evaluation Model

### Layer A: Compliance

Layer A checks standards-aligned implementation risks in semantics, roles, keyboard access, focus behavior, contrast evidence, text alternatives, error handling, and dynamic state communication. It asks whether the implementation likely blocks or degrades access against established patterns and WCAG-style expectations.

### Layer B: Inclusive Design

Layer B checks exclusion risk that may not be a strict WCAG violation but still causes user failure, hesitation, overload, or confusion. It covers cognitive load, affordance clarity, predictability, progressive disclosure, time pressure, sensory burden, instruction dependency, defaults, recovery, and consistency. It asks whether users can understand and complete the flow without unreasonable guesswork, memory burden, or stress.

Both layers are mandatory for every review.

## Universal Severity Scale

Always use these uppercase labels in output.

| Severity | Definition |
|----------|------------|
| CRITICAL | User cannot complete the flow or access essential content |
| HIGH | User can complete the flow, but with significant friction or high error risk |
| MEDIUM | User can complete the flow, but the experience is meaningfully degraded |
| LOW | Minor friction; does not block or significantly impair completion |

Calibration rules: missing keyboard access on a required control is usually CRITICAL or HIGH; incorrect ARIA on a decorative element is usually LOW or MEDIUM; missing state announcement on a complex async interaction is often HIGH; minor wording ambiguity with a visible workaround is often MEDIUM or LOW. Never invent an `INFO` severity in this skill's findings list.

## Canonical Populations

Every finding must tag one or more of these populations.

| ID | Simulates |
|----|-----------|
| `blind-sr` | Blind screen reader user |
| `keyboard-only` | Motor-impaired keyboard user |
| `low-vision` | Low vision / zoom / high contrast |
| `motor-impaired` | Limited dexterity / switch user |
| `deaf-hoh` | Deaf / Hard of Hearing |
| `adhd-distracted` | ADHD user under cognitive load |
| `autism-ambiguity` | Autistic user sensitive to unpredictability |

Tag only populations plausibly affected by the specific issue. Multiple populations are allowed. Do not force all populations onto every finding. Track coverage across the whole review so every population is considered. A population may legitimately end with zero findings, but that must be noted during verification.

## Platform Detection

V1 fully supports only web and design-system review.

| Signal | Platform |
|--------|----------|
| `.html`, `.jsx`, `.tsx`, `.vue` | `web` |
| Design tokens / JSON | `design-system` |
| Others | `shared-logic-only` |

Interpretation rules: `web` gets the full review; `design-system` reviews token semantics, state coverage, contrast intent, and component API implications where evidence exists; `shared-logic-only` reviews naming, error propagation, state exposure, and timing assumptions, and must explicitly note that rendered UI conclusions are limited. Do not apply browser-only heuristics to non-web targets without evidence.

## Optional Repository Config

Check for `.a11y-review.yml` in the repository root. The file is optional.
If present, it may define:
- `platform`: override platform detection (web | design-system | auto)
- `ignore`: glob patterns for files to skip (e.g., "vendor/**")
- `severity_overrides`: map category names to severity levels
- `include`: additional file patterns to include
- `exclude`: additional file patterns to exclude

Treat config as hints, not truth. Never suppress a finding solely because a config file exists. If config conflicts with code evidence, prefer code evidence and note the conflict. If no config exists, proceed with defaults and do not penalize the repo. Unknown keys are ignored with a warning in output.

## Evidence Standard

Every finding must include all of the following:
- `file:line`
- Severity
- Population tags
- Short issue title
- Evidence snippet or precise code reference
- Why the issue matters to the tagged populations
- A concrete fix recommendation

Evidence rules: use exact file paths and line numbers whenever possible; quote only the minimum necessary snippet; if line numbers are unstable in a diff-only context, use the best available location marker and say so; never make a finding without concrete evidence; if a concern is only a hypothesis, label it as a note or question, not as a finding.

Bad finding:
- "This modal probably has focus issues"

Good finding:
- `src/ui/LoginModal.tsx:88` HIGH `[keyboard-only, blind-sr]` Dialog opens without focus being moved into the modal; keyboard users may remain behind the overlay and screen reader users may not receive immediate context. Recommendation: move focus to the dialog title or first actionable control and trap focus until close.

## Review Scope Rules

Scope selection order:
1. Explicit user target
2. Current PR diff
3. Named file or component from context
4. Smallest obvious UI-focused directory

Lite-mode scope rules: prefer changed files over the whole app, prefer one component subtree over the entire design system, prefer evidence-rich files over speculative expansion, and if scope balloons into a subsystem audit, stop and recommend `a11y-review-deep`.

## Mandatory 4-Pass Loop

The following loop is mandatory at every review phase. Use it once for Layer A and once for Layer B.

```text
PASS 1: ANALYZE
  - Initial findings with evidence (file:line, code snippet)
  - Tag each finding with severity and affected populations

PASS 2: CRITIQUE (checklist)
  [ ] Are any findings false positives? (remove if yes)
  [ ] Am I applying web patterns to a non-web platform?
  [ ] Did I check all 7 populations? Which have zero findings?
  [ ] Did I only check Layer A? Are Layer B issues present?
  [ ] Are severity levels justified by actual user impact?
  [ ] Did I assume visual context I cannot verify?

PASS 3: REVISE
  - Remove false positives identified in critique
  - Add missed issues surfaced by critique
  - Adjust severity based on critique findings
  - Ensure both Layer A and Layer B are represented

PASS 4: VERIFY (termination gate)
  - Consistency check (no contradictions between findings)
  - Population coverage check (every defined population considered)
  - Platform consistency check (findings match the detected platform)
  - Severity distribution sanity (all-critical or all-low is suspicious)
  - TERMINATE when: all checklist items addressed, no contradictions found
  - If verify fails: return to CRITIQUE with the specific failure reason (max 1 retry)
```

Hard rules: do not skip the critique checklist; do not terminate after Analyze alone; do not present output until Verify passes or the single retry limit is exhausted; if the retry limit is exhausted, state which verification gate could not be resolved.

## Lite Workflow

Follow this exact workflow:
1. Determine scope
2. Detect platform from file extensions
3. Check for `.a11y-review.yml` in repo root
4. Run Layer A analysis with the 4-pass loop
5. Run Layer B analysis with the 4-pass loop
6. Tag affected populations on every finding
7. Generate report file and chat summary

Do not reorder these steps.

## Phase 1: Determine Scope

Identify whether the target is `pr-diff`, `file`, `component`, or `directory-lite`.
Use `pr-diff` when the user references a PR, commit range, or current diff. Use `file` when the user names a single file and the review is tightly bounded. Use `component` when nearby files are needed to understand one UI unit. Use `directory-lite` when a small feature folder is needed to understand a flow. If the candidate scope is too large, narrow it.

For `pr-diff`, inspect changed files and only the minimum surrounding context needed to make a fair call. For `file` or `component`, inspect the main file, semantic wrappers, and nearby styles only when they affect visibility, focus, or hidden text. Avoid expanding scope unless missing context prevents a fair review.

## Phase 2: Detect Platform

Determine the platform before issuing findings. Web signals include JSX or TSX returning DOM elements, HTML templates, Vue templates, DOM handlers, ARIA attributes, and style hooks tied to focus or hidden content. Design-system signals include token JSON files, semantic color maps, typography or motion tokens, and foundational component APIs without app-specific flows. Shared-logic-only signals include helper logic without rendering, validation modules, state containers, and async action code with no visible UI layer in scope.

If multiple file types exist, choose the platform that matches the reviewed interaction surface. If there is both shared logic and web UI, mark the review `web`. If there are only tokens and no rendered components, mark `design-system`. Always note the detected platform in the report frontmatter.

## Phase 3: Load Optional Config

Look for `.a11y-review.yml` in the repo root. If found, read it, apply include and exclude hints, apply platform overrides only when they match file reality, and note relevant wrappers or known semantics. If not found, continue with defaults and do not emit a finding about the missing config. If the file is malformed, ignore invalid keys, continue with sane defaults, and note in methodology that config could not be fully parsed.

## Phase 4: Layer A Review

Layer A is the compliance and standards pass. Use the table below to drive Pass 1 analysis.

| Area | Look for | Questions |
|------|----------|-----------|
| Semantics and structure | clickable `div` or `span`, missing labels, broken heading structure, non-semantic lists or tables, icon-only controls without names | Is the underlying element correct for the action? Would assistive tech get the right role and name? Does structure communicate hierarchy? |
| Roles and ARIA | redundant or conflicting ARIA, missing required ARIA, `aria-hidden` on focusable content, broken id references, `role="button"` without keyboard support | Is ARIA necessary here? Does it improve or override semantics incorrectly? Are relationships valid? |
| Keyboard access | click-only behavior, missing escape paths, missing dialog or menu trapping, pointer-only disclosure, broken composite widget behavior | Can the flow be completed without a pointer? Can users reach, operate, and exit everything? Are keys conventional? |
| Focus behavior and visibility | outline removed without replacement, no focus move on dialog or route changes, hidden elements receiving focus, clipped focus, broken tab order | Where does focus start, move, and return? Is focus visible? Does the sequence match expectations? |
| Contrast and differentiation | color-only status, placeholder-as-label, token names implying weak contrast, muted helper or error text, disabled-looking active controls | Is critical meaning conveyed by more than color? Do token names imply low contrast? Is there enough textual redundancy? |
| Text alternatives | images without `alt`, informative SVG without names, charts without summaries, state conveyed only by avatars or badges, media without captions or transcripts | Does non-text content have a meaningful text equivalent? Is decorative content hidden? Is media redundant for blind or deaf users? |
| Error handling and validation | visual-only errors, required state shown only by color or symbol, blur validation without recovery guidance, generic messages, async failures not surfaced | Can users identify which field failed and why? Is recovery guidance specific? Are validation behaviors predictable? |
| State and status communication | loading state with no status text, selected or expanded state missing attributes, unannounced toast messages, missing sorting or filtering state, dynamic updates not surfaced | Are dynamic changes announced? Is selection, expansion, and busy state exposed? Can users understand what changed? |

### Layer A Analyze Pass

In Pass 1, collect candidate findings from the table above. For each candidate, record location, description, evidence, likely populations affected, and initial severity. Keep findings scoped to what the code proves.

### Layer A Critique Pass

Run the mandatory checklist exactly as written. Also ask whether you mistook a wrapper component for a raw DOM element, whether a label is supplied by a nearby prop or helper, whether native behavior already covers the interaction, whether focus styling may live elsewhere, and whether you confused test ids with accessible names.

### Layer A Revise Pass

Typical revisions: remove findings satisfied by native semantics, downgrade speculative contrast claims to methodology notes, merge duplicate findings across the same control, split one large finding when different populations face different risks, and add missed labeling or state issues discovered during critique.

### Layer A Verify Pass

Verify that findings do not contradict each other, that the platform supports the type of claim being made, that population tags are specific and plausible, that severity distribution looks credible, and that any category with zero findings is justified by evidence. If verification fails, do one critique and revise retry only.

## Phase 5: Layer B Review

Layer B is the inclusive design and exclusion risk pass. Use the table below to drive Pass 1 analysis.

| Area | Look for | Questions |
|------|----------|-----------|
| Cognitive load | dense forms, weak orientation in multi-step flows, ambiguous copy, competing actions, errors that rely on memory | Does the user need to hold too much in working memory? Is the task chunked? Are explanations timed where needed? |
| Affordance clarity | controls that look static, unclear icons, destructive actions that do not look risky, weak primary action hierarchy | Can a first-time user tell what is interactive? Is the primary path obvious? Does the UI communicate consequence level? |
| Predictability | context-dependent behavior, auto-submission, inconsistent confirm or cancel order, hidden side effects, unexplained navigation jumps | Does the same action behave the same way everywhere? Are consequences visible before commitment? Will users be surprised? |
| Progressive disclosure | advanced settings shown too early, hidden instructions, optional complexity mixed with required steps, delayed error detail | Is complexity revealed at the right time? Are essentials obvious before details? Can users postpone advanced decisions safely? |
| Time pressure | countdowns, transient critical toasts, autosave assumptions, session expiry revealed too late, interruptive validation | Does the user have enough time? Are important messages persistent enough? Can slower users recover without panic? |
| Sensory burden | motion-heavy defaults, stacked alerts, crowded visual state, audio-dependent confirmation, excessive urgency styling | Does the interface demand too much processing? Is information still clear under reduced motion or limited perception? |
| Instruction dependency | placeholder-only rules, distant instructions, exact formatting with no examples, expert jargon, missing local guidance | Can users succeed without memorizing instructions? Is guidance local to the decision point? Does the interface teach itself? |
| Defaults and preselected choices | destructive defaults, consent-like defaults on, surprising sort or destination state, hidden assumptions in prefilled values | Do defaults reduce effort without steering users into harm? Is the safest reasonable choice easy to keep? |
| Recovery and undo | destructive actions with no undo, form resets near submit, loss of typed data, dead-end errors, dismissals that hide context | Can users recover from mistakes? Is there an escape hatch? Are consequences reversible when feasible? |
| Consistency | mixed terminology, inconsistent field order, unstable button placement, mismatched token and component intent, inconsistent error summaries | Are similar things presented similarly? Does terminology stay stable? Would switching screens force relearning? |

### Layer B Analyze Pass

In Pass 1, collect candidate Layer B findings with concrete evidence such as confusing copy, inconsistent button labels, conditional rendering that hides instructions, risky default props, timeout logic, or token names that imply aggressive motion or weak hierarchy. Avoid purely aesthetic critiques.

### Layer B Critique Pass

Run the mandatory checklist exactly as written. Also ask whether you are reporting taste instead of exclusion risk, whether the concern is tied to an actual user task, whether nearby copy or structure already mitigates it, whether you confused product policy with UX risk, and whether you over-tagged populations without evidence.

### Layer B Revise Pass

Typical revisions: remove abstract design opinions with no task impact, merge overlapping confusion findings into a stronger single issue, add recovery or time-pressure issues discovered during critique, tighten recommendations so they are actionable in code review, and rebalance severity if the issue is frustrating but not blocking.

### Layer B Verify Pass

Verify that each finding maps to a concrete exclusion risk, that evidence exists in code, copy, config, or diff behavior, that recommendations are specific enough for follow-up work, that population coverage was considered, and that both Layer A and Layer B are represented before termination. If verification fails, do one critique and revise retry only.

## Phase 6: Population Tagging

After both layers complete, validate population coverage across the whole review.

| Population | Common triggers |
|------------|-----------------|
| `blind-sr` | missing accessible names, broken semantics, unannounced dynamic updates, missing form relationships, context changes without focus or status updates |
| `keyboard-only` | unreachable controls, missing escape paths, broken tab order, focus loss or invisible focus, pointer-only disclosure |
| `low-vision` | weak visual differentiation, placeholder-as-label, tiny or low-emphasis helper text, focus indication concerns, zoom-sensitive clipping or truncation hints |
| `motor-impaired` | small target clues, drag-only interactions, dense control clusters, multi-step precision requirements, keyboard gaps that increase physical effort |
| `deaf-hoh` | audio-only cues, media without captions or transcripts, visual-only state changes without persistent text, instructions that rely on sound or timing cues |
| `adhd-distracted` | competing actions, transient instructions, high memory burden, overload from dense or inconsistent flows, time pressure and interruptive validation |
| `autism-ambiguity` | unpredictable behavior, inconsistent labels or action order, hidden rules, weak affordances, surprising defaults or context shifts |

At verification time, explicitly ask: which populations have findings, which were considered but have zero findings, and whether any population was skipped by habit. This check is mandatory even if the final report only lists affected populations in frontmatter.

## Phase 7: Synthesis and Deduplication

Combine both layers into a final finding set.
If Layer A and Layer B identify the same root cause, keep separate findings only when the user impact differs materially; otherwise merge into a single stronger finding and mention both compliance and exclusion risk in the explanation. Keep recommendations focused and non-duplicative.

Severity sanity check: everything being CRITICAL is suspicious; everything being LOW is suspicious; only Layer A findings is suspicious; all findings hitting the same populations is suspicious; and all issues being copy issues on a complex UI is suspicious. If the distribution looks suspicious, revisit critique once.

## Reporting Rules

The report file must contain YAML frontmatter followed by markdown.

### Required report frontmatter

```yaml
---
tool: a11y-review
version: "1.0.0"
mode: lite
platform: web
scope: pr-diff
critical: N
high: N
medium: N
low: N
populations_affected: [blind-sr, keyboard-only]
---
```

Field rules:
- `tool` is always `a11y-review`
- `version` is always `1.0.0`
- `mode` is always `lite`
- `platform` is the detected platform
- `scope` is one of `pr-diff`, `file`, `component`, `directory-lite`, or `shared-logic-only`
- `critical`, `high`, `medium`, `low` are integer counts
- `populations_affected` lists unique population ids from actual findings only

### Required report sections

Use this section order:
1. Executive Summary
2. Layer A Findings
3. Layer B Findings
4. Recommendations

Optional additional sections are allowed only if they improve clarity: Scope and Methodology, Limitations, and Appendix: Reviewed Files. Do not bury the main findings behind long preamble.

## Executive Summary Format

The Executive Summary should include one paragraph on reviewed scope and platform, one paragraph on risk concentration, and one short note on evidence limits if any. Keep it concise.

Example:
- Reviewed the current PR diff across three web UI files related to account recovery. The main risks are missing accessible labeling on icon controls, modal focus management, and ambiguous recovery messaging.

## Findings Section Format

Group findings by layer, then by severity in this order: CRITICAL, HIGH, MEDIUM, LOW. If a severity has zero findings, omit that subsection.

### Finding template

Use this exact field structure for every finding:

#### [SEVERITY] Short issue title
- Location: `path/to/file.ext:123`
- Populations: `blind-sr`, `keyboard-only`
- Evidence: `minimal relevant snippet`
- Impact: Clear description of what the user cannot do or why the task becomes harder
- Recommendation: Specific fix direction suitable for a follow-up PR

Template example:

#### [HIGH] Icon-only close button has no accessible name
- Location: `src/components/ModalHeader.tsx:42`
- Populations: `blind-sr`, `keyboard-only`
- Evidence: `<button onClick={onClose}><CloseIcon /></button>`
- Impact: Screen reader users may encounter an unnamed button, and keyboard users may need to tab to a control whose purpose is not announced clearly.
- Recommendation: Add a programmatic name such as `aria-label="Close dialog"` or visible text that matches the action.

Rules: keep titles short and concrete; recommendations should describe direction, not prescribe a full patch; impacts must mention user outcome, not only spec language.

## Recommendations Section

End with prioritized recommendations. Suggested structure: immediate blockers, next-highest risk fixes, and tooling or process follow-ups. Recommendations must remain read-only. They can suggest work but do not modify code.

Example recommendations:
- Fix missing dialog focus management before merge
- Add regression tests for accessible names on icon buttons
- Introduce linting or Storybook a11y checks for custom interactive wrappers

## Chat Summary Format

Return this exact summary shape in chat:

```text
## A11y Review Summary

CRITICAL: N | HIGH: N | MEDIUM: N | LOW: N

Top Issues:
1. [CRITICAL] description (populations)
2. [HIGH] description (populations)
...

Populations Most Affected: persona-id (N issues), persona-id (N issues)

Full report: <path-to-file>
```

Chat summary rules: include up to 5 top issues; sort them by severity and user impact; use plain text severity labels only; do not use emoji; do not rely on color; keep the chat summary shorter than the report.

## Special Handling Cases

### Design-system review

When platform is `design-system`, focus on semantic token intent, state tokens, contrast implications where token pairs are explicit, motion tokens, and component API naming. Review whether component props encourage accessible defaults. Avoid pretending the rendered experience is fully visible from tokens alone. Call out when token naming implies color-only or weak state differentiation.

### Shared-logic-only review

When platform is `shared-logic-only`, restrict claims to what logic can prove. Focus on validation messaging hooks, state exposure, timing assumptions, retry behavior, and naming that affects assistive output. Include a limitation note that rendered semantics, focus, and contrast could not be verified.

### Diff-only review

When reviewing a PR diff, prefer changed lines and nearby context. Avoid restating pre-existing issues unless the diff worsens them or makes them newly relevant. If a changed wrapper introduces a likely global risk, note that the blast radius may exceed the diff. Keep recommendations scoped to merge-risk decisions.

## False Positive Controls

Use these controls aggressively. Do not flag a missing label when the accessible name is clearly supplied by `aria-label`, `aria-labelledby`, or adjacent props. Do not flag a missing keyboard handler on a native button or link that already supports keyboard activation correctly. Do not claim a contrast failure based only on generic color names without explicit token pairing or rendered evidence. Do not claim a focus issue based only on absent CSS when focus styles may be inherited elsewhere. Do not report an ARIA issue on a custom wrapper until you inspect what it renders. If uncertain, downgrade from finding to methodology note.

## Severity Calibration Examples

CRITICAL examples: custom menu cannot be operated by keyboard; required submit control has no accessible name; modal opens without focus management and traps the user behind the overlay; essential error state is not surfaced in any perceivable way.

HIGH examples: autocomplete suggestions are not announced clearly but submission is still possible; required field errors exist visually but are not programmatically tied to inputs; important state changes rely on color plus subtle text only; destructive default is preselected with weak affordance.

MEDIUM examples: helper text is distant from the control, increasing memory burden; button labels are inconsistent across steps, creating hesitation; motion-heavy token defaults exist with no clear reduced-motion path in scope; disclosure controls use vague labels that slow understanding.

LOW examples: decorative icon alt handling is inconsistent but non-blocking; secondary action wording is mildly ambiguous with strong surrounding context; low-risk status copy is slightly jargon-heavy; supporting text hierarchy is uneven but the task remains clear.

## Termination Conditions

Terminate the review when all of the following are true:
- Layer A completed the 4-pass loop
- Layer B completed the 4-pass loop
- Verify passed for both layers, or one retry was exhausted and documented
- Every finding has location, severity, population tags, evidence, impact, and recommendation
- Report file was written
- Chat summary was produced

Do not terminate early because the first few findings look obvious.

## Failure Handling

If the review cannot fully proceed, still write a report, explain the limitation clearly, include whatever validated findings exist, and separate verified findings from unresolved questions.
Examples: platform unsupported, so only shared-logic review performed; diff omitted a relevant wrapper, so role semantics remain uncertain; styles unavailable, so contrast claims are limited to token evidence only.

## Guardrails

Always follow these rules:
- No emoji anywhere in output
- No color-only severity indicators
- No Unicode above ASCII
- No em-dashes
- Never modify source code
- Never pretend to have run browser-based tooling if you did not
- Never claim contrast certainty without evidence
- Never omit population tags on findings
- Never omit file:line on findings unless the source context genuinely lacks stable lines; if so, explain why
- Never use this lite skill as a substitute for automated test tooling

## Quick Execution Checklist

Use this checklist before writing the report:
- [ ] Scope determined
- [ ] Platform detected
- [ ] `.a11y-review.yml` checked
- [ ] Layer A 4-pass loop completed
- [ ] Layer B 4-pass loop completed
- [ ] Findings deduplicated
- [ ] Population coverage reviewed
- [ ] Severity distribution sanity checked
- [ ] Report file written
- [ ] Chat summary prepared

## Final Reminder

This is a lite review skill. Prefer a short list of evidence-backed issues over a long list of speculative ones. Compliance matters, but this skill is strongest when it also surfaces who is excluded, how they are excluded, and what kind of change would reduce that risk.
