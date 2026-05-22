# Trust, safety, and knowing when to verify

AI output is a draft, not a fact. Treat it the same way you would treat a suggestion from a new team member who is smart but unfamiliar with your systems: useful, often directionally right, but not yet trusted. Verify before you rely on it.

A simple example is the hallucinated CLI flag. The command looks plausible because it follows real Terraform naming patterns, but one flag is invented.

```bash
# The AI suggested this flag, which does not exist:
terraform plan -detailed-exitcode -refresh-only -target-drift

# The actual correct command:
terraform plan -detailed-exitcode -refresh-only
```

The problem is not that the AI is malicious. The problem is that it is optimized to produce a likely-looking answer, and likely-looking is not the same thing as correct. Your job as an engineer is to separate suggestion from fact before that suggestion reaches production.

### Hallucination patterns to watch for

These failure modes repeat often enough that you should learn to spot them on sight.

1. **Made-up CLI flags**: Flags that sound right because they match the tool's style but were never implemented.
   - `kubectl get pods --show-health`
   - `ansible-playbook --safe-mode`
   - `aws ecs update-service --verify-deployment`

2. **Nonexistent API endpoints**: Paths that follow the product's naming pattern but do not actually exist.
   - `GET /api/v1/incidents/{id}/timeline/export`
   - `POST /v2/maintenance-windows/preview`
   - `GET /clusters/{name}/nodegroups/{id}/healthz`

3. **Plausible-but-wrong configuration**: Syntax that looks valid, but for a different version or product variant than the one you are using.
   - Terraform 0.12-style interpolation habits carried into a Terraform 1.x codebase.
   - Kubernetes config fields shown for an API version your cluster no longer supports.
   - Ansible examples using module parameters removed in later collections.

4. **Outdated version-specific behavior**: Information that was once true but is now stale.
   - AWS service limits quoted from years-old defaults.
   - Old GitHub Actions syntax presented as if it were still current.
   - Deprecated Kubernetes authentication guidance treated as standard practice.

The common thread is confidence without grounding. If the answer depends on a version, provider, API revision, or account-specific behavior, verify it against current docs or the live tool help.

### Credential safety

Treat every AI conversation as a place where secrets do not belong.

- Never paste secrets, tokens, API keys, or passwords into an AI conversation.
- If you need to reference a credential, use the variable name. Say `The token is stored in $VAULT_TOKEN`, not the token value.
- If a credential appears in AI output because you pasted an unsanitized log, treat it as exposed. Stop, rotate the credential, then continue.
- Use environment variables, vault references, or config file paths: never inline values.
- Cross-reference Chapter 2's authentication section for safe token storage patterns.

This rule matters even more during incident work, when people are tempted to paste whatever they are looking at. Slow down long enough to redact first.

### Production systems

The principle is simple: AI proposes, you verify and execute.

```bash
# Let the AI WRITE the command, but YOU review and run it:
# AI suggests:
terraform apply -auto-approve -target=module.rds

# You verify first:
terraform plan -target=module.rds
# Review the plan output manually
# Only then:
terraform apply -target=module.rds
```

For production and other high-risk environments, follow these rules:

- Always use `--dry-run`, `--check --diff`, or `plan` before `apply` or `run`.
- Never let the AI execute destructive operations directly.
- State the environment explicitly before any mutating operation.
- Require confirmation at each step, not blanket approval for a whole sequence.

This is not bureaucracy. It is how you keep a helpful drafting tool from turning into an outage multiplier.

### Sensitive data awareness

Check your organization's data handling policy before pasting logs, configs, or datasets into AI tools. Some organizations allow source code but not customer records, production credentials, incident exports, or unredacted logs. If you are unsure whether a data class is approved for AI use, stop and verify the policy first.

### The verification habit

Before declaring any AI-generated change done, run the same checks you would expect from a careful peer review.

1. Run the test suite and confirm it passes.
2. Read the diff line by line: do not skim.
3. Verify the behavior matches your intent, not just that it compiles.
4. Check for side effects. Did the AI modify anything you did not ask for?
5. For infrastructure changes, run `plan` or `--check` and review the output.

The habit to build is simple: do not ask "did the AI finish?" Ask "did I verify the result?"

### When not to use AI

There are situations where human judgment must lead and the AI should stay in a supporting role.

1. **Highly sensitive production changes**: Database migrations on live systems, security group modifications on production, or credential rotation without a tested rollback. The AI can help plan and review, but a human must verify and execute each step.
2. **Novel security decisions**: Authentication architecture, access control design, threat-model tradeoffs, and third-party security posture reviews depend on current context and risk appetite. The AI may help enumerate options, but it should not be the decision-maker.
3. **Catastrophic-failure-risk scenarios**: Anything where being wrong could cause data loss, extended outage, or compliance violation. Use AI for research and planning, then gate execution on human review.

If the blast radius is high, the AI should make you slower in a good way.

---

[< Real-world workflows](workflows.md) | [Quick start checklist >](quickstart.md)
