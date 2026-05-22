# Skills: the force multiplier

### Introduction

Skills are packaged instruction sets that teach the AI specialized workflows. When you invoke a skill, the AI loads a structured process and follows it step by step: asking the right questions, enforcing gates, and producing consistent output.

Install them by cloning the skill repositories into your local skills directory:

```bash
# Superpowers (process skills: brainstorming, planning, TDD, debugging, etc.)
git clone git@github.com:DwainTR/superpowers-copilot.git ~/.copilot/skills/superpowers

# gstack (browser automation, QA, design review, deploy verification)
git clone git@github.com:ridermw/gstack.git ~/.copilot/skills/gstack
```

To invoke a skill, mention it in conversation. Examples: `use the brainstorming skill`, `invoke systematic-debugging`, or `/code-review`. The AI will load the skill instructions and follow the process.

On disk, skills live under `~/.copilot/skills/`. Each skill is a folder with a `SKILL.md` file.

### 1. brainstorming

**What it does**

This skill explores requirements and design before any code is written. It slows the process down in a good way by forcing clarity on scope, tradeoffs, and success criteria before implementation starts.

**When to use it**

- Starting a new feature or automation flow
- Requirements are unclear or still moving
- Multiple valid approaches exist
- Scope is ambiguous and needs to be narrowed

**Worked example**

User prompt:

```text
I need to add certificate rotation to a fleet of services. Use the brainstorming skill to help me think through the design.
```

What the skill does:

- Explores the current repo and existing cert-handling patterns
- Asks clarifying questions one at a time
- Proposes multiple implementation approaches with tradeoffs
- Presents a recommended design for approval
- Writes the approved design into a spec document

Outcome: you get an agreed design before anyone starts changing Vault roles, playbooks, or service restart behavior.

### 2. systematic-debugging

**What it does**

This skill follows a four-phase root cause process: investigate, analyze, hypothesize, implement. Its main value is discipline: it stops the AI from guessing at fixes before the failure has been understood.

**When to use it**

- A bug is reproducible but the cause is unclear
- You have already tried a few guesses and none held up
- Multiple components might be involved
- The failure is intermittent and needs structured narrowing

**Worked example**

User prompt:

```text
The nightly backup job has been failing intermittently for a week. Use systematic-debugging to find the root cause.
```

What the skill does:

- Gathers logs, config, recent changes, and timing data
- Separates observed facts from assumptions
- Builds and tests explicit hypotheses
- Identifies the root cause before suggesting a fix

Outcome: you get a defensible explanation for the failure instead of another round of trial-and-error patches.

### 3. writing-plans and executing-plans

**What it does**

These two skills work as a pair. `writing-plans` turns an approved design into a sequence of small, reviewable tasks, and `executing-plans` carries that plan out with checkpoints and verification.

**When to use it**

- The change spans multiple files or systems
- Work will likely continue across multiple sessions
- You need mid-flight checkpoints and reviewability
- The implementation has dependencies that should be ordered explicitly

**Worked example**

User prompt:

```text
We have the cert rotation design approved. Use writing-plans to create the implementation plan.
```

What the skill does:

- Breaks the design into atomic tasks
- Captures dependencies and validation steps
- Defines checkpoints for review
- Hands the plan to `executing-plans` when it is time to build

Outcome: the work stops being a blob of AI activity and becomes a traceable plan you can inspect, pause, and resume.

### 7. gstack

**What it does**

`gstack` is a family of browser-driven skills for QA, design review, and deployment verification. It can navigate pages, interact with elements, capture screenshots, and produce evidence instead of relying on text descriptions of what a page supposedly does.

**When to use it**

- Verifying a web deployment after release
- Testing a UI change or a login flow
- Checking that a Grafana dashboard renders correctly
- Filing a bug with screenshots and reproduction evidence

**Worked example**

User prompt:

```text
Use gstack QA to test the status page at https://status.example.com. Verify all services show green and the page loads in under 3 seconds.
```

What the skill does:

- Opens the page in a headless browser
- Measures load behavior and captures visual state
- Checks the service indicators and any obvious errors
- Produces a QA summary with evidence

Outcome: you get a real verification pass on the page, not just a claim that the endpoint returned 200.


### More skills

The reference appendix contains the full skills catalog with additional worked examples:
test-driven-development, code-review, verification-before-completion, and investigate.
See `ai-workflow-guide-reference-engineers.md` for the complete list.

### Quick-reference table

| Skill | What it does | When to use | Invoke with |
|-------|--------------|-------------|-------------|
| conventional-commit | Builds a conventional commit message in a structured format. | When you are ready to commit and want a clean, standard message. | `use conventional-commit` |
| devops-rollout-plan | Produces a deployment or rollout plan with checks, rollback, and validation. | When a change needs a step-by-step release plan. | `use devops-rollout-plan` |
| dispatching-parallel-agents | Splits independent work across multiple sub-agents. | When you have several unrelated tasks that can run in parallel. | `use dispatching-parallel-agents` |
| finishing-a-development-branch | Helps decide how to wrap up completed branch work. | When implementation is done and you need merge, PR, or cleanup guidance. | `use finishing-a-development-branch` |
| incident-response | Guides a safe, structured incident workflow. | When you are actively handling an operational incident. | `use incident-response` |
| operational-knowledge-capture | Records useful operational learnings and patterns. | When a task reveals procedures, gotchas, or repeatable knowledge worth saving. | `use operational-knowledge-capture` |
| pre-commit-workflow | Walks through checks to run before committing. | When you want a repeatable pre-commit gate for code quality. | `use pre-commit-workflow` |
| pytest-coverage | Expands or analyzes Python test coverage. | When you need better pytest coverage or want gaps identified. | `use pytest-coverage` |
| receiving-code-review | Helps process and respond to review feedback. | When you got PR comments and want a structured response workflow. | `use receiving-code-review` |
| requesting-code-review | Prepares work for review and requests a focused review pass. | When you want the AI or a teammate to review a completed change. | `use requesting-code-review` |
| ruff-recursive-fix | Applies `ruff` fixes across Python files recursively. | When a Python repo needs broad lint cleanup with `ruff`. | `use ruff-recursive-fix` |
| security-review | Reviews changes for security weaknesses and risky patterns. | When the task touches auth, secrets, network exposure, or trust boundaries. | `use security-review` |
| subagent-driven-development | Orchestrates implementation through specialized sub-agents. | When a complex task benefits from managed delegation. | `use subagent-driven-development` |
| update-copilot-instructions | Drafts and reviews changes to Copilot instruction files. | When you want to improve the AI's persistent instruction set. | `use update-copilot-instructions` |
| using-git-worktrees | Sets up and manages git worktrees for isolated branch work. | When you want parallel branches without switching the main clone. | `use using-git-worktrees` |
| gstack-canary | Watches a live deployment for failures after release. | When you want post-deploy monitoring and screenshots. | `use canary` |
| gstack-cso | Runs a security-audit style review across code and systems. | When you want a deeper security and threat-modeling pass. | `use cso` |
| gstack-design-consultation | Creates or refines a design system and visual direction. | When a product or UI needs a coherent design system. | `use design-consultation` |
| gstack-benchmark | Benchmarks performance and compares before-and-after page behavior. | When page speed, load time, or web vitals matter. | `use benchmark` |
| gstack-retro | Produces an engineering retrospective from recent work patterns. | When you want a weekly or sprint-level retrospective. | `use retro` |

For the full catalog of all installed skills with detailed descriptions, see the reference appendix.

---

[< Writing effective prompts](prompts.md) | [Writing your own skills >](writing-skills.md)
