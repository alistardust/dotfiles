# Writing effective prompts

The golden rule: context is everything. The AI can only work with what you give it. A vague prompt gets a vague answer.

A useful prompt usually follows a simple formula:

`[Role/Context] + [Task] + [Constraints] + [Output format]`

You do not need to write it that formally every time. The point is to make sure those four elements are present. If the AI knows what system it is working in, what you want done, what boundaries matter, and how you want the result returned, the output gets better fast.

### Pattern library

#### 1. Be specific about scope

| Bad | Good |
|-----|------|
| ```text
Fix the bug in the deploy script.
``` | ```text
The `deploy.sh` script in `scripts/` fails with exit code 1 when the ECS service name contains a hyphen. The variable interpolation on line 47 is unquoted. Fix the quoting so service names with hyphens work correctly.
``` |

Why the good version works: it names the file, the symptom, the likely cause, and the desired fix. That keeps the AI from wandering into unrelated parts of the deployment flow.

#### 2. Provide context upfront

| Bad | Good |
|-----|------|
| ```text
Write a Terraform module for an S3 bucket.
``` | ```text
I am working on a Terraform module in `modules/s3-data-lake/`. It provisions S3 buckets for a data lake in us-east-1. The module needs to support: versioning enabled, lifecycle rules for glacier transition after 90 days, server-side encryption with a KMS key passed as a variable, and a bucket policy that restricts access to a specific VPC endpoint. Use an existing pattern from `modules/s3-logs/` as a reference.
``` |

Why the good version works: it anchors the request in a real module, adds requirements, and points to an existing pattern. That makes the result look like your codebase instead of a generic blog example.

#### 3. Ask for explanations

| Bad | Good |
|-----|------|
| ```text
Add retry logic to the API call.
``` | ```text
Add retry logic to the `fetch_metrics()` function in `src/adapters/cloudwatch.py`. Use exponential backoff with jitter. Explain each change you make and why you chose those specific retry parameters.
``` |

Why the good version works: it asks for both implementation and reasoning. That is useful when you need to review the change, teach a teammate, or sanity-check the retry behavior before rollout.

#### 4. Constrain the output

| Bad | Good |
|-----|------|
| ```text
Review this Terraform.
``` | ```text
Review `modules/rds/main.tf` for security issues only. Do not comment on naming, formatting, or style. Focus on: unencrypted storage, public accessibility, overly permissive security groups, and missing deletion protection.
``` |

Why the good version works: it narrows the review to the risks that matter. This cuts noise and makes the output easier to act on.

#### 5. Iterative refinement

A strong workflow is usually a conversation, not a one-shot prompt.

```text
Turn 1
Show me approaches to implement blue-green deploys for a Kubernetes API using GitHub Actions and Helm.

Turn 2
Option 2 looks right. But we need to handle the case where new pods fail readiness checks during rollout. Add an automatic rollback-and-alert mechanism.

Turn 3
Good. Now send the alert to Slack instead of email, and add a summary step at the end that reports which deployment stages succeeded and which failed.
```

Why this works: each turn adds one more real-world constraint. Instead of trying to write the perfect prompt at the start, you let the design tighten as you learn what matters.

#### 6. Use the AI as a reviewer

| Bad | Good |
|-----|------|
| ```text
Is this code good?
``` | ```text
Review this diff for bugs, security issues, and missed edge cases. Only flag things that genuinely matter; do not comment on style or formatting. If you find nothing significant, say so.
``` |

Why the good version works: it turns a vague opinion question into a focused review request with a clear signal threshold.

### Anti-patterns

#### 1. Fix everything

This is too broad. The AI will touch unrelated code and introduce regressions. Scope the request to specific files, functions, or failure modes.

#### 2. Is this code good?

This is subjective and does not tell the AI what to optimize for. Ask for specific concerns such as security, correctness, performance, readability, or operational risk.

#### 3. Write me a complete X without context

This usually produces generic output disconnected from your actual repo. Always provide architecture context, constraints, environment details, and an example of an existing pattern when one exists.

#### 4. Pasting 500 lines with what's wrong?

That gives the AI too much noise and not enough direction. Narrow to the suspected area, describe the symptom, and let the AI investigate outward if needed.

### DevOps prompt templates

These are general working templates. Copy them, fill in the blanks, and adjust the environment details before use.

#### Monitoring alert investigation template

```text
A production alert just fired.

Alert: [ALERT NAME OR PAYLOAD]
Service or component: [NAME]
Symptoms: [what is broken from the user's perspective]
Timeline: [when it started, any recent changes]

Help me investigate:
1. What are the three most likely root causes, ranked by probability?
2. What dashboards, logs, or queries should I check first to confirm or eliminate each?
3. Are there any low-risk mitigations I should consider while I investigate?

Context: The service runs on [platform]. Logs are in [location]. Metrics are in [system]. Recent deploy status: [details].
```

When to use: the first 5 minutes of an alert, before you have formed a strong hypothesis.

What to look for in the response: specific dashboards, logs, or commands with expected signals, not generic advice.

#### Infrastructure as code review template

```text
Review this infrastructure change for unintended risk. Focus on:
- replacements or rollout patterns that could cause downtime
- security changes that widen access
- configuration drift or defaults that do not match the intent
- changes to resources I did not explicitly plan to modify

Change set:
[PASTE TERRAFORM PLAN, KUBERNETES DIFF, OR MANIFEST CHANGE]

My intent was only to: [DESCRIBE YOUR INTENDED CHANGE]
Target environment: [prod/staging/dev]
```

When to use: after generating a plan, diff, or rendered manifest, before you apply the change.

#### CI/CD and Docker debugging template

```text
This CI/CD job is failing. Help me debug it.

Pipeline or workflow: [NAME]
Failed job or step: [STEP NAME]
Error message: [PASTE ERROR]
Runner or build environment: [RUNNER IMAGE / OS / EXECUTOR]
Container or artifact details: [DOCKERFILE, IMAGE TAG, OR BUILD CONTEXT]
The pipeline worked previously. The recent change was: [DESCRIBE CHANGE]

What is the most likely cause, what should I check first, and what is the safest fix path?
```

When to use: when a pipeline or image build fails and the error message is not immediately clear.

---

[< The instruction system](instructions.md) | [Skills >](skills.md)
