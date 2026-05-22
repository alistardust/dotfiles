# Phase 4: Persona Simulation
Purpose: Simulate key user flows from the perspective of seven representative disabled users using parallel explore subagents.

## Goal

This phase converts the flow inventory from Phase 1 into perspective-specific
user simulation. Each persona reasons about the same flows, but through a
different constraint set. The phase should surface blockers, friction, and
confusion that are easy to miss in standards-only review.

Phase 4 is additive, not optional in spirit. Even partial persona coverage can
reveal issues that are not obvious from static code review. If some personas do
not complete, preserve the results that did complete and disclose the gap.

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

## Preconditions

Before dispatching personas, confirm:
- Phase 1 output exists.
- User flows were identified in Phase 1.
- Platform and scope are known.
- Relevant artifact excerpts are ready.
- Any populations_focus override was applied.
- Manifest status was updated to running.

If Phase 1 produced weak flow detail, derive a minimal fallback flow list from
routes, stories, component docs, or page structure and note that fallback in the
aggregate output.

## Required Inputs

Every persona subagent should receive:
- the persona prompt
- the artifact being reviewed
- the identified flows from Phase 1
- platform and scope summary
- concise instructions to stay grounded in evidence

Useful artifact forms:
- code excerpts
- component tree
- page structure
- route map
- landmark layout
- dialog and menu structure
- field labels and validation behavior
- notes from Phase 2 or Phase 3 that sharpen the simulation

## Parallel Dispatch Model

Dispatch one explore agent per in-scope persona.

Normal case:
- dispatch all seven personas in parallel

Focused case:
- dispatch only personas named in populations_focus
- treat all others as not-run, not as passed

The core question for every persona is the same: can this user navigate each
flow successfully, and if not, where does friction or failure occur?

## Subagent Dispatch Pattern

Use this exact pattern:

```text
For each persona (dispatched in parallel as explore agents):
  1. Provide persona prompt (role, constraints, what to look for)
  2. Provide the artifact being reviewed (code, component tree, page structure)
  3. Provide identified user flows from Phase 1
  4. Ask: "Navigate each flow as this user. Report friction points and failures."
```

Operational rules:
- Keep each prompt self-contained.
- Include the same flow list for all personas unless config narrows scope.
- Ask for step-by-step reasoning from the persona viewpoint.
- Require grounded evidence.
- Do not ask the subagent to invent runtime behavior.

## Shared Dispatch Template

Use this scaffold for every subagent launch.
Replace bracketed fields before dispatch.

```text
You are performing Phase 4 of a deep accessibility review.

Persona:
[persona prompt]

Platform:
[platform enum]

Scope:
[scope summary]

Artifact being reviewed:
[code, component tree, page structure, route list, or equivalent]

Identified user flows from Phase 1:
[flow list]

Instructions:
- Navigate each flow as this user.
- Report friction points and failures.
- Stay grounded in the provided artifact and cited evidence.
- Do not invent runtime facts that are not observable in source or docs.
- If evidence is partial, say what is uncertain.
- Mark a flow BLOCKED if the user would reasonably fail to complete it.
- Mark a flow FRICTION if completion is possible but materially harder.
- Mark a flow PASS only if no meaningful issue is found.
- Report what happens at each step from this persona's perspective.
- Prefer file references or artifact references where available.

Return YAML using the required schema only.
```

## Flow Packaging Guidance

When preparing the flow list for a persona, include:
- flow name
- start point
- major steps
- expected success state
- major UI primitives involved

Good flow names are action-oriented and concrete:
- Sign in and recover from an invalid password
- Open a settings dialog and save changes
- Browse results and apply filters
- Complete checkout and confirm submission

Weak flow names are too broad:
- Navigation
- Forms
- General usage

## Persona Prompt: blind-sr

Use this prompt verbatim:

```text
You are a blind user navigating with a screen reader (NVDA/JAWS on web, VoiceOver on mobile). You cannot see the page. You hear content linearized in DOM order. Focus on: Are all elements labeled? Is reading order logical? Are dynamic changes announced? Can you tell where you are? Report what you hear at each step.
```

Focus areas:
- accessible names
- logical reading order
- heading and landmark utility
- state and error announcements
- current location awareness
- dynamic content changes

Strong evidence examples:
- unlabeled control
- repeated vague button names
- visual order not matching DOM order
- error or toast not announced
- dialog open state not conveyed

## Persona Prompt: keyboard-only

Use this prompt verbatim:

```text
You are a motor-impaired user who cannot use a mouse. You navigate exclusively with Tab, Shift+Tab, Enter, Space, and arrow keys. Focus on: Can you reach all interactive elements? Is focus visible? Are there focus traps? Are skip links available? Can you operate all controls?
```

Focus areas:
- tab order completeness
- visible focus
- keyboard activation support
- skip link access
- dialog and menu escape paths
- focus trap or focus loss behavior

Strong evidence examples:
- interactive element not tabbable
- onClick pattern with no key support
- modal that does not trap focus
- hidden skip link that never appears on focus
- focus indicator removed without replacement

## Persona Prompt: low-vision

Use this prompt verbatim:

```text
You are a low-vision user with browser zoom at 200-400% and high-contrast mode enabled. Focus on: Does content reflow? Is anything clipped or hidden? Do layouts break? Are there spatial relationships that disappear at zoom? Does high-contrast mode hide information?
```

Focus areas:
- zoom reflow
- clipping and overflow
- layout breakage
- reliance on spatial grouping
- high-contrast compatibility
- loss of meaning carried by color or position

Strong evidence examples:
- fixed height clipping text
- overflow hidden masking controls
- no stacked fallback for wide side-by-side layout
- status communicated by color alone
- contrast-dependent icon or divider carrying meaning

## Persona Prompt: motor-impaired

Use this prompt verbatim:

```text
You are a user with limited dexterity using a switch device or head tracker. You move slowly and imprecisely. Focus on: Are targets large enough (44x44px minimum)? Do any interactions require precision (hover, drag, small clicks)? Are there time limits you cannot meet? Can you undo mistakes easily?
```

Focus areas:
- target size
- control spacing
- precision-dependent interactions
- drag or hover dependence
- timing pressure
- error recovery and undo

Strong evidence examples:
- tiny icon hit targets
- destructive action too close to safe action
- drag-only reorder interaction
- hover-reveal action with no alternative
- expiring task with no extension path

## Persona Prompt: deaf-hoh

Use this prompt verbatim:

```text
You are a deaf user. You cannot hear audio. Focus on: Is there audio-only information without text alternatives? Are videos captioned? Are sound-based alerts also shown visually? Are there any hearing-dependent interactions?
```

Focus areas:
- captions
- transcripts or text equivalents
- visual parity for alerts
- audio-only completion or warning cues
- hearing-dependent task steps

Strong evidence examples:
- media with no caption source
- spoken instructions without text equivalent
- sound-only success or error cue
- alert tied only to audio playback

## Persona Prompt: adhd-distracted

Use this prompt verbatim:

```text
You are a user with ADHD navigating while distracted. Your working memory is limited and you are easily interrupted. Focus on: Is there visual hierarchy to guide attention? Are primary actions obvious? Is there too much text without structure? Are there notifications or animations competing for attention? Can you resume after being interrupted?
```

Focus areas:
- visual hierarchy
- primary action clarity
- chunking and scan support
- interruption recovery
- competing notifications
- animation or motion overload
- form progress continuity

Strong evidence examples:
- dense wall-of-text instructions
- competing call-to-action buttons
- interruptive notification stack
- auto-rotating or moving content near the task
- multi-step flow with weak progress cues

## Persona Prompt: autism-ambiguity

Use this prompt verbatim:

```text
You are an autistic user sensitive to ambiguity and unpredictability. Focus on: Are labels and instructions precise and unambiguous? Is the interface consistent (same action always produces same result)? Are there unexpected behaviors (popups, redirects, changing layouts)? Is system state always clear?
```

Focus areas:
- precise labels
- consistent outcomes
- predictable navigation
- clear state communication
- hidden rules and ambiguous instructions
- unexpected layout or route changes

Strong evidence examples:
- vague labels such as Continue or Done
- inconsistent outcome for the same action label
- auto-redirect with no explanation
- unclear toggle state
- validation message that does not explain how to recover

## Persona Output Schema

Each subagent must return YAML in this exact shape:

```yaml
persona: [persona-id]
flows_tested:
  - flow: [flow name from Phase 1]
    result: PASS | FRICTION | BLOCKED
    steps:
      - step: [description]
        severity: [CRITICAL|HIGH|MEDIUM|LOW]
        issue: [what happened]
        impact: [effect on this user]
        recommendation: [specific fix]
```

Schema rules:
- persona must be one canonical id
- every tested flow must be listed
- PASS means no material issue found in that flow
- FRICTION means completion is possible but meaningfully harder
- BLOCKED means completion would likely fail
- recommendations must be specific

## Severity Guidance

Use this interpretation:
- CRITICAL: the flow is blocked or nearly blocked
- HIGH: serious difficulty, repeated failure risk, or major confusion
- MEDIUM: real friction, delay, or cognitive burden
- LOW: minor but noticeable reduction in usability

Important rule:
- Any flow marked BLOCKED should become a CRITICAL finding in the aggregate output
  unless there is strong evidence to justify a narrower interpretation.

## Handling Subagent Results

Apply these rules exactly:
- Wait for all subagents (30s timeout per persona)
- If a persona times out: mark as `skipped` in output
- Collect all findings, tag with persona source
- Note which flows were BLOCKED (these become CRITICAL findings)
- Note which populations had zero friction (suspicious; may indicate insufficient simulation)

Additional handling rules:
- malformed YAML should be salvaged only if the result is still reliable
- execution failure should usually be surfaced as skipped with reason
- one persona failure must not fail the whole phase
- preserve completed persona outputs even when others time out

## 4-Pass Aggregation Loop

After collecting subagent results, apply the 4-pass loop to the aggregate output:

### PASS 1: ANALYZE
- Compile all persona findings into unified structure
- Count blocked/friction/pass flows per persona
- Identify which personas found unique issues not caught by Phases 2-3

### PASS 2: CRITIQUE
- [ ] Are any persona results suspiciously clean (zero friction on complex flows)?
- [ ] Are results too generic (could apply to any codebase)?
- [ ] Did any persona just repeat Phase 2/3 findings without persona-specific insight?
- [ ] Are severity levels consistent with the persona's actual constraint?
- [ ] Did low-vision persona actually consider zoom? Did keyboard-only consider focus?

### PASS 3: REVISE
- Flag suspiciously clean results with a note (do not fabricate findings)
- Elevate severity where persona constraint makes impact worse than raw standard suggests
- Note which findings are truly unique to persona perspective vs already found

### PASS 4: VERIFY
- Every persona has a result or explicit skip
- Blocked flows are highlighted as CRITICAL
- Summary table is complete
- No contradictions (same flow cannot be PASS for one persona and BLOCKED for same persona with stricter constraints)

## Aggregate Output Structure

The phase output must include:
- `## Status: COMPLETE` header
- Results per persona (or `skipped` with reason)
- Summary table: persona | flows_pass | flows_friction | flows_blocked

Recommended structure:

```markdown
# Phase 4: Persona Simulation
Purpose: Simulate key user flows from the perspective of seven representative disabled users using parallel explore subagents.

## Status: COMPLETE

## Scope
- Platform: [platform]
- Scope: [scope]
- Flows evaluated: [count]
- Personas attempted: [count]

## Blocked Flow Summary
- [flow]: blocked for [persona ids]

## Suspiciously Clean Populations
- [persona ids or none]

## Persona Results
### blind-sr
[results or skipped reason]

### keyboard-only
[results or skipped reason]

## Summary Table
| Persona | Flows Pass | Flows Friction | Flows Blocked |
|---------|------------|----------------|---------------|
```

## Suspicion Checks

Treat these conditions as suspicious and note them explicitly:
- a persona tested several complex flows and reported zero friction
- multiple personas reported PASS on flows already known to have strong issues
- a persona report contains no step reasoning
- a report is generic enough to fit any codebase
- low-vision or keyboard-only output lacks zoom or focus analysis

## Completion Checklist

Before marking Phase 4 complete, confirm:
- all in-scope personas were attempted
- timeout handling was applied consistently
- every persona has a result section or skipped note
- blocked flows were called out explicitly
- suspiciously clean populations were noted
- summary table is present
- output is ASCII-safe only
- no em-dashes appear
- severity labels are uppercase only

## Exit Condition

This phase is complete when the aggregate persona report exists, every in-scope
persona is represented, blocked flows are visible, and the output is ready for
synthesis.
