# Phase 2: Baseline Standards and Technical Accessibility
Purpose: review the target for baseline accessibility standards compliance. This is Layer A: technical accessibility grounded in WCAG 2.2 AA and platform conventions.

This document is an internal reference for the a11y-review-deep orchestrator.
It is not a standalone skill and is not independently runnable.
The orchestrator loads this phase after Phase 1 establishes platform, scope, flows, and limitations.

## Canonical References

Use these values exactly in analysis and output.

### Populations
- blind-sr
- keyboard-only
- low-vision
- motor-impaired
- deaf-hoh
- adhd-distracted
- autism-ambiguity

### Severity
- CRITICAL
- HIGH
- MEDIUM
- LOW

### Platform enum
- web
- ios
- android
- desktop
- cross-platform-mobile
- design-system
- multi-platform
- unknown

### V1 platform scope
V1 fully supports web and design-system.
If another platform is detected, preserve the correct platform label and note:
"Platform-specific checks not yet implemented for [platform]."
When that happens, still apply shared standards logic where possible.

## Phase Objective

Phase 2 produces the Layer A findings set.
It answers: does the implementation meet baseline technical accessibility expectations?

Layer A is about structural, semantic, and standards-based correctness.
It is not the full story of usability.
That broader question belongs to Phase 3.

Phase 2 must:
1. evaluate the target against WCAG 2.2 AA categories
2. apply platform-specific checks when supported
3. anchor every finding in evidence
4. tag affected populations explicitly
5. propose concrete fixes
6. avoid claiming certainty about things static analysis cannot prove

## Inputs Required from Phase 1

Do not run this phase in isolation.
Consume these Phase 1 outputs first:
- detected platform
- scope boundary
- user flows
- missing information and limitations
- configuration applied

If Phase 1 says platform is unknown, do not quietly switch to web.
If Phase 1 says this is multi-platform, keep findings segmented by platform or clearly mark cross-platform findings.
If Phase 1 says rendered contrast cannot be verified, preserve that limitation.

## Layer A Definition

Layer A asks: "Does this meet the standard?"
The focus is technical accessibility, including semantic correctness, input support, content alternatives, and assistive technology compatibility.

A finding belongs in Layer A when it can be tied to:
- WCAG success criteria
- platform accessibility API expectations
- established semantic or interaction conventions
- a clear technical gap that affects access

Examples:
- missing label
- invalid heading structure
- keyboard trap
- aria-expanded not updated
- status message not announced
- video missing captions

## WCAG 2.2 AA Reference Frame

Organize findings by the four WCAG principles:
1. Perceivable
2. Operable
3. Understandable
4. Robust

Each principle should be explicitly considered even if there are no findings.
If a principle has no issues, say so.
Do not omit a principle because no finding was found there.

## Perceivable

Perceivable covers whether users can detect and interpret content through one or more senses or assistive technologies.

### Text alternatives
Check for non-text content that needs an accessible alternative.
Examples:
- images without meaningful alt text
- icon-only controls without accessible names
- charts with no textual summary
- decorative images missing empty alt
- SVG content with no label when it carries meaning

Relevant user populations:
- blind-sr
- low-vision

Common WCAG references:
- 1.1.1 Non-text Content
- 4.1.2 Name, Role, Value when naming is missing on controls

### Time-based media
Check whether media content communicates information that needs accessible equivalents.
Examples:
- video missing captions
- audio content missing transcript
- video-only content missing descriptive alternative
- autoplay media with no controls

Relevant user populations:
- deaf-hoh
- blind-sr
- adhd-distracted

Common WCAG references:
- 1.2.x time-based media criteria

### Adaptable
Check whether structure and relationships are preserved programmatically.
Examples:
- headings used only for styling
- form fields visually grouped but not semantically grouped
- tables without proper headers
- list-like content built from generic div elements
- instructions that depend on visual position alone

Relevant user populations:
- blind-sr
- low-vision
- autism-ambiguity

Common WCAG references:
- 1.3.1 Info and Relationships
- 1.3.2 Meaningful Sequence
- 1.3.3 Sensory Characteristics

### Distinguishable
Check whether content remains usable when vision, hearing, or attention is limited.
Examples:
- color-only status communication
- placeholder-only labels
- low-contrast text or controls suspected from token or style usage
- text that cannot be resized due to fixed containers or clipping patterns
- autoplay audio that interferes with assistive tech
- content hidden on hover-only reveal

Relevant user populations:
- low-vision
- blind-sr
- adhd-distracted
- motor-impaired

Common WCAG references:
- 1.4.1 Use of Color
- 1.4.3 Contrast Minimum
- 1.4.4 Resize Text
- 1.4.10 Reflow
- 1.4.11 Non-text Contrast
- 1.4.13 Content on Hover or Focus

### Perceivable review cautions
Do not state that contrast definitively fails unless actual values or token math support it.
If contrast cannot be measured, say so clearly.
Valid wording:
- "Potential contrast risk due to color-only communication; rendered ratio not verified."
- "Structural analysis suggests placeholder-only labeling; rendered label visibility not confirmed."

## Operable

Operable covers whether users can interact with the interface using available input methods and without being blocked by timing or navigation issues.

### Keyboard accessible
For V1 web reviews, this is a primary check.
Verify that all interactive elements appear reachable and operable by keyboard.
Examples:
- clickable div or span with no keyboard support
- custom control missing Enter or Space handling
- hidden focus target required to complete a task
- dialog interactions that cannot be completed without pointer input

Relevant user populations:
- keyboard-only
- motor-impaired
- blind-sr

Common WCAG references:
- 2.1.1 Keyboard
- 2.1.2 No Keyboard Trap
- 2.1.4 Character Key Shortcuts where applicable

### Enough time
Check for time limits, auto-advance behavior, or session expiry risks.
Examples:
- OTP fields that auto-submit before review
- session timeout warnings missing accessible notice
- carousels that auto-rotate with no pause control
- progress loss when a timed step expires

Relevant user populations:
- motor-impaired
- adhd-distracted
- autism-ambiguity

Common WCAG references:
- 2.2.x time-related criteria

### Seizures and physical reactions
Static code review can only catch obvious motion or flashing risks.
Examples:
- animation utilities that force repeated flashing
- autoplaying animated hero section with no reduction path
- motion-heavy transitions without reduced motion handling

Relevant user populations:
- autism-ambiguity
- low-vision

Common WCAG references:
- 2.3.x seizures and physical reactions criteria
- 2.2.2 Pause, Stop, Hide when motion cannot be controlled

### Navigable
Check whether the user can understand where they are, where they can go, and how to move efficiently.
Examples:
- missing page title or view title
- missing heading level one for major views
- no skip link in dense application shell
- repeated navigation with no bypass path
- focus order that does not match visual or task order
- SPA route changes with no focus reset or announcement

Relevant user populations:
- blind-sr
- keyboard-only
- low-vision
- adhd-distracted

Common WCAG references:
- 2.4.1 Bypass Blocks
- 2.4.2 Page Titled
- 2.4.3 Focus Order
- 2.4.4 Link Purpose
- 2.4.6 Headings and Labels
- 2.4.7 Focus Visible
- 2.4.11 Focus Not Obscured Minimum
- 2.4.13 Focus Appearance

### Input modalities
This category covers pointer, touch, and alternative input expectations.
V1 web reviews should still consider whether custom interactions assume precise pointer use.
Examples:
- drag-only interaction with no alternative
- tiny clickable target in dense toolbars
- hover-only affordance required for action discovery
- gesture-based mobile interaction with no alternative path

Relevant user populations:
- motor-impaired
- keyboard-only
- low-vision

Common WCAG references:
- 2.5.x input modality criteria

## Understandable

Understandable covers whether users can read, predict, and recover from interaction without unnecessary confusion.

### Readable
Check for language and reading support issues that are visible in code structure.
Examples:
- missing document language
- abbreviations or jargon in labels with no expansion where meaning is unclear
- instructions hidden in placeholder text only

Relevant user populations:
- deaf-hoh
- adhd-distracted
- autism-ambiguity

Common WCAG references:
- 3.1.x readable criteria

### Predictable
Check for consistent behavior and stable interaction patterns.
Examples:
- control changes context unexpectedly on focus
- navigation items behave differently across similar components
- modal opens without focus transfer
- submit button triggers navigation without warning

Relevant user populations:
- autism-ambiguity
- keyboard-only
- blind-sr

Common WCAG references:
- 3.2.x predictable criteria

### Input assistance
Check whether form interaction supports error prevention, identification, and recovery.
Examples:
- fields missing labels
- required state indicated only by color or asterisk with no accessible explanation
- errors not tied to fields
- no clear validation message
- autocomplete opportunity missed on common personal data fields
- destructive submission with no review step when errors are costly

Relevant user populations:
- blind-sr
- keyboard-only
- adhd-distracted
- motor-impaired

Common WCAG references:
- 3.3.1 Error Identification
- 3.3.2 Labels or Instructions
- 3.3.3 Error Suggestion
- 3.3.4 Error Prevention Legal, Financial, Data
- 1.3.5 Identify Input Purpose
- 3.3.7 Redundant Entry
- 3.3.8 Accessible Authentication Minimum

### Understandable review cautions
Do not treat vague UX discomfort as a Layer A issue unless it maps to an actual standards-based requirement.
If the concern is more about overwhelm, ambiguity, or design quality despite technical compliance, move it to Phase 3.

## Robust

Robust covers whether the interface exposes reliable structure and state to assistive technologies.

### Compatible with assistive technologies
Check whether the code likely produces a coherent accessibility tree.
Examples:
- missing names, roles, or values on custom controls
- ARIA roles that conflict with native semantics
- aria-hidden on focusable content
- duplicate IDs breaking relationships
- invalid aria-labelledby or aria-describedby references
- state attributes that never update
- status messages inserted with no live region strategy

Relevant user populations:
- blind-sr
- keyboard-only

Common WCAG references:
- 4.1.2 Name, Role, Value
- 4.1.3 Status Messages

### Robust review cautions
Remember: no ARIA is better than bad ARIA.
Use native elements whenever possible.
Only recommend ARIA when native semantics cannot express the behavior.
If a native element can replace a custom role-based control, that is usually the preferred fix.

## Web-Specific Checks

V1 web reviews should go deep here.
These checks should be treated as primary, not optional.

### HTML semantics
Check:
- correct use of button, link, input, select, textarea, dialog, table, list, heading
- heading hierarchy is meaningful and not obviously skipped without reason
- landmarks exist where the page structure warrants them
- forms use label or equivalent accessible naming
- groups use fieldset and legend when the relationship matters
- lists and tables are real lists and tables when structure matters

Common failure patterns:
- div styled as button
- anchor used as button without href semantics adjustment
- heading level used for size only
- main content missing a main landmark in app shell
- card grid built with no list semantics despite repeated navigable items

### ARIA
Check roles, states, and properties conservatively.
Questions to ask:
- Is ARIA needed here at all?
- Does the role match actual interaction behavior?
- Are state properties updated when state changes?
- Are relationships valid and pointing at existing IDs?
- Is the component duplicating or conflicting with native semantics?

Common failure patterns:
- role="button" with no keyboard support
- aria-expanded present but never changed
- aria-controls pointing to missing element
- role="dialog" without labeling
- aria-hidden="true" on visible interactive descendant
- menu role used for normal site navigation

### Focus management
Check the lifecycle of focus during dynamic changes.
This is especially important for SPAs, dialogs, drawers, menus, and async states.

Check:
- focus indicators appear likely to remain visible
- tab order follows task order
- opened dialogs move focus inside
- closed dialogs restore focus logically
- route changes set focus to heading, main landmark, or another sensible target
- hover content is also reachable by focus where needed
- no obvious keyboard traps in menus, drawers, modals, editors

### Color and contrast
Static review cannot fully verify rendered ratios without real values and final rendering.
Still check for structural risks such as:
- instructions like "items in red are required"
- success and error communicated only by color
- disabled states that may become too faint
- token usage that suggests low-emphasis text for critical content
- icons or borders used as the only error indicator

If design token values are visible, use them as evidence.
If not, call this a risk, not a proven failure.

### Keyboard
Check whether every interactive element is both reachable and operable.
Inspect:
- click handlers on non-interactive nodes
- suppressed default focus outlines
- roving tabindex logic in composite widgets
- event handling limited to mouse events
- shortcut-only features without discoverable alternative

### Forms
Forms deserve special attention because they combine many WCAG categories.
Check:
- label association
- required state communication
- instructions available before submission
- error summary and inline errors
- aria-invalid and describedby relationships where custom validation is used
- autocomplete on known personal information fields when applicable
- grouped options use fieldset and legend or equivalent
- disabled submit buttons do not hide what is wrong
- status updates during submit and save are announced
- authentication steps do not rely on memory puzzles or inaccessible CAPTCHA

### Dynamic content
Check whether asynchronous or client-side changes are conveyed accessibly.
Examples:
- loading spinner appears but no status message
- toast communicates critical result but is not announced
- tabs update panels but not aria-selected or relationships
- accordion changes but state is not exposed
- route transition occurs but focus remains in previous nav item
- inline validation appears visually but not programmatically

### Media
Check whether media experiences include necessary alternatives and controls.
Examples:
- captions for spoken video
- transcript for audio-only content
- avoid autoplay audio
- controls reachable by keyboard
- descriptive alternative for visual-only instructional media

## Design System Checks

V1 design-system reviews are the secondary supported path.
These checks matter when the target is a token package, primitives library, or shared pattern set.

### Token-level checks
Inspect whether token architecture creates systemic risk.
Questions:
- Are color tokens used for semantic state in a way that may rely on color alone?
- Are low-contrast text tokens encouraged for small body text?
- Are focus ring tokens optional or easy to disable?
- Are motion tokens missing reduced-motion alternatives?
- Are spacing and sizing tokens likely to create tiny hit targets?

A token-level problem may deserve elevated severity because it propagates broadly.
If the problem affects multiple components by design, say that clearly.

### Component-level checks
Inspect shared component primitives for built-in accessibility support.
Questions:
- Does Button render a real button by default when used as a button?
- Does Dialog require labeling and initial focus management?
- Does Input expose accessible name wiring?
- Does Menu follow the correct pattern only when truly acting as a menu?
- Do Tabs expose roles and keyboard behavior by default?
- Do Toast or Alert components expose live region patterns?

If a primitive is unsafe by default, note that this creates broad downstream risk.

### Pattern-level checks
Inspect whether documented usage patterns are accessible by default.
Examples:
- docs recommend placeholder-only form labels
- examples suppress focus outlines for aesthetics
- card links and nested buttons are shown together in examples
- docs show infinite carousel with no pause control
- filter chips are documented as color-only state toggles

The key question is not just whether a component can be used accessibly.
It is whether the default example and documentation push teams toward accessible outcomes.

## Platform-Specific Notes for V2

These notes are placeholders for future deeper adapters.
They should appear as notes, not full V1 checklists.

### Mobile placeholder notes
For ios, android, and cross-platform-mobile, note relevant future checks such as:
- touch target size
- VoiceOver and TalkBack traits and labels
- rotor and accessibility action support
- gesture alternatives for drag, swipe, or long press
- dynamic type and text scaling
- haptics not used as sole feedback channel

If V1 encounters these platforms, record shared findings and add a note that detailed platform-specific checks are not yet implemented.

### Desktop placeholder notes
For desktop, note future checks such as:
- high contrast mode compatibility
- magnifier support
- keyboard shortcut discoverability and remapping
- menu bar accessibility patterns
- system accessibility API exposure

Again, V1 should not pretend these checks were completed.

## Severity Guidance for Layer A

Use the canonical severity scale.
Choose severity based on actual user impact, not code smell alone.

### CRITICAL
Use when the user is effectively blocked from completing a core flow.
Examples:
- submit button inaccessible to keyboard-only users in checkout
- modal traps focus with no escape path
- required field has no accessible name in a critical form
- authentication step is impossible with assistive technology

### HIGH
Use when the flow can technically complete but with major friction or high error risk.
Examples:
- custom button missing semantic role but still partially operable
- inline errors not announced, causing repeated failed submission
- focus order causes repeated disorientation in a dense flow

### MEDIUM
Use when access exists but quality is clearly degraded.
Examples:
- heading hierarchy is inconsistent but task is still navigable
- icon labels are ambiguous but discoverable through surrounding text
- token usage creates contrast risk that is likely but unverified

### LOW
Use when friction is minor and does not meaningfully impair completion.
Examples:
- redundant title mismatch with visible heading
- decorative icon exposed but not harmful in context

## Population Tagging Guidance

Every finding must tag affected populations.
Use the canonical population IDs only.
Do not use broad labels like "screen reader users" in the structured field.
Use blind-sr instead.

Common mapping examples:
- missing accessible name: [blind-sr, keyboard-only]
- no keyboard support: [keyboard-only, motor-impaired, blind-sr]
- color-only communication: [low-vision, blind-sr]
- captions missing: [deaf-hoh]
- hidden focus indicator: [keyboard-only, low-vision, motor-impaired]

If a finding affects everyone, still choose the populations most directly harmed.
Avoid tagging all seven unless the issue truly cuts across the whole experience.

## The 4-Pass Loop

Every phase uses the same 4-pass structure.
Phase 2 applies it to standards-based findings.

### ANALYZE
Perform the first-pass compliance review.
For each finding, include:
- severity
- file and line reference
- issue statement
- WCAG criterion
- affected populations
- concrete fix recommendation

Cover all four WCAG principles.
If a principle has no issues, record that explicitly.

### CRITIQUE
Challenge the initial findings.
Answer each question explicitly:
- Are any findings false positives or under-evidenced?
- Did I mark a contrast failure without actual measurement?
- Did I apply web rules to non-web files?
- Did I confuse a design-system issue with an application issue?
- Did I cover Perceivable, Operable, Understandable, and Robust?
- Did I overuse ARIA in fixes when native semantics would be better?
- Are severity levels tied to actual user impact?
- Are file:line references precise enough to act on?

### REVISE
After critique:
- remove false positives
- downgrade or upgrade severity if needed
- add missed findings
- move non-compliance issues that are really design quality concerns to Phase 3
- clarify limitations on uncertain findings
- tighten fixes so they are implementable

### VERIFY
Before Phase 2 is complete, confirm all of the following:
- findings are organized by WCAG principle
- every finding has severity, populations, WCAG, file:line, and fix
- all four WCAG principles were considered
- platform label matches Phase 1
- unsupported platform notes are present when needed
- no contradictory findings remain

If verification fails, return once to CRITIQUE, revise, and verify again.
If uncertainty remains, proceed with an explicit note.

## Finding Format

Use this structure exactly for individual findings.

```markdown
- severity: HIGH
  file: src/components/Button.tsx:42
  issue: Button uses div with onClick but no role="button" or keyboard handler
  wcag: 4.1.2 Name, Role, Value
  population: [blind-sr, keyboard-only]
  fix: Use <button> element or add role="button" and onKeyDown handler
```

## Output Structure

Output must begin with this header:

```markdown
## Status: COMPLETE
```

After that, organize the report in this order:
1. Perceivable
2. Operable
3. Understandable
4. Robust
5. Limitations and Notes
6. Configuration Applied

### Required section skeleton

```markdown
## Status: COMPLETE

### Perceivable
- severity: ...
  file: ...
  issue: ...
  wcag: ...
  population: [...]
  fix: ...

### Operable
...

### Understandable
...

### Robust
...

### Limitations and Notes
- Structural analysis only; rendered contrast was not measured.

### Configuration Applied
- standard: WCAG-2.2-AA
- platform: web
- ignore: [third-party/vendor/**]
```

If there are no findings under a principle, write:

```markdown
### Perceivable
- No issues identified from static analysis in reviewed scope.
```

Do not omit empty sections.

## Review Discipline

Phase 2 should be evidence-heavy and conservative.
A smaller set of high-confidence findings is better than a long list of guesses.
The goal is to identify actionable accessibility defects, not to sound exhaustive while being wrong.

Key reminders:
- no ARIA is better than bad ARIA
- native semantics usually beat custom role-based controls
- static review cannot fully validate visual contrast or runtime announcement behavior
- a technically compliant structure may still fail real users, but that belongs to Phase 3

## Completion Standard

Phase 2 is complete when the output can stand on its own as a technical accessibility review for Layer A.
A reader should be able to trace each finding to evidence, understand which WCAG area it maps to, know who is affected, and see a plausible fix.
