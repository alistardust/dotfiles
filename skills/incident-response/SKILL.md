---
name: incident-response
description: Incident response procedure for PagerDuty pages, escalations, on-call alerts, or any active or suspected incident. Use this skill whenever responding to an incident, alert, or anything framed as a production issue.
---

## RCA before action

Before taking any remediation action, perform a full Root Cause Analysis (RCA)
and write it to a file. Investigations -- querying logs, reading metrics,
running read-only commands -- may proceed immediately and interactively without
waiting. But no change to any system, service, or configuration may be made
until the RCA is complete, unless one of the explicit exceptions below applies.

## RCA file format

Write the RCA to:
  `~/Documents/pd-incidents/<YYYY-MM-DD>-<incident-id>-rca.md`

The file must include:

- **Incident summary**: alert name, service, severity, time fired
- **Timeline**: ordered list of observed events with timestamps
- **Evidence**: specific log lines, metric values, error messages, and command
  output supporting each conclusion -- quote the actual data, not a summary
- **Root cause**: a clear, specific statement of what caused the incident, with
  a direct chain of evidence leading to that conclusion
- **Contributing factors**: anything that made the incident worse, harder to
  detect, or slower to resolve
- **Confidence**: state explicitly whether the root cause is confirmed or
  suspected, and what would confirm it if not yet certain
- **Remediation plan**: ordered steps to resolve the issue, with the expected
  outcome of each step and how to roll it back if it goes wrong

## Production changes: Ali decides

In production, Ali makes all final decisions on remediation actions. The
preferred workflow is:

1. Present the completed RCA and remediation plan
2. Walk Ali through each proposed step -- explain what it does, what could go
   wrong, and how to roll it back
3. Ask for explicit confirmation before executing each step (a direct question
   requires a direct affirmative response)
4. Never apply a production change autonomously

For any production change, **ask for confirmation twice** -- once when
presenting the plan, and once as a direct question immediately before executing
each action. Both confirmations must be affirmative responses in the current
session. This is not optional and cannot be skipped by default or convention.

## AWX troubleshooting exception

Before the RCA is complete, it is acceptable to propose running a
non-destructive, idempotent AWX job template or playbook as a troubleshooting
step -- for example, a health-check play or a facts-gathering job. This
requires:

1. Ali's explicit approval for that specific run
2. Ali initiates the job herself (via the AWX UI, tachi, or the API)

Even under this exception, AI must not trigger AWX jobs directly in production.
The proposal is: "here is the job I recommend running and why". The action is
Ali's to take.

## Non-production systems

For non-production environments, changes may be made with a single confirmation,
but the RCA and plan must still be written first unless Ali explicitly waives it.

## Immediate danger

If a system is actively causing data loss, a security breach is in progress, or
a cascading failure is spreading and every second matters, state the risk
clearly, describe the proposed immediate action, and ask Ali whether to
proceed. Do not act unilaterally even in these cases -- surface the situation
and let Ali decide.

## Incident notes

While working a PagerDuty incident, append a running summary to
`~/Documents/pd-incidents/YYYY-MM-DD.md` (one file per calendar day). After
each incident is resolved or handed off, write a full summary including:
- Incident number, title, severity, and escalation policy
- Timeline of key events (alert fired, investigated, action taken, resolved)
- Root cause (confirmed or suspected)
- Actions taken and by whom
- Resolution status and any follow-on work required
- Lessons learned or process gaps surfaced

Mirror the same summary to `~/git/tachikoma/tmp/pd-incidents/YYYY-MM-DD.md`.
