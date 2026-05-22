# Skills catalog

### Process skills

| Skill | Description | When to use | Invoke with |
|-------|-------------|-------------|-------------|
| brainstorming | Collaborative design exploration before implementation | Starting any new feature, component, or significant change | "Use the brainstorming skill" |
| writing-plans | Creates structured implementation plans from specs | After design approval, before coding | "Use writing-plans to create the implementation plan" |
| executing-plans | Executes plans with review checkpoints | When ready to implement an approved plan | "Execute the plan" or invoke executing-plans |
| dispatching-parallel-agents | Runs independent tasks concurrently | 2+ tasks with no shared state or sequential deps | "Dispatch parallel agents for X and Y" |
| subagent-driven-development | Delegates implementation to focused subagents | Complex multi-file changes that benefit from isolated context | "Use subagent-driven development" |
| finishing-a-development-branch | Guides PR/merge decisions at branch completion | Implementation complete, tests pass, ready to integrate | "Finish this branch" |

### Quality skills

| Skill | Description | When to use | Invoke with |
|-------|-------------|-------------|-------------|
| test-driven-development | Red-green-refactor TDD workflow | Writing new functions or fixing bugs | "Use TDD for this" |
| verification-before-completion | Final validation before declaring done | End of any task, before commit | Automatically suggested at task end |
| requesting-code-review | Structures outgoing code review requests | Before submitting PR for review | "Help me request a code review" |
| receiving-code-review | Processes incoming review feedback systematically | After receiving PR feedback | "Help me address this code review" |
| pre-commit-workflow | Runs pre-commit checks and fixes | Before committing changes | "Run pre-commit checks" |
| conventional-commit | Generates conventional commit messages | When committing changes | "Write a commit message" |
| ruff-recursive-fix | Fixes Python linting issues recursively | After linting failures in Python code | "Fix ruff issues" |
| pytest-coverage | Runs pytest with coverage analysis | Checking test coverage gaps | "Run pytest with coverage" |

### gstack skills

| Skill | Description | When to use | Invoke with |
|-------|-------------|-------------|-------------|
| gstack-browse | Headless browser for page interaction | Testing deployed pages, verifying state | "Open [URL] in browser" |
| gstack-qa | Systematic QA testing + fix loop | Feature ready for testing | "QA test this site" |
| gstack-qa-only | Report-only QA (no fixes) | Bug report without code changes | "QA report only" |
| gstack-design-review | Visual consistency and polish audit | After UI implementation | "Design review this page" |
| gstack-design-consultation | Creates design system from scratch | New project needs visual identity | "Design consultation" |
| gstack-ship | PR creation and ship workflow | Ready to ship a change | "Ship it" |
| gstack-land-and-deploy | Merge + deploy + canary verification | PR approved, ready to land | "Land and deploy" |
| gstack-review | High signal-to-noise code review | Before PR submission | "Review my changes" |
| gstack-investigate | Root cause debugging with iron law | Bugs, errors, unexpected behavior | "Investigate this error" |
| gstack-benchmark | Performance regression detection | Checking page speed, bundle size | "Benchmark this page" |
| gstack-canary | Post-deploy monitoring | After shipping to production | "Monitor this deploy" |
| gstack-retro | Weekly engineering retrospective | End of sprint or work week | "Weekly retro" |
| gstack-autoplan | Automated full review pipeline | Want all reviews without answering questions | "Autoplan" or "auto review" |
| gstack-plan-ceo-review | Strategy and scope review | Questioning ambition or scope of a plan | "Think bigger" or "CEO review" |
| gstack-plan-eng-review | Architecture and execution review | Before coding, after design | "Engineering review" |
| gstack-plan-design-review | Design critique of a plan | Plan has UI/UX components | "Design review the plan" |
| gstack-office-hours | YC-style brainstorming for ideas | Exploring whether something is worth building | "Office hours" |
| gstack-careful | Safety guardrails for destructive commands | Working near production | "Be careful" or "careful mode" |
| gstack-freeze | Restrict edits to a directory | Debugging (prevent accidental edits elsewhere) | "Freeze edits to src/" |
| gstack-guard | Full safety mode (careful + freeze) | Maximum safety near production | "Guard mode" |
| gstack-cso | Security audit (OWASP, STRIDE, supply chain) | Security review needed | "CSO review" or "security audit" |
| gstack-document-release | Post-ship documentation sync | After merging/shipping code | "Update the docs" |
| gstack-unfreeze | Remove directory edit restrictions | Done with restricted editing | "Unfreeze" |
| gstack-setup-browser-cookies | Configure browser cookies for auth | Testing authenticated pages | "Setup browser cookies" |
| gstack-setup-deploy | Configure deployment settings | Setting up ship/deploy workflow | "Setup deploy" |
| gstack-upgrade | Upgrade gstack skills | Updating to latest gstack | "Upgrade gstack" |

### Domain skills

| Skill | Description | When to use | Invoke with |
|-------|-------------|-------------|-------------|
| security-review | Targeted security analysis of changes | Code touching auth, crypto, input handling | "Security review this" |
| postgresql-code-review | PostgreSQL-specific code review | DB migrations, queries, schema changes | "Review this SQL" |
| pdf-reader | Extract and work with PDF content | Need to read a PDF document | "Read this PDF" |
| code-audit | Full codebase quality audit | Periodic code health check | "Audit this codebase" |
