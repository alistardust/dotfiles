# Phase 3: Inclusive Design and Interaction Quality
Purpose: review the target for inclusive design quality beyond baseline compliance. This is Layer B: cognitive accessibility, neurodiversity support, exclusion risk, and usability under real-world constraints.

This document is an internal reference for the a11y-review-deep orchestrator.
It is not a standalone skill and is not independently runnable.
The orchestrator loads this phase after Layer A findings are established.

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
If another platform is detected, preserve the correct label and note:
"Platform-specific checks not yet implemented for [platform]."
Layer B still applies shared inclusive design reasoning even when platform-specific adapters are limited.

## Phase Objective

Phase 3 produces the Layer B findings set.
It answers: even if the interface might technically pass many standards checks, does it actually work for real people under realistic conditions?

This phase cares about:
- mental effort
- ambiguity
- distraction
- fatigue
- recovery from mistakes
- interaction consistency
- hidden dependence on reading or memory
- whether accessible paths are the default path

## Key Distinction from Layer A

Layer A asks: "Does this meet the standard?"
Layer B asks: "Even if it passes, does it actually work for this person?"

Example:
- A form with proper labels and valid error markup may pass Layer A.
- The same form may still fail Layer B if it shows 47 fields at once, mixes billing and shipping logic with no grouping, and gives no sense of progress.

Do not duplicate every Layer A finding here.
Layer B should highlight exclusion risk, cognitive burden, and design quality issues that matter in real use.
If the same root cause has both Layer A and Layer B relevance, Phase 6 will merge them later.

## Layer B Categories

Every category below must be explicitly considered.
If no findings are present for a category, say so rather than omitting it.

### Cognitive Load
What to check:
- dense pages with too many simultaneous decisions
- long ungrouped forms
- excessive memory burden across steps
- several competing calls to action with equal visual weight
- repeated scanning demands to find the next important action
- jargon-heavy copy that requires extra interpretation

Who benefits most:
- adhd-distracted
- autism-ambiguity
- low-vision

Typical signals:
- many fields visible at once
- sparse grouping or headings
- repeated optional branches that alter completion logic
- long dashboards with little hierarchy

### Clarity of Affordances
What to check:
- is the next action obvious
- does clickable content look clickable
- are instructions hidden in helper text that appears too late
- do icons communicate meaning without labels
- are destructive actions visually or semantically distinguished

Who benefits most:
- all populations, especially neurodivergent users

Typical signals:
- ghost buttons that look like plain text
- cards that are clickable but give no cue
- hidden instructions that only appear after error
- icon-only controls with ambiguous purpose

### Predictability
What to check:
- consistent patterns across similar screens
- stable layout and state changes
- no surprise navigation or context switches
- actions do what users expect based on prior screens
- modal and drawer behavior is consistent

Who benefits most:
- autism-ambiguity
- adhd-distracted
- blind-sr

Typical signals:
- same button label causes different outcomes in different places
- filters auto-apply on one screen but require submit on another
- focus or scroll jumps unexpectedly after save
- route transition occurs with no stable anchor

### Progressive Disclosure
What to check:
- complexity introduced gradually
- optional or advanced settings hidden until needed
- users are not forced to confront all edge cases at once
- review steps break complex actions into digestible chunks

Who benefits most:
- adhd-distracted
- low-vision
- autism-ambiguity

Typical signals:
- huge all-in-one forms
- massive settings pages with no grouping or collapsing
- wizard steps collapsed into one overloaded page
- advanced controls exposed by default without explanation

### Time Pressure
What to check:
- session expiry with data loss risk
- countdowns, auto-advance, or OTP flows with forced pace
- disappearing toasts that contain important next steps
- no pause or save draft path during long tasks

Who benefits most:
- motor-impaired
- adhd-distracted
- autism-ambiguity

Typical signals:
- auto-submitting verification codes
- short-lived banners that explain required action
- long forms with no save draft support
- steps that expire without accessible warning

### Sensory Burden
What to check:
- animation intensity
- autoplay media
- notification overload
- excessive visual noise
- rapid layout changes
- blinking or flashing content

Who benefits most:
- autism-ambiguity
- adhd-distracted
- low-vision

Typical signals:
- animated backgrounds behind core tasks
- stacked toast storms during save or validation
- several concurrent badges, banners, and alerts
- motion-heavy transitions with no quiet mode

### Instruction Dependency
What to check:
- can the interface be used without carefully reading long instructions
- do controls communicate their purpose directly
- is success dependent on remembering hidden rules
- do users have to learn a system-specific grammar before basic use

Who benefits most:
- adhd-distracted
- autism-ambiguity
- deaf-hoh

Typical signals:
- placeholder text as primary instruction source
- long setup panels where the only real guidance is a paragraph block
- dense helper text required to decode control behavior
- tiny captions that explain destructive consequences after the action trigger

### Default Accessibility
What to check:
- are accessible choices the default path
- do users need to discover a setting before the product becomes usable
- are reduced-motion, captions, or simpler views easy to access
- do components ship with accessible defaults rather than opt-in fixes

Who benefits most:
- all populations

Typical signals:
- captions off by default where they should be on or immediately available
- safe button semantics require an opt-in prop
- motion reduction only available deep in settings
- high-contrast mode treated as a niche add-on instead of supported baseline

### Recovery and Forgiveness
What to check:
- undo paths for reversible actions
- confirmation before destructive actions
- clear recovery from validation errors
- persistence of entered data after failure
- no penalty for exploratory clicks or mistaken activation

Who benefits most:
- motor-impaired
- adhd-distracted
- autism-ambiguity

Typical signals:
- delete action placed near common action with no confirm
- failed submit clears form state
- invalid step sends user backward with lost context
- errors identify a problem but not how to recover

### Interaction Consistency
What to check:
- same action gives same result across the interface
- common controls share naming and placement patterns
- state chips, toggles, and menus behave consistently
- primary actions remain primary, not sometimes secondary

Who benefits most:
- autism-ambiguity
- adhd-distracted
- blind-sr

Typical signals:
- Save button location changes between steps
- close control is top-right in one dialog and hidden in another
- cards and rows alternate between navigation and selection behavior
- sort control label changes meaning across screens

## Real-World Constraint Simulation

Layer B must imagine the interface under real conditions, not ideal lab conditions.
Consider at least these scenarios during review:

### Distraction
Ask:
- what happens if notifications or interruptions occur mid-task
- can the user easily recover place in a dense workflow
- does the current step remain obvious after attention returns

### Fatigue
Ask:
- is the task still understandable near the end of a long session
- are there repeated small decisions that compound mental effort
- does the UI require precision or sustained vigilance that wears users down

### Stress
Ask:
- can a user recover cleanly after a mistake
- are error messages calm, direct, and action-oriented
- does failure increase complexity when the person is already frustrated

### Partial attention
Ask:
- can the user safely multitask without losing the thread
- does the next action remain obvious without rereading the whole page
- are critical instructions repeated at the moment of need rather than only once upfront

Use these simulations to deepen the analysis.
Do not use them to invent behavior that code evidence does not support.

## Exclusion Risk Assessment

For each Layer B finding, assess three things:
1. Who is excluded or substantially frustrated?
2. How severe is the exclusion: annoying, degrading, or blocking?
3. Is the issue systemic or isolated?

### Systemic versus isolated
Systemic problems deserve clear labeling because their impact spreads.
Examples:
- a base dialog pattern that never preserves context after close
- a design-system button pattern that hides labels behind icons across many screens
- a global save pattern that uses disappearing toasts as the only confirmation

Isolated problems are still important but should be described as local instances.
Example:
- one checkout screen uses an unusually dense summary panel compared with the rest of the product

## Population Coverage Discipline

All seven populations must be considered.
At the end of the phase, include an explicit note naming any populations with zero findings.
This is a gap check, not proof that the experience is perfect for them.
It simply shows the analyst remembered to consider them.

Example:
- Populations with zero Layer B findings in reviewed scope: [deaf-hoh]

Do not omit this note.

## Severity Guidance for Layer B

Use the canonical severity scale.
Severity should reflect exclusion impact, not just visual annoyance.

### CRITICAL
Use when design quality creates a practical block in a core flow.
Examples:
- a multi-step financial form presents all critical decisions at once with no grouping and no recovery path
- a confirmation timeout discards entered data in a core transactional flow

### HIGH
Use when users can finish but with major cognitive burden, confusion, or error risk.
Examples:
- long ungrouped setup form with several hidden dependencies
- destructive controls visually under-differentiated from harmless ones
- inconsistent navigation patterns across primary steps

### MEDIUM
Use when the flow is usable but meaningfully harder than it should be.
Examples:
- dense instruction panels that must be reread to proceed
- optional settings overwhelm the default screen but do not block completion

### LOW
Use when friction is noticeable but minor.
Examples:
- one extra confirmation message is wordy but recoverable
- slightly inconsistent placement of a non-critical helper link

## The 4-Pass Loop

Every phase uses the same 4-pass structure.
Phase 3 applies it to inclusive design findings.

### ANALYZE
Perform the first-pass Layer B review.
For each finding, include:
- severity
- file and line reference
- issue statement
- Layer B category
- affected populations
- impact statement
- recommendation

Check all ten categories.
If a category has no issues, say so.

### CRITIQUE
Challenge the first-pass findings.
Answer each question explicitly:
- Am I only finding obvious issues and missing subtle exclusion patterns?
- Did I check all ten Layer B categories?
- Am I just repeating Layer A instead of analyzing real usability risk?
- Did I consider distraction, fatigue, stress, and partial attention?
- Are severity levels tied to exclusion impact?
- Did I overstate certainty where only runtime or visual evidence could confirm it?
- Did I think about which populations have zero findings?

### REVISE
After critique:
- add overlooked exclusion patterns
- remove duplicated Layer A-only findings
- refine impact statements
- adjust severity where exclusion is worse or milder than first stated
- label systemic patterns clearly when they affect more than one screen or component
- strengthen recommendations so they are actionable

### VERIFY
Before Phase 3 is complete, confirm all of the following:
- all ten Layer B categories were considered
- every finding has severity, populations, category, impact, and recommendation
- at least one real-world constraint simulation informed the analysis where relevant
- populations with zero findings are explicitly listed
- Layer B remains distinct from Layer A even when issues overlap in root cause
- platform label matches Phase 1

If verification fails, return once to CRITIQUE, revise, and verify again.
If uncertainty remains, proceed with an explicit note.

## Finding Format

Use this structure exactly for individual findings.

```markdown
- severity: HIGH
  file: src/pages/Checkout.tsx:15-89
  issue: 12-field form displayed simultaneously with no logical grouping or progress indicator
  category: Cognitive Load
  population: [adhd-distracted, autism-ambiguity, low-vision]
  impact: Users under cognitive load may abandon the flow; no sense of progress
  recommendation: Group fields into logical steps such as shipping, payment, and review, with a progress indicator
```

## Output Structure

Output must begin with this header:

```markdown
## Status: COMPLETE
```

After that, organize the report by Layer B category in this order:
1. Cognitive Load
2. Clarity of Affordances
3. Predictability
4. Progressive Disclosure
5. Time Pressure
6. Sensory Burden
7. Instruction Dependency
8. Default Accessibility
9. Recovery and Forgiveness
10. Interaction Consistency
11. Populations with Zero Findings
12. Limitations and Notes
13. Configuration Applied

### Required section skeleton

```markdown
## Status: COMPLETE

### Cognitive Load
- severity: ...
  file: ...
  issue: ...
  category: Cognitive Load
  population: [...]
  impact: ...
  recommendation: ...

### Clarity of Affordances
...

### Predictability
...

### Progressive Disclosure
...

### Time Pressure
...

### Sensory Burden
...

### Instruction Dependency
...

### Default Accessibility
...

### Recovery and Forgiveness
...

### Interaction Consistency
...

### Populations with Zero Findings
- [deaf-hoh]

### Limitations and Notes
- Static analysis only; rendered sensory burden and full copy experience were inferred from code structure.

### Configuration Applied
- platform: web
- populations_focus: [blind-sr, adhd-distracted]
```

If there are no findings under a category, write:

```markdown
### Predictability
- No inclusive design issues identified from reviewed evidence in this category.
```

Do not omit empty categories.

## Review Discipline

Phase 3 should reveal design quality issues that pure standards checks can miss.
That means:
- do not stop at "label exists"
- do not stop at "keyboard works"
- do not stop at "error is announced"

Ask whether the person can stay oriented, recover, and keep going without unusual mental effort.
This is where exclusion risk becomes visible.

Useful reminders:
- a product can be standards-compliant and still exhausting
- a default that is technically adjustable may still be exclusionary if the safer path is buried
- a screen reader user can be blocked by interaction inconsistency, not only missing semantics
- cognitive accessibility issues are real accessibility issues, even when WCAG mapping is indirect

## Completion Standard

Phase 3 is complete when the output can stand on its own as an inclusive design review for Layer B.
A reader should understand which non-compliance risks matter, who is affected, how exclusion manifests in realistic use, and what design changes would reduce that exclusion.
