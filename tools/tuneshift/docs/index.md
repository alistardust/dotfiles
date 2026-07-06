# TuneShift Documentation

A one-page map of the TuneShift docs. Start at the [README](../README.md) for
install, the core model, and the command surface; use [CLAUDE.md](../CLAUDE.md)
for agent-facing architecture notes.

## Feature guides

| Document | What it covers |
|----------|----------------|
| [version-selection.md](version-selection.md) | The version-selection engine: two-phase filter/score, the 15 criteria axes, require/prefer/avoid/forbid strengths, source-aware recording verdicts, confidence tiers, deterministic tie-breaks, and how ambiguity surfaces. |
| [preferences.md](preferences.md) | The typed `(criterion, strength, target)` preference model: scopes and precedence, multi-target axes, inspecting the effective cascade, and the deprecated legacy keyword model. |
| [locks.md](locks.md) | Two-level composite identity locks: precedence, how a lock short-circuits selection, dead-lock self-heal, and version-downgrade flagging. |
| [plan-apply.md](plan-apply.md) | The plan/apply safety backbone: the plan and journal data model, the apply engine, rollback, the `plan` verbs, and which commands default to a plan. |
| [resolution-enrichment.md](resolution-enrichment.md) | Library-first add/import, the resumable resolution-queue worker, the resolver pipeline, candidate persistence, metadata hydration, coverage/quarantine, and the enrichment layer. |
| [matching-known-limits.md](matching-known-limits.md) | The honest register of what matching deliberately does not auto-resolve, and how each limit surfaces for review. |
| [CLI.md](CLI.md) | Complete flag-by-flag reference for every subcommand. |

## Task-oriented

| Document | What it covers |
|----------|----------------|
| [workflows.md](workflows.md) | End-to-end recipes for the common user journeys (resolve, triage, Atmos prefs, plan heal, per-playlist locks, resuming a resolve). |
| [roadmap.md](roadmap.md) | Known future work, deferred improvements, and intentional non-goals. |

## Reading order

New to the tool: [README](../README.md) -> [workflows.md](workflows.md) ->
the feature guide for whatever you are doing.

Working on the matching engine: [version-selection.md](version-selection.md) ->
[preferences.md](preferences.md) -> [locks.md](locks.md) ->
[matching-known-limits.md](matching-known-limits.md).

Working on syncing/mutations: [plan-apply.md](plan-apply.md) ->
[resolution-enrichment.md](resolution-enrichment.md).
