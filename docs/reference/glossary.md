# Glossary

| Term | Definition |
|------|-----------|
| Agent | An AI instance running in a separate context window, typically handling a delegated subtask. |
| Background agent | An agent that runs asynchronously while you continue other work. |
| Brainstorming | A structured design exploration process that precedes implementation. |
| Context window | The total amount of text (prompt + conversation + files) the model can process at once. |
| Device flow | OAuth authentication method where you visit a URL and enter a code, rather than pasting tokens. |
| gstack | A collection of skills focused on browser-based QA, deployment, and visual workflows. |
| Grounding | Providing the AI with specific, relevant context to reduce hallucination. |
| Hallucination | When an AI generates plausible-sounding but factually incorrect information. |
| Instruction file | A markdown file that provides persistent context and rules to the AI tool. |
| MCP (Model Context Protocol) | A standard for connecting AI tools to external data sources and capabilities. |
| Model tier | A category of AI model grouped by capability and cost (reasoning, standard, fast). |
| Multi-model review | Using two or more different AI models to review the same work independently. |
| Plan | A structured implementation document that breaks work into ordered, dependency-tracked steps. |
| Prompt | The text input you give to an AI tool: the quality of output depends heavily on prompt quality. |
| Reasoning model | A model optimized for complex multi-step thinking at the cost of speed and price. |
| Skill | A reusable instruction set that encodes a specific workflow or methodology. |
| Spec | A design specification document produced during brainstorming that defines what will be built. |
| Subagent | An agent dispatched by the primary AI to handle a specific subtask independently. |
| Superpowers | A collection of process and quality skills for structured software development workflows. |
| Tool | A capability available to the AI (file editing, bash, grep, web browsing, etc.). |
| Verification | The practice of confirming AI-generated output is correct before accepting it. |

Canonical forms for all terms used across all three tiers.
When in doubt, use the form listed here. Created 2026-05-19.

## Tool names

| Canonical form | NOT this | Notes |
|---------------|----------|-------|
| GitHub Copilot | Github copilot, GH Copilot, COPILOT | Full name on first use per file, "Copilot" after |
| Copilot CLI | copilot cli, copilot-cli | The terminal tool specifically |
| Claude | claude, CLAUDE | Anthropic's model family |
| Claude Code | claude code, Claude code | CLI tool by Anthropic specifically |
| Codex CLI | codex, CODEX, OpenAI Codex CLI | CLI tool by OpenAI |
| ChatGPT | chatgpt, Chat GPT, chat-gpt | OpenAI's web chat interface |
| OpenAI | openai, OPENAI, Open AI | The company |
| Anthropic | anthropic, ANTHROPIC | The company |
| VSCode | VS Code, vscode, vs code | Short form in prose |
| Visual Studio Code | visual studio code | Full name on first formal use only |
| Neovim | neovim, NeoVim, neo-vim | Editor |
| GitHub | Github, github, GITHUB | Always capital H |
| GitHub Desktop | Github Desktop, github desktop | GUI git client |

## AI model names

| Canonical form | NOT this | Notes |
|---------------|----------|-------|
| GPT-4o | gpt-4o, GPT4o | Include hyphen |
| GPT-5 | gpt-5, GPT5 | Include hyphen |
| Claude Sonnet | claude sonnet, Sonnet | Include "Claude" prefix on first use |
| Claude Opus | claude opus, Opus | Include "Claude" prefix on first use |
| Claude Haiku | claude haiku, Haiku | Include "Claude" prefix on first use |

## Concepts (shared across tiers)

| Canonical form | NOT this | Notes |
|---------------|----------|-------|
| prompt | query, question, input | What you send the AI. "Query" acceptable in research context only. |
| response | answer, output, reply | What AI returns. "Output" acceptable when referring to generated files. |
| skill | recipe, macro, template | Packaged reusable workflow (Ch5+ concept). Not "recipe" except in analogy. |
| workflow | process, procedure, pipeline | A multi-step sequence of actions |
| hallucination | confabulation, fabrication, making things up | AI generating false information. "Making things up" acceptable in Tier 3 as plain-language alternative. |
| model | AI, engine, brain | The underlying AI system. "AI" acceptable as general term. Never "brain" or "engine". |
| context window | memory, token limit | How much text the AI can consider at once |
| token | word-piece, unit | Unit of text the model processes. Approximate: 1 token is roughly 3/4 of a word. |

## Interface labels

| Canonical form | NOT this | Notes |
|---------------|----------|-------|
| web chat | browser interface, web UI, chat interface, web app | The browser-based AI conversation interface |
| editor integration | IDE plugin, extension, editor mode | AI built into your code editor |
| CLI | command line, terminal, shell | As an interface category. "Terminal" acceptable when referring to the application window. |

## Action terms

| Canonical form | NOT this | Notes |
|---------------|----------|-------|
| verify | validate, check, confirm | When checking AI output against sources |
| iterate | refine, improve, loop | When having a multi-turn conversation to improve results |
| scaffold | template, boilerplate, starter | When AI provides structure you fill in |

## Tier-specific terms (allowed only in that tier)

### Tier 1 only
- AWX, tachi, PagerDuty, Jira, Confluence (by name)
- PHI, HIPAA, HITRUST
- SRE, SLO, SLI, SLA
- Terraform, Ansible, Kubernetes (by name)
- runbook, playbook, incident

### Tier 2 only
- Infrastructure-as-code (generic, not tool names)
- CI/CD pipeline (generic)
- Deployment, rollout, canary (generic DevOps terms)
- (No Iodine-specific tool names)

### Tier 3 only
- No jargon without inline definition
- "Code editor" not "IDE"
- "Version control" not "git" on first use (define git inline)
- "Shared project" not "repository" on first use (define repository inline)
- "Change request" or "pull request (a way to propose changes)" not bare "PR"
