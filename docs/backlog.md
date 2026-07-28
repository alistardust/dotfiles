# Backlog

Tracked follow-up work for this repo. GitHub issues are unavailable here (the
account is an Enterprise Managed User and cannot create issues on a personal
repo), so this file is the durable record.

Close an item by deleting it and referencing this file in the commit that
completes it.

---

## 1. Prove the rebuilt code-audit works on a real repo

**Status:** open
**Context:** follow-up to `82eaf37`, the adjudication rebuild.

The reporter/adjudicator pipeline in `skills/code-audit/SKILL.md` is written but
has never been executed end to end. Passing shellcheck and dry-runs does not
prove the audit produces a correct report.

Run it against a real repository and verify:

- [ ] Every finding in "Findings by Severity" carries either `adjudication` set
      or an explicit *unadjudicated* label. No finding reaches the report with an
      inherited `proposed_severity`.
- [ ] Adjudicators actually opened the cited `file:line` and quoted source in
      their rationale rather than paraphrasing the reporter.
- [ ] Reporter passes really did spread across ecosystems, and the security pass
      really did run twice.
- [ ] The deterministic criticality classifier produced sane rungs. A LOW finding
      in a test fixture must not land at `critical`.
- [ ] The Phase 1 file-census coverage check catches a stack with no matching
      manifest.
- [ ] Rejected findings appear in the appendix with rejection rationale.
- [ ] Panel splits merge by conservative arithmetic, not by a tie-breaker model.

Record actual cost and wall-clock time. Frontier models now read source during
Phase 5, so runs are meaningfully more expensive than before, and the real number
should inform whether the rigor ladder needs retuning.

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
