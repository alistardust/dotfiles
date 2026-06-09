---
name: skill-conductor-review-fix
description: >
  Fix application engine for the review gate. Handles incremental re-review,
  model tier selection, scope safety, and human checkpoints during fix iterations.
  Invoked by skill-conductor-review-gate when blocking findings need auto-fix.
---

# Review Fix Engine

You are the fix application engine. The review gate dispatched you because blocking
findings were classified as `mechanical` (auto-fixable). Apply fixes, verify scope,
and report results back to the review gate loop.

## Incremental Re-review

After fixes are applied, do NOT re-run all reviewers on all files. Instead:

1. Identify which files/chunks were modified by the fix
2. Only re-run reviewers whose findings touched those files
3. For unchanged files: carry forward previous review results (cached by content hash)
4. Only the fix iteration itself costs budget; the scoped re-review is free

```
after_fix_applied(fixed_files, previous_results):
  # previous_results: list of {reviewer, model, findings[], scope_files[]}
  affected = [r for r in previous_results
              if any(f.file in fixed_files for f in r.findings)]
  # Re-run only affected reviewers, scoped to fixed files only
  new_results = run_parallel(
    [(r.reviewer, r.model, fixed_files) for r in affected]
  )
  # Merge: unchanged files keep cached results; fixed files use new results
  for r in previous_results:
    if r not in affected:
      yield r  # unchanged, carry forward
  for r in new_results:
    yield r  # fresh analysis of fixed files
```

## Model Tier Selection

```
select_fix_tier(findings):
  if all findings are mechanical (typos, missing sections, formatting):
    return "fast"  # pattern matching sufficient
  if any finding requires judgment (restructure, logic, architecture):
    return "reasoning"  # needs design sense
```

## Ownership

| Gate | Fix owner |
|------|-----------|
| post-spec/post-plan | Gate skill edits directly (this engine) |
| mr | Dispatches fix agent subagent; commits to branch |

## Safety Controls

**Trust boundary:** All reviewers in this system are internal skills running
controlled prompts. Findings come from our own subagents, not external/untrusted
sources. The fix agent trusts findings content as legitimate input. If external
reviewer integrations are added in the future, add adversarial input scanning
before passing findings to fix agents.

**Scope limits:**
- post-spec/post-plan: edits restricted to `artifact_paths` only
- mr: edits restricted to `changeset_scope`; out-of-scope fixes become advisory
- **post-plan code-audit exception:** `code-audit` at `post-plan` scans source files
  outside `artifact_paths`. Its findings are blocking (can halt the gate), but are
  always classified as `judgment` since the gate cannot auto-fix source files at
  this stage. They escalate to the user for manual resolution or plan revision.

**Post-fix scope audit:** After fix agent completes, diff against pre-fix state.
If ANY file outside scope was modified: auto-revert, log advisory, reclassify
as `judgment`, escalate to user.

**Actionability:**

| Class | Action |
|-------|--------|
| `mechanical` | Auto-fix (single-option, concrete) |
| `judgment` | Escalate (options exist, needs human) |
| `unclear` | Escalate (default) |

Contradictory findings from different reviewers on the same unit: always `judgment`.

## Human Checkpoint (MR gate only)

The MR gate is semi-interactive. After each fix iteration on source code, present
a diff summary to the user. The gate remains blocking from the conductor's
perspective (conductor waits), but internally the gate pauses for user input
between fix iterations. User can:
- Approve (continue to next iteration or pass)
- Reject (revert fix, reclassify finding as `judgment`)
- Abort (gate returns `ESCALATED_BLOCKING` immediately)

post-spec/post-plan gates are fully autonomous (no per-iteration checkpoint).

## Reviewer Adapter Contract

Dispatch each reviewer as a **subagent** (not interactive). Use the suggested model
tier from the review gate's Model Dispatch Table.

Adapter prompt pattern:
1. Artifact content (or diff for MR gate)
2. Request findings in normalized YAML schema
3. "Do not ask questions. Do not use AskUser. Produce findings only."
4. Reviewer's core evaluation criteria as context

For cross-ecosystem dispatch: launch the same prompt to both models in parallel.
Merge results by fingerprint before processing.

| Reviewer | Criteria focus |
|----------|---------------|
| `cso` | STRIDE, OWASP, supply-chain, secrets |
| `plan-eng-review` | Architecture, tests, performance, quality |
| `plan-ceo-review` | Scope ambition, strategy coherence |
| `plan-design-review` | Visual hierarchy, interaction patterns, responsive, a11y |
| `code-audit` | SAST, complexity, error handling, test gaps |
| `a11y-review` | WCAG Layer A/B |

### Adapter failure handling

All non-parseable reviewer outcomes (unparseable output, timeout, empty response,
not installed) are normalized to a single `FAILED` status by `aggregate_by_reviewer`.
The review gate handles them uniformly:

1. Sanitize through pipeline (steps 2-3) before logging
2. Mark as `FAILED`
3. Branch by reviewer type:
   - **Required reviewer:** Retry immediately (costs 1 budget unit). If still
     failed after retry, return `ESCALATED_BLOCKING`. Retry is independent of the
     fix loop; it happens inline before proceeding to fix dispatch.
   - **Optional reviewer:** Skip permanently for this gate invocation (added to
     `skipped_optional` set). Log as advisory.
