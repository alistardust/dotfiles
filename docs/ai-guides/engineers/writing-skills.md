# Writing your own skills (advanced)

This chapter is aimed at team leads and senior engineers who want to codify workflows for their teams. You should be comfortable using existing skills in Chapter 5 before attempting to author your own.

### When to write a skill

Write a skill when:

1. You find yourself giving the AI the same instructions repeatedly across sessions.
2. A workflow has specific steps that must not be skipped, such as pre-deploy checks or incident response procedures.
3. You want to enforce a process consistently across a team, not just remember it yourself.

If the process is still changing every week, do not write a skill yet. Wait until the shape is stable enough that encoding it will save time instead of creating maintenance work.

### Anatomy of a SKILL.md file

A skill is just a directory with a `SKILL.md` file inside it. The file is plain markdown, but the structure matters because the AI reads it as process, not prose.

- **Frontmatter**
  - This is the short metadata block at the top. It gives the skill a name and a one-line description so the AI knows when to use it.
  - Keep the name short and action-oriented. The description should say what job the skill performs, not how it is implemented.
- **Instructions**
  - This is the main body. It tells the AI what role to play, what outcome to produce, and what assumptions to make.
  - Write this like an operator runbook: direct, concrete, and specific about what good behavior looks like.
- **Process steps**
  - Use numbered steps for workflows that have an order. This gives the AI a path to follow instead of a bag of ideas to sample from.
  - Each step should be observable. `Check deployment history` is better than `understand the situation`.
- **Hard gates**
  - Use explicit `HARD-GATE` markers for things the AI must not skip. These are the safety rails.
  - A hard gate should stop forward motion until a condition is satisfied. Example: do not proceed until rollback steps are confirmed.
- **Examples**
  - Show what good and bad behavior looks like. Examples train the model on the shape of a useful answer.
  - Include at least one invocation example and one example of the expected output format.

A good skill reads like a small operational standard. It is opinionated, testable, and easy to recognize in output.

### Worked example: deployment-checklist skill

```markdown
---
name: deployment-checklist
description: "Run the required pre-deploy checks for a service deployment and stop if safety gates are not met."
---

# Deployment checklist

Use this skill before any service deployment. Your job is to verify that the release is ready, call out missing evidence, and stop the workflow if any hard gate is unmet.

## Process

1. Identify the service name, target environment, deployment method, and change window.
2. Verify the relevant tests passed. Prefer CI evidence over claims in chat.
3. Check that the diff or release artifact has been reviewed by a human.
4. Confirm the exact target environment. Do not assume staging versus production.
5. Verify that a rollback plan exists and is specific to this deployment.
6. Confirm monitoring is in place: dashboards, alerts, logs, and a post-deploy signal to watch.
7. Summarize readiness as PASS, BLOCKED, or NEEDS INFO.

<HARD-GATE>
Do NOT proceed to deploy without explicit confirmation of the rollback plan.
If the rollback is vague, missing, or depends on guessing, return BLOCKED.
</HARD-GATE>

<HARD-GATE>
Do NOT mark the deployment ready if tests have not passed or if the target environment is ambiguous.
</HARD-GATE>

## Output format

- Service
- Target environment
- Test status
- Review status
- Rollback status
- Monitoring status
- Final readiness: PASS, BLOCKED, or NEEDS INFO
- Missing items

## Example invocation

User: "Use deployment-checklist for the billing-api release to staging."

## Example output

- Service: billing-api
- Target environment: staging
- Test status: PASS - GitHub Actions run 18452 succeeded
- Review status: PASS - PR #482 approved by one reviewer
- Rollback status: BLOCKED - no rollback steps documented
- Monitoring status: PASS - Grafana dashboard and PagerDuty alert linked
- Final readiness: BLOCKED
- Missing items: document rollback steps before deployment
```

The example is intentionally strict. A skill should not be afraid to block work when required evidence is missing. That is the whole point.

### Design principles

1. **Be opinionated**: A skill encodes a specific process. It should make decisions, not present menus. "Always run tests before declaring done" is better than "Consider running tests."
2. **Include hard gates**: Mark steps the AI must not skip with explicit `HARD-GATE` blocks. These are your safety nets for automated workflows.
3. **Provide examples**: Show the AI what good output looks like. A skill with examples produces dramatically better results than one without.
4. **Keep focused**: One skill per workflow. A deployment skill and a debugging skill, not a deployment-and-debugging skill. Small, composable skills are easier to maintain and combine.

### Installing and sharing skills

Install custom skills by putting them under `~/.copilot/skills/`. The simplest team pattern is to keep them in a git repo and have each engineer clone that repo into their local skills directory.

```bash
# Share a custom skill with your team
cd ~/.copilot/skills/
mkdir team-platform-skills
cd team-platform-skills
# Create your skill
mkdir deployment-checklist
# Write SKILL.md...
git init && git add . && git commit -m "feat: add deployment-checklist skill"
git remote add origin git@github.com:your-org/platform-copilot-skills.git
git push -u origin main

# Teammates install it
git clone git@github.com:your-org/platform-copilot-skills.git ~/.copilot/skills/team-platform-skills
```

Treat team skills like code. Review changes, keep them small, and update them when the underlying runbook changes. If a skill drifts away from the real workflow, people will stop trusting it.

---

[< Skills](skills.md) | [Multi-model workflows >](multi-model.md)
