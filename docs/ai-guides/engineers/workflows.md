# Real-world DevOps workflows

The fastest way to get value from these tools is to use them on real delivery and operations work. The patterns below are not toy examples. They are the kinds of prompts that save time when systems are noisy and you need the AI to be precise.

### Workflow 1: Debug a failing CI/CD pipeline

**Scenario**

A release pipeline started failing in the `integration-tests` job after the runner image was updated. Builds still compile, but containers fail when the test stage tries to start dependent services. You need root cause quickly so delivery does not stall.

**Skill invocations**

1. `systematic-debugging`
2. `investigate`

**Prompt example**

```text
Use systematic-debugging and investigate for this pipeline failure.

Pipeline: deploy-api
Failed job: integration-tests
Symptoms: the build succeeds, but the docker-compose test environment fails to start and the job exits after health checks time out.
Recent context: the GitHub Actions runner image changed this morning and the base test image was rebuilt last night.

I need:
1. The top three hypotheses ranked by probability
2. The first logs, commands, or artifacts to inspect for each
3. What evidence would confirm or rule out each
4. The lowest-risk mitigation if we need to unblock merges before the root cause is fully fixed
```

**Expected AI actions**

- Rank likely causes such as runner drift, container image regressions, or dependency startup ordering.
- Point to the first job logs, artifacts, and config diffs to inspect.
- Separate immediate containment from full remediation.
- Keep the investigation scoped to evidence, not guesswork.

**Verification steps**

1. Re-run the failed job with verbose logging or artifact capture enabled.
2. Compare the runner image, dependency versions, and container digests to the last successful run.
3. Reproduce the failing step locally or in an isolated test runner if possible.
4. Confirm the chosen mitigation does not hide the root cause.

**Outcome**

You leave the first pass with a ranked hypothesis list and a short set of checks that can actually narrow the failure.

### Workflow 2: Design and review a Kubernetes deployment

**Scenario**

A new API is moving onto Kubernetes. The deployment needs sane requests and limits, readiness and liveness probes, rollout safety, and a review for namespace, RBAC, and secret-handling mistakes before it reaches staging.

**Skill invocations**

1. `brainstorming`
2. `writing-plans`
3. `code-review`

**Prompt example**

```text
Use brainstorming first, then writing-plans and code-review for this Kubernetes deployment.

What I need: a Deployment, Service, HorizontalPodAutoscaler, PodDisruptionBudget, and Ingress for `catalog-api`.
Requirements: zero-downtime rollout, readiness and liveness probes, secret injection from the platform secret store, and resource defaults that will not starve the node pool.
Context: this service will run in staging and prod, and it should follow the patterns already used in `k8s/base/payments-api/`.
Start by proposing the deployment design and rollout strategy, not by writing manifests.
```

**Expected AI actions**

- Propose rollout options such as rolling update versus canary, with trade-offs.
- Define the manifest set, required inputs, and environment-specific overlays.
- Review for dangerous defaults such as missing probes, weak security context, or broad RBAC.
- Identify validation steps such as schema checks, rendered manifest review, and staged rollout.

**Verification steps**

1. Render the manifests with `kustomize build` or `helm template` and inspect the output.
2. Run the repo's Kubernetes validation checks and schema linting.
3. Diff the staged rollout against the current environment before apply.
4. Confirm the pod starts cleanly and passes probes in staging before promoting further.

**Outcome**

You get a reviewed deployment design that is ready for a staged rollout instead of a first draft that still hides basic operational risk.

### Workflow 3: Investigate a production alert

**Scenario**

A latency alert fires for a customer-facing service shortly after a deploy. One region is breaching the SLO, but error rate is still low. You need to decide whether this is a bad rollout, a dependency issue, or a traffic imbalance.

**Skill invocations**

1. `systematic-debugging`
2. `investigate`

**Prompt example**

```text
Use systematic-debugging and investigate for this production alert.

Alert: p95 latency for checkout-api exceeded 1.5s for 10 minutes in us-east-1.
Symptoms: requests are slow but mostly successful.
Recent context: deploy `checkout-api:2025.03.14.3` completed 12 minutes before the alert.
Infra: service runs on Kubernetes, traces are in Tempo, logs are in Loki, and service metrics are in Prometheus.

I need:
1. The top three hypotheses ranked by probability
2. The first queries or dashboards to inspect for each
3. What evidence would confirm a rollback versus continued observation
4. Any safe mitigation steps while investigation is ongoing
```

**Expected AI actions**

- Rank the likely causes and tie them to the timing of the deploy.
- Point to concrete logs, metrics, and traces to inspect first.
- Distinguish rollback triggers from signals that justify continued observation.
- Suggest low-risk mitigations such as scale adjustments or traffic shifting only when justified.

**Verification steps**

1. Run the suggested queries and compare the observed signals to the predicted ones.
2. Check whether the symptoms are isolated to one region, one replica set, or one dependency.
3. Compare latency by version, node pool, and upstream dependency.
4. Verify that any mitigation improves the alert without creating a broader issue.

**Outcome**

You end up with a sharper incident hypothesis and a smaller set of high-value checks instead of a broad, noisy search.

### Workflow 4: Plan and execute a database migration

**Scenario**

A service needs a schema change that cannot break live traffic. The migration includes a new nullable column, backfill work, application rollout, and a cleanup step after the old code path is gone. You need an execution sequence that is safe, reversible, and easy to verify.

**Skill invocations**

1. `brainstorming`
2. `writing-plans`
3. `postgresql-code-review`
4. `verification-before-completion`

**Prompt example**

```text
Use brainstorming first, then writing-plans, postgresql-code-review, and verification-before-completion for this migration.

Context: `orders_api` needs a new `fulfillment_state` column on `orders`, plus a backfill based on existing event data. The application must support both old and new schema during rollout.
Requirements:
- zero downtime
- rollback path at each phase
- explicit verification after schema change, backfill, app deploy, and cleanup
- a short execution checklist another engineer could follow

Start with the migration strategy and sequencing, not with raw SQL.
```

**Expected AI actions**

- Propose an expand-migrate-contract sequence with clear rollback points.
- Review SQL and migration steps for locking risk, default values, and backfill safety.
- Define verification checks for schema state, query performance, and application compatibility.
- Produce a short operator checklist that mirrors the full plan.

**Verification steps**

1. Test the migration in staging with production-like data volume if available.
2. Measure lock duration, query plans, and backfill throughput before production.
3. Confirm the application works with both schema versions during rollout.
4. Verify it is safe to remove the old path only after traffic and logs show the new field is fully in use.

**Outcome**

You get a migration plan that treats sequencing and rollback as first-class requirements instead of afterthoughts.

### Workflow 5: Automate a manual runbook

**Scenario**

Engineers still promote a container image from staging to production with a 14-step shell runbook. The process works, but it is slow, easy to perform out of order, and hard to audit. You want to turn it into safe automation without losing the existing checkpoints.

**Skill invocations**

1. `brainstorming`
2. `writing-plans`
3. `test-driven-development`

**Prompt example**

```text
Use brainstorming, writing-plans, and TDD to automate this runbook.

Current process: promote `payments-api` from the approved staging image to production, update the release tag, trigger the deploy workflow, watch health checks, and record the result in the release log.
Requirements:
- preserve manual approval before production deploy
- dry-run support for everything that can be simulated
- idempotent steps so reruns are safe
- clear failure handling and rollback instructions
- tests for the decision logic and command assembly

Start by turning the human runbook into an automation design with inputs, outputs, guardrails, and decision points.
```

**Expected AI actions**

- Break the manual procedure into explicit steps, inputs, and gates.
- Identify which steps should remain human approvals versus fully automated actions.
- Define failure paths, rollback behavior, and audit logging requirements.
- Produce a testing strategy for the automation logic before implementation starts.

**Verification steps**

1. Compare the planned automation to the current human runbook step by step.
2. Dry-run the workflow in a non-production environment and inspect the output.
3. Inject a simulated failure to verify rollback and alerting behavior.
4. Confirm rerunning the workflow does not duplicate state changes or skip required approvals.

**Outcome**

You end up with automation that preserves the intent of the runbook while removing the fragile, repetitive shell work.

### Workflow 6: Security audit a pull request

**Scenario**

A pull request updates a GitHub Actions workflow, a Dockerfile, and Kubernetes RBAC for a service that deploys to production. This is exactly the kind of mixed change where security mistakes can hide in plain sight.

**Skill invocations**

1. `code-review`
2. `security-review`

**Prompt example**

```text
Run code-review and security-review on this PR.

Scope:
- `.github/workflows/release.yml`
- `Dockerfile`
- `k8s/base/reporting-api/rbac.yaml`

Intent: add image signing, speed up the build, and allow the deployment controller to patch one ConfigMap.
Review for:
- over-broad workflow token permissions
- unsafe use of unpinned actions or base images
- secret exposure in logs or build args
- RBAC permissions that exceed the stated intent
- any supply-chain or container hardening issues
```

**Expected AI actions**

- Review the diff for credential handling, least privilege, and supply-chain risk.
- Flag unpinned actions, overly broad workflow permissions, and insecure container defaults.
- Compare the requested RBAC scope to the stated intent.
- Distinguish blockers from lower-severity follow-up items.

**Verification steps**

1. Inspect each flagged permission or secret-handling issue directly in the diff.
2. Confirm actions and base images are pinned to trusted versions or digests.
3. Verify the RBAC change grants only the verbs and resources the controller actually needs.
4. Re-check the workflow with the final changes to ensure no new exposure was introduced.

**Outcome**

You leave review with a shorter, higher-confidence list of security issues that are worth fixing before merge.

---

[< Multi-model workflows](multi-model.md) | [Trust and safety >](safety.md)
