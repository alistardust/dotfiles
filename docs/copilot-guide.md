# GitHub Copilot CLI: A Practical Field Guide

This guide covers everything you need to go from zero to productive with
GitHub Copilot CLI -- from installation through advanced workflow techniques.
The goal is not just to get the tool running, but to help you use it in a way
that genuinely speeds up your work and improves the quality of what you ship.

---

## Table of Contents

1. [Installation on WSL](#installation-on-wsl)
2. [First Launch and Authentication](#first-launch-and-authentication)
3. [How the CLI Works](#how-the-cli-works)
4. [Choosing and Switching Models](#choosing-and-switching-models)
5. [Writing Your Copilot Instructions](#writing-your-copilot-instructions)
6. [Skills: Installing, Using, and Writing](#skills-installing-using-and-writing)
7. [Installing and Using gstack](#installing-and-using-gstack)
8. [Using Copilot in VSCode](#using-copilot-in-vscode)
9. [Writing Effective Prompts](#writing-effective-prompts)
10. [Using Multiple Models Strategically](#using-multiple-models-strategically)
11. [Practical Workflow Examples](#practical-workflow-examples)

---

## Installation on WSL

Copilot CLI runs natively inside WSL2 on Ubuntu. The install is a single
command, but there are a few things to have in place first.

### Prerequisites

- **WSL2 with Ubuntu 24.04** (not WSL1 -- check with `wsl -l -v` in PowerShell)
- **An active GitHub Copilot subscription** -- individual, team, or enterprise
- **curl** -- present by default in Ubuntu

If you are using this dotfiles repo, the `copilot` section of `setup.sh` handles
everything below automatically. To run it:

```bash
./setup.sh --only copilot
```

### Manual Installation

If you prefer to install by hand, run this inside your WSL terminal:

```bash
curl -fsSL https://gh.io/copilot-install | bash
```

This installs the `copilot` binary to `~/.local/bin`. Make sure that directory
is on your `PATH` -- add this to `~/.zshrc` if it is not already there:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then reload your shell:

```bash
source ~/.zshrc
```

---

## First Launch and Authentication

Launch the CLI from inside a project directory:

```bash
cd ~/your-project
copilot
```

On first launch you will see the animated welcome screen. If you are not
authenticated, run:

```
/login
```

Follow the browser prompts to authenticate with your GitHub account. Your
session persists across launches so you will not need to log in again.

### Authenticating With a Personal Access Token

If you prefer token-based authentication (useful in headless or CI environments):

1. Go to <https://github.com/settings/personal-access-tokens/new>
2. Under **Permissions**, add the **Copilot Requests** permission
3. Generate the token and copy it
4. Export it in your shell before launching:

```bash
export GH_TOKEN="your-token-here"
```

---

## How the CLI Works

The CLI is a conversational coding agent -- not a simple autocomplete tool.
You describe what you want in plain language, and the agent plans and executes
multi-step tasks: editing files, running commands, reading your codebase, and
checking its own output.

### Interaction Modes

Press `Shift+Tab` to cycle between modes:

| Mode | Behaviour |
|------|-----------|
| **Normal** | Confirm each action before it runs |
| **Autopilot** | Agent works continuously until the task is complete |

Start in Normal mode while you are building familiarity. Autopilot is useful
for well-scoped, lower-risk tasks once you trust the agent's judgment on your
codebase.

### Key Slash Commands

| Command | What It Does |
|---------|--------------|
| `/model` | Choose which AI model to use |
| `/instructions` | View and toggle your instruction files |
| `/skills` | Manage installed skills |
| `/diff` | Review changes made in the current directory |
| `/review` | Run the code review agent on your changes |
| `/plan` | Create an implementation plan before coding |
| `/compact` | Summarise conversation history to reclaim context |
| `/context` | Show context window usage |
| `/share` | Export the session to a Markdown or HTML file |
| `/help` | Full command reference |

### Referencing Files, Issues, and Pull Requests

- Type `@filename` to bring a specific file into context
- Type `#123` to reference a GitHub issue or pull request by number
- Type `!command` to run a shell command inline

---

## Choosing and Switching Models

Copilot CLI defaults to **Claude Sonnet**. You can change the model at any time
with `/model`.

### Setting Claude as Your Preferred Model

The `copilot` section of the dotfiles bootstrap writes a `~/.copilot/settings.json`
with the Claude preference already set. If you installed manually, create or edit
that file:

```json
{
  "model": "claude-sonnet-4.5"
}
```

This preference is applied at startup. You can still switch models mid-session
with `/model` without changing the file.

### Available Models

Run `/model` inside a session to see the current list. As of writing, the main
options are:

- **Claude Sonnet** -- best default choice: fast, capable, strong at reasoning
  and code
- **Claude Opus** -- higher quality for complex multi-step problems; slower and
  uses more quota
- **GPT-5** -- a useful second opinion; particularly good for tasks where you
  want a different perspective on a problem

The quota note: each prompt uses one premium request from your monthly allocation.
There is no free tier for requests -- heavier models cost the same request unit
but produce higher quality output for complex tasks.

---

## Writing Your Copilot Instructions

Instructions are the most powerful lever you have. Well-written instructions
mean every session starts with the agent already knowing your conventions, your
expectations, and your constraints. Poorly written instructions (or none at all)
mean you are repeating yourself constantly.

Copilot loads instructions from multiple locations, in order:

1. `$HOME/.copilot/copilot-instructions.md` -- global, applies to all sessions
2. `.github/copilot-instructions.md` -- per-repo, applies when you work in that
   repo
3. `.github/instructions/**/*.instructions.md` -- additional per-repo instruction
   files (can be scoped to file patterns)
4. `AGENTS.md` in the repo root -- also read by other agents (Codex, etc.)

### Global Instructions

Global instructions go in `~/.copilot/copilot-instructions.md`. This is where
you put things that are true for all your work:

- Your name and pronouns (the agent will address you correctly)
- Your model preference
- Universal coding standards: naming conventions, error handling, logging,
  security rules
- Your review and approval workflow
- Anything you find yourself repeating in every session

The dotfiles repo ships a complete, production-grade example of this file under
the `copilot` section -- run `./setup.sh --only copilot` to bootstrap it, then
edit it to reflect your own preferences. The bootstrapped file covers naming,
error handling, logging, security, architecture, testing, Git hygiene, Python,
and JavaScript standards.

Here is a minimal but effective global instructions file to start from:

```markdown
# Global Copilot Instructions

## Identity

My name is Alex. Use he/him pronouns.

## Model Preference

Prefer Claude Sonnet for standard tasks. Use Claude Opus for complex
multi-step reasoning or security-sensitive changes.

## Quality Rules

- Prioritise accuracy over speed.
- Never guess. Only provide answers you can verify.
- Fail fast and loudly -- a crash immediately is better than silent
  data corruption later.
- Never swallow exceptions silently (no bare `except: pass` or empty `catch {}`).

## Naming Conventions

- Variables and functions describe what the thing IS, not where it came from.
- Booleans use question form: `is_active`, `has_permission`, `can_retry`.
- No magic numbers -- name the constant (`MAX_RETRIES = 3`, not `3`).

## Security -- Absolute Blockers

- No `eval()` or `exec()` with any external input.
- No SQL built by string formatting -- always use parameterised queries.
- No hardcoded credentials anywhere in source code.
- No `random` for security purposes -- use `secrets` (Python) or
  `crypto.randomBytes` (Node).

## Git

- Conventional Commits: `<type>[scope]: <description>`
- Atomic commits -- one logical change per commit.
- Branch naming: `feature/ID-description` or `fix/ID-description`.

## Explicit Approval

Ask before acting on anything that modifies state, opens a PR, or runs a
destructive command. Wait for an unambiguous confirmation before proceeding.
```

**Key principle:** Put hard constraints first. Use bullets, not prose. Always
state *why* a rule exists -- this helps the agent make good decisions in edge
cases that your instructions do not explicitly cover.

### Per-Repo Instructions

Per-repo instructions go in `.github/copilot-instructions.md` inside each
repository. This is where you capture things that are specific to that project:

- The tech stack and language versions in use
- Framework-specific conventions (which router, which ORM, etc.)
- Local test commands (`make test`, `pytest -x`, etc.)
- Deployment context (staging vs production, environment variable names)
- Things the agent should never touch (generated files, vendor directories)
- Branch naming and PR conventions for that specific team

**Tip:** Run `/init` inside a project and the agent will read your codebase and
propose a starter `copilot-instructions.md` for you. Review it carefully and
edit before committing.

Here is an example for a Python web service:

````markdown
# Project: Payments Service

## Stack

- Python 3.12, FastAPI 0.115, SQLAlchemy 2.0 (async), PostgreSQL 16
- Tests: pytest, pytest-asyncio, httpx (async test client)
- Dependency management: uv

## Running Tests

```bash
uv run pytest -x --tb=short
```

## Conventions

- All database access goes through `src/repository/` -- never in route handlers.
- All business logic goes in `src/services/` -- no DB calls there.
- Config is loaded from environment variables via `src/config.py` using pydantic-settings.
- Never import from `src/api/` into `src/services/` -- that direction is forbidden.

## Do Not Touch

- `src/generated/` -- auto-generated from the OpenAPI spec, do not edit by hand.
- `migrations/` -- always generate Alembic migrations, never write them manually.

## Deployment

- Staging: `APP_ENV=staging`
- Production: `APP_ENV=production`
- Secrets come from AWS Secrets Manager, not environment variables in production.
````

### Path-Specific Instructions

For larger repos you can scope instructions to specific file patterns using
`.github/instructions/` files with an `applyTo` frontmatter field. These are
picked up automatically by Copilot CLI and the VSCode Copilot extension when
you are working in matching files.

```markdown
---
applyTo: "**/*.test.ts"
---

# Test File Conventions

- Use `describe` / `it` blocks (not `test()`).
- Mock HTTP calls with `msw` -- never use `jest.spyOn` on `fetch`.
- Each test file has a single top-level `describe` matching the module under test.
- Use `userEvent` from `@testing-library/user-event` for all interactions,
  not `fireEvent`.
```

```markdown
---
applyTo: "src/api/**/*.ts"
---

# API Route Conventions

- All routes validate input with a Zod schema before touching the database.
- Return `ApiResponse<T>` -- never return raw objects from route handlers.
- Log at INFO on entry and exit of every route using the request correlation ID.
```

### What to Include and What to Leave Out

**Include:**
- Constraints that, if violated, would require you to undo the work
- Conventions that are not obvious from the code itself
- Context the agent cannot infer (deployment targets, external API versions,
  team agreements)

**Do not include:**
- Secrets, credentials, API keys, or internal hostnames
- PII -- real names, emails, or anything identifying real users
- Content that changes frequently (keep instructions stable; use context for
  session-specific needs)
- Generic advice the agent already follows well without being told

### Viewing Active Instructions

At any time, run:

```
/instructions
```

This shows all instruction files currently loaded and lets you toggle individual
files on or off for the session.

---

## Skills: Installing, Using, and Writing

Skills are specialised instruction sets that the agent loads on demand to handle
specific types of tasks. Instead of writing one massive instruction file that
covers everything, skills let you load the right guidance for the right task.

Think of a skill as a playbook for a specific situation. When the agent invokes
a skill, it loads the playbook and follows it -- so the skill determines not just
what gets done, but how rigorously and in what order.

### How Skills Work Technically

Skills live in `~/.copilot/skills/`. Each skill is a directory containing a
`SKILL.md` file:

```
~/.copilot/skills/
  brainstorming/
    SKILL.md
  test-driven-development/
    SKILL.md
  systematic-debugging/
    SKILL.md
  gstack/
    SKILL.md
  ...
```

At session start, Copilot reads the `name` and `description` fields from every
skill's YAML frontmatter. When you ask for something, the agent decides which
skills are relevant and loads the full `SKILL.md` content for those skills only.
This keeps the context window efficient -- skills that are not relevant to your
current task cost nothing.

### Installing the Superpowers Collection

The [Superpowers](https://github.com/obra/superpowers) collection (via the
[DwainTR community fork for Copilot](https://github.com/DwainTR/superpowers-copilot))
includes skills for:

- **Test-Driven Development** -- enforces the red-green-refactor cycle
- **Brainstorming** -- structured exploration of requirements before coding
- **Writing plans** -- structured planning before implementation
- **Executing plans** -- methodical plan execution with review checkpoints
- **Systematic debugging** -- root-cause-first debugging discipline
- **Code review** -- structured review with signal vs noise filtering
- **Subagent-driven development** -- running parallel agents for independent tasks

The `copilot` section of the dotfiles bootstrap installs everything:

```bash
./setup.sh --only copilot
```

Skills are installed to `~/.copilot/skills/`.

### Managing Skills

Inside a Copilot session:

```
/skills
```

This opens the skills manager where you can browse, enable, and disable skills.

To see what is installed from your shell:

```bash
ls ~/.copilot/skills/
```

### Using a Skill

The agent will invoke relevant skills automatically. You can also trigger one
explicitly by naming it in your prompt:

```
Use the brainstorming skill to help me design the caching layer for this service.
```

```
I want to fix this bug using systematic-debugging.
```

```
Use test-driven-development. I need to add input validation to the sign-up endpoint.
```

```
Run the code-review skill on the changes in @src/auth/handler.py.
```

When a skill is active you will see its name in the session status line. The
agent is now following that skill's structured process rather than improvising.

### Key Skills and When to Use Them

| Skill | When to Invoke It |
|-------|------------------|
| `brainstorming` | Before building any new feature -- explore requirements first |
| `writing-plans` | Before a multi-file change -- get a plan reviewed before coding |
| `executing-plans` | When you have a written plan and are ready to implement it |
| `test-driven-development` | Any time you are writing new code |
| `systematic-debugging` | When something is broken and you do not yet know why |
| `code-review` | After a significant change -- before opening a PR |
| `verification-before-completion` | Before declaring any task done |
| `finishing-a-development-branch` | When implementation is complete and you need to merge |

**Rule of thumb:** If there is a skill for what you are about to do, use it.
Skills are there because someone found the undisciplined approach produced worse
results.

### Writing Your Own Skills

You can write skills for patterns specific to your team or project -- deployment
runbooks, incident response checklists, on-call procedures, or any multi-step
process you want the agent to follow precisely.

#### Skill File Structure

A skill is a directory with a single `SKILL.md`:

```
~/.copilot/skills/my-skill-name/
  SKILL.md
```

The filename must be `SKILL.md`. The directory name is the skill's identifier.

#### SKILL.md Format

Every skill file starts with YAML frontmatter, followed by the skill content in
Markdown:

```markdown
---
name: deployment-runbook
description: Use when deploying the payments service to staging or production.
  Covers pre-deploy checks, the deploy sequence, and post-deploy verification.
---

# Deployment Runbook -- Payments Service

## Pre-Deploy Checklist

Before deploying, confirm all of the following:

- [ ] All tests pass: `uv run pytest`
- [ ] No secrets in the diff: `git log -p HEAD~1..HEAD | grep -i "password\|token\|secret"`
- [ ] Migration is backwards-compatible (if any)
- [ ] Feature flags are set correctly for the target environment

## Deploy Sequence

1. Tag the release: `git tag v$(date +%Y%m%d)-$(git rev-parse --short HEAD)`
2. Push the tag: `git push origin --tags`
3. Watch the CI pipeline -- do not proceed until it is green.
4. Deploy to staging: `./scripts/deploy.sh staging`
5. Smoke test staging: `./scripts/smoke-test.sh staging`
6. Deploy to production: `./scripts/deploy.sh production`

## Post-Deploy Verification

- Check error rate in Grafana for 10 minutes after deploy.
- Verify the health endpoint: `curl https://api.example.com/health`
- Confirm the deploy version matches: the response should include `"version": "..."`.

## Rollback

If error rate spikes above 1% or the health check fails:

```bash
./scripts/rollback.sh production
```

Then open a post-mortem ticket before investigating further.
```

#### Key Principles for Writing Good Skills

**Be specific, not generic.** Generic instructions ("follow best practices") add
no value -- the agent already follows best practices. Skills should encode
knowledge the agent cannot infer: your team's specific commands, your
architecture decisions, your non-obvious constraints.

**Keep it concise.** Every token in a skill competes with your conversation
history for context window space. Challenge every sentence: does the agent
actually need this? If it is something any competent developer would know, leave
it out.

**Put constraints before steps.** List the things that must be true before the
process begins, then the process itself. This prevents the agent from racing
ahead before preconditions are met.

**Use the description field for discovery.** The description is what the agent
reads to decide whether a skill applies. Start it with "Use when..." and include
specific situations and symptoms -- not a summary of what the skill does.

```markdown
# Good -- describes when to use it
description: Use when deploying the payments service to staging or production.

# Bad -- describes what it contains
description: Contains deployment steps, pre-deploy checks, and rollback instructions.
```

**Test your skill before relying on it.** After writing a skill, start a new
session and describe a scenario where the skill should apply. Verify the agent
picks up the skill and follows the process correctly. If it does not, the
description field probably needs to be more specific.

#### A Minimal Working Example

Here is a complete, minimal skill to use as a starting point:

```markdown
---
name: pr-checklist
description: Use before opening any pull request. Runs through a pre-PR quality
  and safety checklist to catch issues before code review.
---

# Pre-PR Checklist

Work through each item before opening the pull request. Do not skip items --
if something cannot be done, document why in the PR description.

## Quality

- Run the full test suite and confirm it passes.
- Review the diff with `/diff` -- look for debug code, commented-out blocks,
  and TODO comments without ticket numbers.
- Check that every new function has at least one test covering the happy path
  and one covering an error case.

## Safety

- No hardcoded credentials, tokens, or internal hostnames in the diff.
- No changes to generated files (if present in this repo).
- If the change touches authentication, authorisation, or data handling:
  run the security review skill before proceeding.

## PR Description

The PR description must include:
- What changed and why
- How it was tested
- Any risks or known limitations
- The ticket number this closes
```

Place this file at `~/.copilot/skills/pr-checklist/SKILL.md` and it will be
available in every session immediately.

---

## Installing and Using gstack

gstack is a virtual engineering team -- a collection of specialised review
agents that cover the full software delivery lifecycle, from CEO-style product
thinking through QA, security, and design review.

It installs to `~/.copilot/skills/gstack/` (for Copilot) and
`~/.claude/skills/gstack/` (for Claude Code).

### Installing Via the Dotfiles Bootstrap

gstack is installed automatically with the `copilot` section:

```bash
./setup.sh --only copilot
```

gstack requires [Bun](https://bun.sh). If Bun is not installed, the setup
script will install it.

### Key gstack Skills

| Skill | Purpose |
|-------|---------|
| `gstack` | Fast headless browser QA -- screenshots, form tests, user flow verification |
| `gstack-browse` | Navigate and test a live site or local server |
| `gstack-qa` | Systematically find and fix bugs, with before/after health scores |
| `gstack-review` | Code review with high signal-to-noise ratio |
| `gstack-plan-ceo-review` | Product-level plan review -- scope, ambition, strategy |
| `gstack-plan-eng-review` | Engineering plan review -- architecture, data flow, edge cases |
| `gstack-design-review` | Visual QA -- spacing, hierarchy, responsiveness |
| `gstack-ship` | End-to-end ship workflow |
| `gstack-canary` | Post-deploy monitoring against a live site |
| `gstack-cso` | Security audit -- secrets, dependencies, OWASP Top 10 |
| `gstack-retro` | Weekly engineering retrospective from commit history |

### Using gstack

Invoke a gstack skill by describing the task or referencing the skill directly:

```
Run a QA pass on the login flow at localhost:3000.
```

```
Use gstack-plan-eng-review to review this architecture plan.
```

```
Run gstack-cso for a security audit before we ship.
```

**Suggested review sequence for a significant feature:**

1. `gstack-plan-ceo-review` -- is this the right thing to build?
2. `gstack-plan-eng-review` -- is the architecture sound?
3. Write and implement the feature
4. `gstack-review` -- code review
5. `gstack-qa` -- find and fix bugs
6. `gstack-cso` -- security check
7. `gstack-ship` -- open PR and deploy

You do not need to run all of these for every change. A small bug fix may only
need `gstack-review`. A new user-facing feature warrants the full sequence.

---

## Using Copilot in VSCode

GitHub Copilot works in VSCode through two separate but complementary channels:
the **Copilot extension** (inline suggestions and chat inside the editor) and
the **Copilot CLI** (the terminal agent you have been setting up). They share
your instruction files, so configuring one benefits the other.

### Installing the Copilot Extension

Install the extension from the VSCode Marketplace:

1. Open VSCode
2. Press `Ctrl+Shift+X` to open Extensions
3. Search for **GitHub Copilot** and install it
4. Also install **GitHub Copilot Chat** (listed separately)
5. Sign in with your GitHub account when prompted

Or install from the terminal:

```bash
code --install-extension GitHub.copilot
code --install-extension GitHub.copilot-chat
```

### What the Extension Gives You

| Feature | How to Use It |
|---------|--------------|
| Inline completions | Start typing -- suggestions appear automatically, press `Tab` to accept |
| Copilot Chat panel | `Ctrl+Shift+I` -- a chat interface in the sidebar |
| Inline chat | `Ctrl+I` -- chat anchored to the current cursor position or selection |
| Explain code | Select code, right-click, choose "Copilot > Explain" |
| Generate tests | Select a function, right-click, choose "Copilot > Generate Tests" |
| Fix error | Click the lightbulb on an error, choose "Fix using Copilot" |

### How Your Instructions Apply in VSCode

The same instruction files you set up for the CLI are read by the VSCode
extension automatically:

- `~/.copilot/copilot-instructions.md` -- global, applies everywhere
- `.github/copilot-instructions.md` -- applies in the current repo
- `.github/instructions/**/*.instructions.md` -- applies to matching file patterns

You do not need to configure anything extra. Open a repo in VSCode and your
instructions are active in both the extension and the CLI.

### Connecting the CLI to VSCode

You can connect a running Copilot CLI session to your VSCode workspace so the
agent can read open files and navigate the editor:

```
/ide
```

This opens a pairing flow. Once connected, the agent can reference files open
in VSCode directly, and you can send prompts from the CLI that interact with
your editor state.

### VSCode-Specific Prompt Techniques

**Reference the current file in chat:**

In the Copilot Chat panel, type `#file` to attach the current file:

```
#file Explain what this function does and identify any edge cases it misses.
```

**Reference a specific file by name:**

```
#file:src/services/payment.py What is the retry strategy here and is it correct?
```

**Use slash commands in VSCode chat:**

The VSCode Copilot Chat supports several built-in commands:

```
/explain    -- explain selected code
/fix        -- suggest a fix for selected code or an error
/tests      -- generate tests for a function or file
/doc        -- generate a docstring or JSDoc comment
/new        -- scaffold a new file or component
```

Example:

```
/tests Write unit tests for the selected validate_payment() function.
Cover the happy path, an invalid card number, and an expired card.
```

### CLI vs Extension -- When to Use Which

| Situation | Tool |
|-----------|------|
| Multi-file refactor or new feature | CLI -- better at multi-step tasks |
| Quick explanation of a function | VSCode inline chat (`Ctrl+I`) |
| Generating a test for a single function | VSCode right-click > Generate Tests |
| Debugging across multiple files | CLI with `systematic-debugging` skill |
| Reviewing a PR diff | CLI with `/review` or `gstack-review` |
| Autocomplete while typing | VSCode extension (always running) |
| Following a structured process (TDD, runbook) | CLI with the relevant skill |

The extension is your always-on pair programmer for small things. The CLI is the
tool you reach for when the task requires a plan, spans multiple files, or needs
a structured process enforced by a skill.

---

## Writing Effective Prompts

The quality of what the agent produces is directly proportional to the quality
of what you ask for. Here is how to communicate clearly.

### The Structure of a Good Prompt

Every effective prompt has three components:

1. **Context** -- what situation is this in?
2. **Task** -- what specifically do you want done?
3. **Constraints** -- what must be true about the output?

**Without structure:**
```
add error handling to the upload function
```

**With structure:**
```
In @src/uploads/handler.py, the upload_file() function currently does not handle
the case where the S3 client throws a ConnectionError. Add error handling that:
- Retries up to 3 times with exponential backoff
- Logs each retry attempt at WARNING level using structlog
- Raises an UploadFailed exception (defined in @src/exceptions.py) after all retries
  are exhausted
Do not change the function signature.
```

The second version gives the agent exactly the context it needs and eliminates
ambiguity about the expected outcome.

### Referencing Files Directly

Use `@filename` to bring the exact file into context rather than describing it:

```
Looking at @src/api/routes.py and @src/models/user.py, what is the fastest path
to adding email verification without touching the existing auth flow?
```

This is more precise than saying "look at the routes and user model."

### Scoping the Task

Smaller, well-scoped prompts produce better results than large open-ended ones:

- Instead of: "Refactor the whole service layer"
- Try: "Refactor @src/services/payment.py so that retry logic is handled in a
  single helper function, rather than repeated in each method"

If a task is genuinely large, ask the agent to write a plan first (`/plan`),
review it, then execute it step by step.

### Asking for Reasoning

When you are not sure whether you agree with a proposed approach, ask:

```
Before you make any changes, explain your approach and the tradeoffs involved.
```

Reading the explanation first lets you catch wrong assumptions before code is
written.

### Iterating

Do not expect perfection in one shot. A productive loop looks like:

1. Ask for a first pass
2. Review the diff with `/diff`
3. Give specific feedback ("the retry count should come from config, not be
   hardcoded")
4. Ask for the revision

This is faster than trying to write the perfect prompt the first time.

### Things That Improve Every Prompt

- **Name the file.** Use `@filename` instead of "that file" or "the auth module."
- **State what not to do.** "Do not modify the public API" is as useful as
  describing what to change.
- **Specify the format.** If you want a list, say so. If you want a summary
  before the code, say so.
- **Give the why.** "This needs to be idempotent because it may be retried by
  the job queue" helps the agent make better decisions in places you did not
  explicitly cover.

---

## Using Multiple Models Strategically

One of the most underused techniques is switching models deliberately at
different stages of a task. Claude and GPT have different strengths, and using
both is often better than sticking with one.

### Recommended Model Assignments

| Task | Model | Why |
|------|-------|-----|
| Planning and architecture | Claude Sonnet or Opus | Strong structured reasoning |
| Writing and refactoring code | Claude Sonnet | Consistent, idiomatic output |
| Complex debugging | Claude Opus | Better at multi-step causal reasoning |
| Code review | GPT-5 | Different perspective; catches things Claude normalises |
| Security review | Claude Opus or GPT-5 | Run both for important changes |
| Quick questions and lookups | Claude Sonnet | Fast, low-cost |

### The Second Opinion Workflow

The most valuable use of multiple models is getting a second opinion on your
own work. After completing a feature with Claude:

1. Use `/model` to switch to GPT-5
2. Ask it to review the same changes independently:

```
Review the changes in @src/services/payment.py. Be critical. I want to know
about correctness issues, edge cases, and anything you would push back on in
a code review.
```

3. Compare the feedback from both models
4. Switch back to Claude to implement any changes

This works because the two models do not share the same internal biases. Claude
may have normalised a pattern it generated; GPT will notice it looks unusual.

### When to Use Claude Opus

Opus is slower and uses the same quota unit as Sonnet, but produces noticeably
better output for:

- Initial architecture decisions on a new system
- Debugging a subtle, non-obvious problem where the root cause is not clear
- Writing instructions or documentation that will be reused many times
- Reviewing a complex security-sensitive change

For routine coding tasks, Sonnet is faster and produces results that are
difficult to distinguish from Opus.

---

## Practical Workflow Examples

### Starting a New Feature

```
# 1. Brainstorm the design before writing anything
Use the brainstorming skill to help me think through adding rate limiting to
the POST /api/upload endpoint. Users are limited to 10 uploads per minute.

# 2. Write a plan
/plan
Add rate limiting to the upload endpoint. Approach: ...

# 3. Review the plan with gstack
Use gstack-plan-eng-review to review this plan.

# 4. Implement using TDD
Use the test-driven-development skill. Start with the rate limiter tests in
@tests/test_upload.py.

# 5. Code review before PR
Use gstack-review on the changes in the current branch.
```

### Debugging a Production Issue

```
# 1. Invoke systematic debugging
Use systematic-debugging. Here is the error: [paste error and stack trace]

# 2. Do not skip straight to the fix -- understand the root cause first.
# The skill will walk you through this.

# 3. After implementing the fix, verify
Use verification-before-completion. Confirm the fix addresses the root cause
and does not introduce regressions.
```

### Pre-PR Checklist

Before opening any pull request on a significant change:

```
1. /diff                         -- review all changes
2. gstack-review                 -- code quality
3. gstack-cso                    -- security (for auth, data handling, or infra changes)
4. Switch to GPT-5, run a review -- second opinion
5. gstack-qa (if it has a UI)   -- visual/functional check
6. /share                        -- save session summary for reference
```

---

## Quick Reference

### Keyboard Shortcuts Inside the CLI

| Shortcut | Action |
|----------|--------|
| `Shift+Tab` | Switch modes (Normal / Autopilot) |
| `Ctrl+S` | Run command and preserve input |
| `Ctrl+L` | Clear screen |
| `Ctrl+T` | Toggle reasoning display |
| `Ctrl+C` twice | Exit |
| `Ctrl+G` | Edit prompt in your `$EDITOR` |
| `Ctrl+W` | Delete previous word |

### Files and Directories

| Path | Purpose |
|------|---------|
| `~/.copilot/copilot-instructions.md` | Global instructions |
| `~/.copilot/settings.json` | Model preference and other settings |
| `~/.copilot/skills/` | Installed skills |
| `.github/copilot-instructions.md` | Per-repo instructions |
| `AGENTS.md` | Repo-level instructions (read by multiple agents) |

### Getting Help

- `/help` -- full interactive command reference
- `/changelog` -- what changed in recent versions
- `/feedback` -- submit feedback directly to GitHub
- `/update` -- update to the latest version

---

*This guide is versioned in the dotfiles repository. If something has changed
or you find a gap, open an issue or update the guide directly.*
