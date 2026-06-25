---
name: operational-knowledge-capture
description: >-
  Procedures for capturing operational knowledge during and after work.
  Use this skill when finishing an incident, noticing a repetitive manual
  task, finding a bug in tachi, or identifying tech debt that should be tracked.
---

# Operational Knowledge Capture

These practices serve two purposes: building Ali's personal knowledge base, and
feeding real operational patterns back into tachi so future automation and
workflows can be built from lived experience.

## PD Incident Notes

PagerDuty incident capture follows the procedure in the `incident-response`
skill. This section covers only the file destinations:

- Primary: `~/Documents/pd-incidents/YYYY-MM-DD.md` (one per calendar day)
- Mirror: `~/git/tachikoma/tmp/pd-incidents/YYYY-MM-DD.md`

Create files if they do not exist. For the full summary template and required
fields, see `incident-response`.

## PagerDuty Query Defaults

When querying or listing PagerDuty incidents, scope results to the current user
and their active on-call escalation policies by default, unless the request
explicitly asks for a broader scope. Resolve user identity and on-call schedule
dynamically from the configured API token at query time: do not use hardcoded
user IDs or policy IDs.

## Improvement and Automation Tracking

When performing or observing tasks that are repetitive, manual, fragile, or
undocumented, append a note to the appropriate file under
`~/Documents/routine-tasks/`. Create the directory and file if they do not
exist.

- **`ansible-automation.md`** -- tasks suited for Ansible/AWX: cert rotations,
  service restarts, disk expansion, maintenance window orchestration. Include:
  task description, trigger, rough playbook sketch, priority (high/medium/low).
- **`terraform-automation.md`** -- infrastructure patterns currently done
  manually that should be codified: EC2 tagging, EBS sizing, IAM roles, S3
  lifecycle rules. Include: what is manual today, target state, estimated scope.
- **`bugs.md`** -- open bugs in tachi (the CLI tool itself). When a bug is
  discovered, add an entry: command/module affected, behavior observed, root
  cause if known, and workaround if any. When the bug is fixed, **remove the
  entry** -- this is a live list of open issues, not a history. Fix history
  belongs in commit messages and `CHANGELOG.md`.
- **`tech-debt.md`** -- broader infrastructure and operational issues:
  workarounds, architectural gaps, missing tooling, patterns that degrade
  reliability or increase toil. Use severity labels (CRITICAL/HIGH/MEDIUM/LOW).
  Include: description, impact, context, suggested fix. Do not use this for
  tachi bugs -- those go in `bugs.md`.

## Tachi Feature Ideas

When you notice a tachi capability gap: something tachi doesn't do that
would save repeated manual work: append it to `IDEAS.md` in
`~/git/tachikoma/`. Create the file if it does not exist. This is a flat
catch-all; format is loose. Include:
- What the command would look like (`tachi <module> <subcommand>`)
- What it replaces (the manual operation)
- Why it matters (frequency, incident impact, toil reduction)

This is distinct from `tech-debt.md` (infrastructure/tooling gaps) and
`bugs.md` (broken tachi behavior). Feature ideas for tachi go in `IDEAS.md`,
not in `ARCHITECTURE.md`.


## Tachi Agent Runbook

When encountering environment-specific patterns, authentication gotchas,
host/service relationships, or procedures that took meaningful effort to work
out, add them to `~/git/tachikoma/AGENT_RUNBOOK.md`. Focus on
knowledge that would save a future agent session significant time; not general
Ansible or AWS docs.
