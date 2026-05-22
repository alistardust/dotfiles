# Prompt pattern library

### Code generation

```text
Write [language] code that [specific behavior]. Requirements:
- [Requirement 1]
- [Requirement 2]
- [Error handling approach]
- [Testing expectation]

Context: This will be used in [where/how]. The existing codebase uses [relevant conventions].
```

Use when you want a well-scoped implementation prompt.

### Code review

```text
Review the staged changes in this repo. Focus only on:
- Bugs and logic errors
- Security vulnerabilities
- Performance issues that matter at our scale

Do not comment on style, formatting, naming, or anything cosmetic.
For each issue found, state: what is wrong, why it matters, and how to fix it.
```

Use when you want a high-signal review of changes.

### Debugging

```text
I am seeing [symptom]. Expected behavior: [what should happen].
Actual behavior: [what happens instead].

What I have tried:
- [Step 1]
- [Step 2]

Relevant context:
- [Tool/service version]
- [Recent changes]
- [Error messages verbatim]

Help me find the root cause. Do not suggest fixes until we understand why this is happening.
```

Use when troubleshooting a bug and you want root cause first.

### Architecture design

```text
I need to design [system/component]. It must:
- [Functional requirement 1]
- [Functional requirement 2]
- [Non-functional requirement: scale, latency, etc.]

Constraints:
- [Technology constraints]
- [Team/org constraints]
- [Timeline constraints]

Propose 2-3 approaches with trade-offs. Recommend one and explain why.
```

Use when you need structured options before building.

### Documentation

```text
Write documentation for [component/API/process]. The audience is [who].
They need to understand: [what they will do with this knowledge].

Structure: [overview -> setup -> usage -> troubleshooting] or [appropriate structure]

Use concrete examples. No filler text. Every sentence should teach something.
```

Use when drafting docs for a defined audience.

### Testing

```text
Write tests for [function/module/endpoint]. Cover:
- Happy path with typical input
- Edge cases: [list specific edges]
- Error cases: [list specific errors]
- [Integration points if applicable]

Use [test framework]. Follow the existing test patterns in [path].
Tests must assert intended behavior, not just current behavior.
```

Use when adding tests for new or changed behavior.

### Incident investigation

```text
We have a [severity] incident affecting [service/component].
Symptoms: [what is broken from the user's perspective]
Timeline: [when it started, any recent changes]

Help me investigate. Start with: what data do we need to confirm the scope
and identify the component at fault? Do not suggest remediation until we
have a root cause hypothesis.
```

Use when starting a production investigation and you need a structured triage prompt.

### Infrastructure as code

```text
I need to [infrastructure change]. Environment: [prod/staging/dev].
Current state: [what exists now].
Desired state: [what should exist after].

Requirements:
- Must be idempotent
- Must have a rollback path
- Must not cause downtime (or: acceptable maintenance window is [X])

Write the [Terraform/Kubernetes manifest/script] and explain each resource.
```

Use when planning or generating infrastructure changes.
