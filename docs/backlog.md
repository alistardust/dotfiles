# Backlog

Tracked follow-up work for this repo. GitHub issues are unavailable here (the
account is an Enterprise Managed User and cannot create issues on a personal
repo), so this file is the durable record.

Close an item by deleting it and referencing this file in the commit that
completes it.

---

## 1. Prove the rebuilt code-audit works on a real repo

**Status:** done (2026-07-28)
**Context:** follow-up to `82eaf37`, the adjudication rebuild.

Executed scoped against `tools/tuneshift` (`platforms/`, `identity/`, `db.py`;
17 files, 6307 LOC). Report: session files,
`audit-report-tuneshift-scoped-2026-07-28.md`.

- [x] Every finding carries an adjudication verdict. All 8 non-INFO findings were
      verified by opening the cited line; none inherited a proposed severity.
- [x] Adjudication quoted source. Killed 3 ruff F821 "undefined name" findings as
      string annotations with function-local imports, and 16 of 18 bandit B608
      SQL-injection alerts as placeholder expansion or allowlisted columns.
- [x] Reporters spread across ecosystems (OpenAI, Google); security pass doubled.
- [x] Criticality classifier behaved. `db.py` hit `critical` via SAST
      corroboration, `auth.py` via path, `spotify.py`/`ytmusic.py` via content
      (`subprocess.`). Nothing trivial landed at `critical`.
- [x] Rejected findings recorded with rationale.
- [x] A panel split resolved by arithmetic, no tie-breaker dispatched. On
      `db.py:3797` Google proposed INFO claiming an allowlist that does not exist
      in that function; OpenAI proposed LOW. LOW carried.

**Not exercised:** the Phase 1 coverage check had nothing to catch (100% Python,
single stack). Still unproven against a polyglot repo.

**Cost/time:** ~11 min wall clock. Reporters ran 5.5 and 9.3 min in parallel
(Google was ~70% slower for comparable depth). Deterministic scans under 2 min.
Adjudication was the orchestrator reading ~10 source regions directly, which was
cheaper than dispatching subagent adjudicators would have been.

**Value evidence:** the doubled security pass justified its cost, but not in the
way first recorded here. The original entry credited it with catching a live
functional bug at `ytmusic.py:110`. **That finding was wrong and has been
retracted.** The code was correct; the audit's own file-reading layer redacts
credential-shaped literals, so a valid bearer-token f-string was displayed as a
hardcoded mask and the pipeline faithfully reported the artifact. Byte-level
verification disproved it.

What the spread actually bought was better: the second ecosystem's pass is what
surfaced the redaction defect itself. One lineage produced the false finding, a
different lineage noticed the reading was untrustworthy. That is a stronger
result than catching an ordinary bug, because it caught a flaw in the
instrument rather than in the sample, and it is precisely the failure a
single-lineage panel cannot catch: every member would have confirmed the HIGH
against the same corrupted view, unanimously and wrongly. Fixed in the skill by
a mandatory byte-level verification rule for credential-shaped evidence.

The precision half also held: 20 of 28 tool findings were false positives that
adjudication removed.

**Second run (frozen snapshot, full package).** Re-run against a detached
worktree at `d2c0895` covering all 390 Python files / 35,941 source LOC, because
`db.py` had been decomposed 3873 lines -> 60 and the original scope no longer
mapped. Results in the re-audit report. Three things worth carrying forward:

- **A reporter failed silently.** The Google correctness pass returned completely
  empty after 2h18m and one turn. The quality gate caught it (<100 words =
  FAILED), but only because a human was watching the clock; nothing in the skill
  bounds a reporter's runtime. Re-dispatched across two ecosystems, both of which
  returned in 6-8 minutes. **Add a hard reporter timeout.**
- **Spread paid again, measurably.** The two replacement reporters overlapped on
  one finding and were otherwise disjoint: OpenAI found pin-collision and
  lock-fallback issues Anthropic missed; Anthropic found a rollback-journal issue
  OpenAI missed.
- **Adjudication corrected a reporter's reasoning, not just its severity.** On
  `apply.py:326` the reporter had the location right and the mechanism wrong
  (claimed re-reversal "re-applies mutations"; restore is idempotent). Two
  adjudicators independently downgraded HIGH -> MEDIUM for the same reason while
  preserving the real defect underneath. A pipeline that only voted on severity
  would have kept a finding whose stated justification was false.
- **A dissent sharpened a CRITICAL instead of softening it.** Google's
  adjudication was the only one to argue the bug needs an *asymmetric* failure
  (read fails, write succeeds) and might be implausible. That argument was
  defeated by the target's own test fixtures, which instantiate exactly that
  asymmetry in five files. Unanimous CRITICAL across three ecosystems.

---

## 2. Expand the sensitive-path list

**Status:** done in `94d49ce`.

Widened the path list, added deterministic content patterns so a dangerous file
with an innocuous name still escalates, and added per-repo overrides via
`.code-audit.yml`. `skill-conductor` now points at `code-audit` as canonical
instead of keeping a second narrower copy.

Still open as a tuning question rather than a task: the real cost and hit rate
are unknown until item 1 runs. Revisit the thresholds with real numbers.

---

## 3. Audit the remaining skills for single-model steps

**Status:** done in `be9c553`.

Two reporters from different ecosystems audited every skill that dispatches
subagents or renders a verdict. Findings were adjudicated against source.

Fixed: `security-review` (set final severity with no tier requirement),
`a11y-review-deep` (synthesis phase picked winners without re-reading evidence),
`secret-patterns` (instructed the model to compute Shannon entropy inline, which
it cannot do and would silently fake), `hunk-reviewer` (framing implied a
verdict), `a11y-review` (unlabeled single-model synthesis), and
`skill-conductor-test-gate` (tautological-assertion repair assigned to fast).

Rejected: the `brainstorming` spec-review loop, which escalates to a human and
gates on user review.

Not examined, and worth a pass if these ever grow verdict steps:
`awx-job-execution`, `conventional-commit`, `draw-io-diagram-generator`,
`operational-knowledge-capture`, `pdf-reader`, `pytest-coverage`,
`team-directory`, `tmux-rename`, `update-copilot-instructions`,
`using-git-worktrees`, `skill-conductor-context`, `skill-conductor-execution`.

---

## 4. Fix the CRITICAL rollback data-wipe in `tools/tuneshift`

**Status:** open. **Urgent: do this before the next sync run.**
**Found by:** full re-audit, 2026-07-28. Unanimous CRITICAL across three
adjudicator ecosystems (Anthropic, OpenAI, Google), each having read the source.

`planapply/sync.py` can permanently destroy a remote playlist during a rollback:

1. `_remote_ids()` (`sync.py:51-57`) catches all exceptions and returns `None`.
2. `make_sync_executor` (`sync.py:207-214`) calls `replace_playlist_tracks()`
   anyway, journaling `{"track_ids": None}` as the prior state.
3. `build_compensating_plan` (`sync.py:248`) does
   `prior.get("track_ids") or []`, converting "prior state UNKNOWN" into "prior
   state was EMPTY".
4. Applying that plan calls `replace_playlist_tracks(id, [])`, which clears the
   playlist on all three clients (verified in `spotify.py:318`, `tidal.py:348`,
   `ytmusic.py:410`).

Reachable via `tuneshift plan rollback <id>` -> `tuneshift plan apply <id>`.

The preconditions are correlated, not independent: a user reaches for rollback
*because* a sync misbehaved, and a flaky connection causes both the misbehaviour
and the failed snapshot read. The recovery mechanism is most dangerous exactly
when it is needed.

- [ ] Fail closed in the executor when `_remote_ids()` returns `None`: refuse to
      push rather than perform an unreversible change. A newly created playlist
      has a legitimately known prior state of `[]`; distinguish the two.
- [ ] Make `build_compensating_plan` reject unknown `track_ids` instead of
      coercing to `[]`.
- [ ] Narrow the bare `except Exception` in `_remote_ids` so permanent failures
      (404/403) are distinguishable from transient ones.
- [ ] Regression test: snapshot read fails, sync applies, rollback runs. Assert
      no destructive empty push is generated.

---

## 5. Fix the stale rollback journal in `tools/tuneshift`

**Status:** open (MEDIUM). Two adjudicators, two ecosystems.

`rollback_plan` (`planapply/apply.py:326-328`) only calls `clear_journal` when
`remote_skipped == 0`, so the journal survives for every plan containing a remote
push, which is every sync plan. The docstring promises the opposite: "On success
the journal is cleared so the plan cannot be rolled back twice."

An immediate second rollback is harmless (`_reverse_one` restores absolute prior
state and `_restore_row` is an idempotent upsert). The real risks are that a
later rollback overwrites *newer* work with stale prior values, and that the
surviving remote entry lets item 4's destructive compensating plan be regenerated
repeatedly. `models.py:34` has no `rolled-back` status, so nothing can guard it.

- [ ] Clear the journal unconditionally after the `RollbackReport` is built; the
      report already carries the remote snapshots it needs.
- [ ] Test that a second rollback is a no-op and preserves later local edits.

---

## 6. Stop normalizing "prior state unknown" in the tuneshift test fixtures

**Status:** open. This is a testing-practice defect, not a code defect, and it is
why item 4 survived to production.

Five test files set the standard mock to make the remote read fail while the
write succeeds:

```
tests/test_order_retention.py:82
tests/test_sync_cmd.py:38
tests/integration/test_lock_consistency.py:42
tests/test_sync_records_last_synced.py:28
tests/test_sync_persist_order.py:37
```

```python
# Remote read isn't enumerable in tests -> prior order unknown -> never an
# idempotent skip, so a genuine push is always planned.
client.get_playlist_tracks.side_effect = TypeError("no live remote in test")
```

The dangerous state was made the *default fixture*, as a convenience to force a
push past the idempotency check. Every sync test therefore exercises the branch
that loses the prior snapshot and asserts success. The suite is structurally
incapable of catching this bug class, and it also encodes the asymmetric failure
(read fails, write succeeds) that the one dissenting adjudicator hoped was
implausible.

- [ ] Give the mock an enumerable remote read; force the non-idempotent path
      explicitly per-test where it is actually wanted.
- [ ] Keep one test that asserts the *failed* read is handled safely.

**Lesson worth generalizing:** a test convenience that makes an error state the
default teaches the whole suite that the error state is normal.

---

## 7. Bound reporter runtime in `code-audit`

**Status:** open.

The skill sets per-agent timeouts for Phase 3 skills-hub agents but nothing
bounds a custom reporter dispatched in Phase 3/4. A Google correctness reporter
ran 2h18m and returned completely empty. The <100-word quality gate caught it
after the fact, but only because a human noticed the elapsed time.

- [ ] Hard timeout per reporter, with automatic re-dispatch to a different
      ecosystem on empty or failed return.
- [ ] Record the re-dispatch in the report's methodology so a silently retried
      pass is visible.
