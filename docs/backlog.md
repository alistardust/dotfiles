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

**Status:** open
**Context:** seeded during the adjudication rebuild; deliberately left minimal.

The deterministic criticality classifier in `skills/code-audit/SKILL.md` uses a
sensitive-path pattern list as one of its three escalation signals. The current
list covers auth, crypto, secrets, IAM, prod IaC, migrations, and CI/CD.

The list is the main lever controlling how much of a repo gets frontier
attention, so both failure directions are real: too narrow and genuinely risky
code is adjudicated at the routine rung, too broad and every run costs frontier
prices. Expand deliberately rather than defensively.

Worth considering:

- [ ] Deserialization and parsing entry points (`pickle`, `yaml`, XML, protobuf)
- [ ] Network and request boundaries where external input first lands
- [ ] Subprocess and shell invocation sites
- [ ] File upload and path-construction code
- [ ] Anything handling PHI or PII in work repos
- [ ] Per-repo overrides, so a personal project and a production service can use
      different lists

Keep the list in sync between `skills/code-audit/SKILL.md` and
`skills/skill-conductor/SKILL.md`, or make one canonical and have the other point
at it.

---

## 3. Audit the remaining skills for single-model steps

**Status:** open
**Context:** the seats model was applied to `skill-conductor*` and `code-audit`
only. Other skills were not reviewed.

The defect fixed in `code-audit` was structural rather than local: a pipeline
that looked multi-agent while a single model quietly set the outcome. Other
skills plausibly share the shape.

- [ ] Enumerate every skill that dispatches subagents or renders a verdict
- [ ] For each, identify who sets final severity or decides what blocks
- [ ] Flag any step where one model both proposes and rules
- [ ] Flag any synthesis or merge step that silently picks a winner, which is a
      single arbiter wearing the costume of a merge step
- [ ] Confirm no skill claims a capability the runtime does not have. The false
      "the agent runtime resolves tier names to actual model IDs" claim in
      `skill-conductor-review-gate` is the pattern to look for.

Known starting points: `a11y-review`, `a11y-review-deep`, `security-review`,
`review`, `hunk-reviewer`, `sql-code-review`, `postgresql-code-review`.
