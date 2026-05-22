# Phase 1: Platform & Context Reconstruction
Purpose: determine what is being reviewed, which platform or platforms are involved, which user flows matter, and what information is missing before deeper analysis begins.

This document is an internal reference for the a11y-review-deep orchestrator.
It is not a standalone skill and is not independently runnable.
The orchestrator loads this phase on demand and executes its logic in the main context.

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
Do not relabel a non-web project as web just because the code is easier to reason about that way.

## Phase Goal

By the end of Phase 1, the orchestrator should be able to answer all of the following:
- What artifact or surface is under review?
- What platform or platforms does it belong to?
- What user-facing scope should be included?
- Which internal or utility files should be excluded from direct findings?
- Which user flows matter most for later phases?
- Which important facts are missing and must be called out as limitations?

If these questions are not answered clearly, Phase 2 should not proceed.

## Inputs the Phase May Inspect

The orchestrator may reconstruct context from any combination of the following:
- user request text
- explicitly named files
- repository root contents
- file extensions and framework markers
- design token files
- route definitions
- component exports
- README or docs that describe product behavior
- configuration from .a11y-review.yml
- diffs, if the audit is scoped to changed files

Prefer direct evidence from the codebase over guesses.
If the user request narrows the scope, honor that narrower scope unless it prevents a meaningful accessibility review.

## Default Assumptions

Apply these defaults unless stronger evidence exists:
1. Treat the review target as the files or directories named by the user.
2. If no files are named, infer whether the request is for a full codebase, a feature area, or a component set.
3. If platform is not explicitly configured, infer it from file types and framework markers.
4. If platform remains ambiguous, use unknown and skip platform-specific checks.
5. If multiple real platform families are present, use multi-platform and list each detected platform.

## Platform Detection Logic

Platform detection is Phase 1's first hard requirement.
Never start with "this is probably web" unless the evidence actually supports that conclusion.

### Highest-precedence source: .a11y-review.yml override

Check repository root for .a11y-review.yml.
If present, inspect the platform field first.

Valid values:
- web
- ios
- android
- desktop
- cross-platform-mobile
- design-system
- auto

Rules:
1. If platform is set to a concrete enum value, use it as the primary platform.
2. If platform is auto or missing, perform normal detection.
3. If config value is invalid, warn and fall back to detection.
4. If config names one platform but repository evidence strongly indicates multiple platforms, preserve the configured platform and note the mismatch under Configuration Applied.

### File extension and artifact mapping

Use the following mapping as canonical inference guidance.

| Artifact or file pattern | Infer platform | Notes |
|---|---|---|
| .html | web | Static or server-rendered UI |
| .js | web | Only if tied to browser UI, routes, or components |
| .jsx | web | React UI |
| .ts | web | Only if tied to UI, not generic tooling |
| .tsx | web | React UI |
| .vue | web | Vue UI |
| .svelte | web | Svelte UI |
| .css, .scss, .less | web | Supporting evidence, not sole evidence |
| .swift | ios | Native iOS |
| .xib | ios | Interface Builder |
| .storyboard | ios | Interface Builder |
| .kt | android | Native Android if tied to app UI |
| .xml | android | Android layout XML if in Android resource paths |
| .xaml | desktop | WPF, MAUI, WinUI |
| .cs | desktop | Desktop only if paired with XAML or desktop app structure |
| .dart | cross-platform-mobile | Flutter |
| design-tokens.json | design-system | Token packages |
| tokens.json | design-system | Token packages |
| component library stories | design-system | Storybook or equivalent |
| mixed web plus mobile artifacts | multi-platform | List all detected sub-platforms |

### Framework and repository markers

Use structure and dependency clues to strengthen or weaken extension-based inference.

Web indicators:
- package.json with react, next, vue, svelte, angular, remix, astro
- app router or pages directories
- src/components, src/pages, src/routes, public
- storybook configuration for browser components

Design-system indicators:
- packages with tokens, primitives, foundation, icons, theme
- Storybook without clear app flows
- exported reusable UI primitives rather than feature pages
- design token JSON, theme maps, CSS variable layers

iOS indicators:
- .xcodeproj, .xcworkspace
- UIKit or SwiftUI entry points
- Info.plist with app targets

Android indicators:
- AndroidManifest.xml
- app/src/main/res/layout
- Jetpack Compose or XML layouts

Desktop indicators:
- Electron app shells
- XAML desktop project structure
- MAUI or WPF project markers

Cross-platform mobile indicators:
- Flutter project structure
- React Native app folders
- shared mobile component primitives

### Multi-platform handling

If evidence shows more than one platform family, do all of the following:
1. List every detected platform.
2. Set overall platform to multi-platform.
3. Name which files or folders belong to which platform.
4. Note whether a shared design-system layer exists across platforms.
5. Tell later phases to avoid applying web-only checks to non-web files.

Example cases:
- React web app plus iOS client
- design-system package plus consuming web application
- shared token package plus Android and web front ends

### Unknown platform handling

If no reliable inference is possible:
1. Set platform to unknown.
2. Note: "Platform could not be determined; platform-specific checks skipped."
3. Continue with only shared logic that does not depend on a platform adapter.
4. Do not invent file semantics that are not evident from the code.

## Scope Determination

Phase 1 must identify what is actually in scope.
Accessibility reviews become noisy when utility files and user-facing files are mixed together.

### Possible scope shapes

#### Full codebase
Use this when the user asks for a broad audit or when the target appears to be the whole repository.
Look for:
- multiple routes or screens
- application shell files
- top-level navigation
- many user-facing components

#### Component scope
Use this when the user names a component, directory, or a small UI package.
Look for:
- a single component file
- a component folder with tests and stories
- a design-system primitive or pattern

#### Specific file scope
Use this when the user names exact files or the review is limited to a diff.
The scope stays narrow unless understanding requires opening an adjacent file such as a wrapper, hook, or style module.

### Entry point identification

For the chosen scope, identify the user-facing entry points.
Examples:
- page route files
- screen or scene components
- exported component entry files
- modal open triggers
- menu or navigation roots
- form start points
- checkout or onboarding shells

### User-facing surfaces to include

Include surfaces that a person directly experiences or that directly affect accessibility behavior:
- layout containers
- navigation menus
- forms and field groups
- dialogs and popovers
- tables, lists, grids, trees
- media players
- notifications and toasts
- async loading states
- error boundaries that present UI

### Internal or utility code to exclude from direct findings

Usually exclude the following from direct line-item findings unless they create a clear accessibility effect:
- generic utility functions with no UI output
- build scripts
- test fixtures
- mocks
- vendor code
- generated files
- icon source files that are not rendered directly
- data mappers with no user-facing behavior

If internal code clearly causes a user-facing issue, include it as supporting evidence but anchor the finding to the user-facing surface whenever possible.

### Scope notes to record

The Scope section should answer:
- what area is reviewed
- what exact directories or files are included
- what was intentionally excluded
- whether the scope is complete or sampled

## User Flow Reconstruction

Phase 1 must reconstruct the primary flows that later phases and personas will test.
A flow is a sequence of user-visible steps with a goal.

### Common flow categories

Look for evidence of:
- navigation and discovery
- login and authentication
- account setup or onboarding
- search and filtering
- form submission
- cart, checkout, or transaction flow
- document upload or media interaction
- settings and preferences
- error recovery and retry
- destructive actions with confirmation

### How to reconstruct flows

Use available code evidence to map the flow from start to completion.
Helpful sources include:
- route trees
- button and link labels
- form sections
- conditional rendering branches
- API mutation names
- progress indicators
- modal sequences
- success and error screens

Keep the flow phrased in concrete steps.
Bad: "checkout stuff happens"
Good: "Cart review -> shipping address -> delivery method -> payment -> order review -> confirmation"

### Flow detail level

Record enough detail for later testing, but not every implementation detail.
A useful flow entry should include:
- flow name
- start point
- intermediate steps
- success state
- important error or branch state

### State and authentication dependencies

Note when a flow depends on context that may not be visible in isolated files.
Examples:
- logged-in state
- role-based permissions
- persisted cart or draft state
- feature flags
- geolocation or locale
- form wizard step memory
- async data loading before interaction becomes available

If a flow cannot be fully reconstructed without runtime state, note the uncertainty explicitly.

## Missing Information Audit

Phase 1 must explicitly document what cannot be known from static code review alone.
This is mandatory because later phases must avoid overclaiming certainty.

### Common blind spots

Static code alone often cannot fully determine:
- final visual layout
- rendered spacing density
- exact color contrast ratios
- visible focus styling as actually rendered
- motion intensity and timing in runtime
- screen reader announcements from third-party widgets
- behavior gated behind authentication or remote data
- conditional states not represented in the inspected files
- browser or device-specific rendering differences

### Information that would improve confidence

Call out any missing artifact that would materially improve the review:
- screenshots
- design mocks
- recorded flow walkthroughs
- Storybook links
- runtime URL or test environment
- keyboard interaction notes
- copy deck for long forms or instructions
- token documentation or contrast specs

### Limitation phrasing

Use clear limitation statements such as:
- "Structural analysis only; rendered contrast was not measured."
- "No runtime available; dynamic announcements inferred from code structure only."
- "Authentication-dependent branches were identified but not executed."
- "Visual hierarchy was inferred from markup, not validated in a rendered UI."

Do not hide these limitations in footnotes.
They belong in Missing Information and may also be repeated in findings when relevant.

## Configuration Handling

If .a11y-review.yml is present, record what changed the phase behavior.
Relevant keys for Phase 1:
- platform
- ignore
- populations_focus
- standard
- severity_overrides
- custom_rules

Phase 1 does not apply standards logic itself, but it should capture these values so later phases can consume them.
If a config value is unknown or invalid, note the warning in Configuration Applied.

## The 4-Pass Loop

Every phase must apply the same structured loop.
Phase 1 uses it to validate platform, scope, and flow interpretation.

### ANALYZE

Perform a first-pass interpretation of:
- detected platform or platforms
- confidence level and evidence
- review scope
- included and excluded surfaces
- primary user flows
- known missing information
- applied configuration

Record explicit evidence for each major conclusion.
If confidence is weak, say so.

### CRITIQUE

Challenge the first-pass interpretation.
Answer each question explicitly:
- Am I defaulting to web without enough evidence?
- Did I confuse a design-system package with an application?
- Did I overlook a second platform in a monorepo?
- Did I treat utility files as primary review targets?
- Did I miss an important user flow such as login, checkout, or form submission?
- Did I assume runtime behavior that the code does not actually prove?
- Did I forget to note missing screenshots, rendering, or auth state?

### REVISE

Adjust the interpretation after critique.
Possible revisions include:
- change platform from web to design-system
- elevate to multi-platform and list sub-platforms
- narrow scope from full repo to named component area
- add overlooked flows
- remove flows that were guessed rather than evidenced
- expand missing information notes
- add configuration mismatch notes

### VERIFY

Confirm that Phase 1 output is ready for Phase 2 only if all of the following are true:
- platform is stated using the canonical enum
- scope is explicit
- at least one user flow is identified, or the absence of flows is explained
- missing information is explicitly listed
- configuration handling is documented
- limitations are visible enough to prevent overclaiming later

If verification fails, return once to CRITIQUE with the failure reason, revise, and verify again.
If uncertainty remains after one retry, proceed with a visible note about the unresolved ambiguity.

## Expected Output Format

Use this structure exactly so downstream phases can read it consistently.

```markdown
## Status: COMPLETE

### Platform
[detected platform and confidence]

### Scope
[what is being reviewed]

### User Flows Identified
1. [flow name]: [steps]
2. ...

### Missing Information
- [what cannot be determined]

### Configuration Applied
[from .a11y-review.yml or defaults]
```

## Output Guidance

### Platform section
Include:
- final platform label
- confidence level such as high, medium, or low
- evidence summary
- note if V1 platform-specific checks are unavailable

Example:
- web, high confidence: TSX route files, form pages, browser event handlers
- design-system, medium confidence: token package plus primitive components, limited end-user flow evidence
- multi-platform, high confidence: React web app plus Android layout resources detected

### Scope section
State the actual review boundary in plain language.
Examples:
- Full codebase audit of user-facing web application routes and shared layout components; vendor and test fixtures excluded.
- Component review of Button, Dialog, and Menu primitives in packages/ui; build scripts excluded.
- File-scoped review of src/pages/Checkout.tsx and directly related form subcomponents.

### User Flows Identified section
Prefer numbered flows with concise step sequences.
If no real flow can be reconstructed because the target is a primitive component set, say so and substitute component usage contexts.

Example:
1. Sign in: landing page -> email field -> password field -> submit -> inline error or dashboard
2. Checkout: cart -> shipping form -> payment form -> review -> confirmation

### Missing Information section
List only true limitations.
Do not invent missing artifacts.
Include anything that could materially affect confidence.

### Configuration Applied section
Summarize detected config or defaults.
Examples:
- No .a11y-review.yml found; defaults used.
- Config applied: platform=web, ignore=[third-party/vendor/**], populations_focus=[blind-sr, adhd-distracted]
- Config warning: unknown key custom_theme_rules ignored.

## Completion Standard

Phase 1 is complete when another analyst could read the output and know:
- what is being reviewed
- how platform was determined
- what flows matter most
- where certainty ends

Do not proceed with hidden ambiguity.
Document it.
