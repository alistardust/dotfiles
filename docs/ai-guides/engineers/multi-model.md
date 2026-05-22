# Multi-model workflows

### Why use multiple models

Different models have different strengths and blind spots. Claude tends to be more careful, thorough, and conservative. GPT tends to be faster, more creative, and sometimes more willing to take shortcuts. Using both catches things either alone would miss. This is not about one being better. It is about coverage.

A practical rule is simple: use one model to draft and another to challenge the draft. If both agree, confidence goes up. If they disagree, that disagreement is usually the most valuable part of the exercise.

### Setting your preferred model

```bash
# Copilot CLI
copilot config set model claude-sonnet-4-5

# Claude Code
claude config set model claude-sonnet-4-5

# Codex
codex --model gpt-5.4
```

In practice, Claude Code always stays in the Claude family and Codex stays in the GPT family. The exact command matters less than being deliberate about which model is doing which job.

### The draft and review pattern

Use one model to write code or a plan, then switch to a different model to review it. The reviewing model catches assumptions the drafting model baked in. This works especially well for security-sensitive changes, complex logic, and infrastructure modifications where hidden assumptions are expensive.

A good review prompt says what to ignore as well as what to look for. Ask for bugs, security issues, failure modes, and missing rollback steps. Tell the reviewer not to waste time on naming or formatting.

### The dual review pattern

After writing code, have both Claude and GPT review it independently, then compare their feedback. Disagreements between models are almost always worth investigating because they reveal edge cases or assumptions that need explicit handling.

Use dual review when the cost of being wrong is high: IAM policy changes, Terraform in shared environments, certificate rotation, deployment automation, or anything that can cause downtime. You are not trying to get a vote. You are trying to find the hidden edge case before production does.

### General model strengths

| Scenario | Recommended | Why |
|----------|-------------|-----|
| Complex reasoning, careful analysis | Claude (Opus or Sonnet) | More thorough, catches edge cases |
| Quick generation, rapid iteration | GPT (5.4 or mini) | Faster, good for first drafts |
| Security review | Both | Different threat models, different catches |
| Refactoring large files | Claude | Better at maintaining context across changes |
| Brainstorming alternatives | GPT | More willing to suggest unconventional approaches |

These are tendencies, not laws. If one model keeps missing an issue in your environment, change the pattern. The workflow matters more than brand loyalty.

### Practical example: catching a race condition

1. **Draft with Claude**

   Prompt:

   ```text
   I am writing a Terraform module for an ECS service behind an ALB.
   Please draft the service and target group resources for the payments-api service.
   Constraints: Fargate, desired_count = 3, /health endpoint, rolling deploys, and keep the example production-safe.
   The container takes about 70 to 90 seconds to warm up before /health returns 200.
   ```

   Abbreviated response:

   - Creates `aws_lb_target_group` with `/health` checks every 15 seconds
   - Creates `aws_ecs_service` with `health_check_grace_period_seconds = 30`
   - Uses sane defaults for deployment percentages and log configuration

2. **Review with GPT**

   Prompt:

   ```text
   Review this Terraform for bugs and operational risk only. Ignore style.
   Focus on ECS service readiness, ALB health checks, and deployment failure modes.

   [PASTE THE CLAUDE DRAFT HERE]
   ```

   Abbreviated response:

   - `health_check_grace_period_seconds = 30` is shorter than the 70 to 90 second startup time
   - ECS may replace tasks before the ALB ever marks them healthy
   - Recommend increasing the grace period and aligning target group thresholds with real startup behavior

3. **Tighten the implementation**

   Follow-up prompt back to Claude or Copilot:

   ```text
   Update the module based on this review. Set a safer ECS health check grace period for a 90 second startup window and explain the tradeoff.
   ```

   Abbreviated response:

   - Raises grace period to 120 seconds
   - Notes that slower failure detection is acceptable here because premature replacement is worse
   - Suggests validating with one deploy in staging before promoting

That is a useful multi-model workflow in miniature. Claude produced a strong first draft. GPT caught the operational race. The fix was small, but the failure mode would have been ugly in production.

---

[< Writing your own skills](writing-skills.md) | [Real-world workflows >](workflows.md)
