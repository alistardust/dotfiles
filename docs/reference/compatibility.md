# Tool compatibility matrix

| Feature | Copilot CLI | Claude Code | Codex |
|---------|-------------|-------------|-------|
| Instruction files | `.github/copilot-instructions.md` (repo), `~/.github/copilot-instructions.md` (global) | `CLAUDE.md` (repo), `~/.claude/CLAUDE.md` (global) | `AGENTS.md` (repo), codex config (global) |
| Skill support | Yes (via instruction files + skill directories) | Yes (via CLAUDE.md + skill references) | Limited (via AGENTS.md) |
| Skill invocation | Natural language or `/skill-name` | Natural language reference | Natural language |
| Model selection | Multi-provider (Claude, GPT, etc.) | Anthropic models only | OpenAI models only |
| Browser/QA tools | Yes (gstack browse, qa) | Yes (with MCP or built-in) | Limited |
| Subagent support | Yes (task tool, background agents) | Yes (via tool use) | Yes (via sandbox) |
| MCP support | Yes | Yes | Yes |
| File editing | Yes (edit, create tools) | Yes (built-in) | Yes (built-in) |
| Git integration | Yes (commit, diff, status) | Yes (built-in) | Yes (built-in) |
| Background tasks | Yes (async agents) | Limited | Yes (sandbox) |
| Session persistence | Yes | Yes (with --continue) | Yes |
| Cost visibility | Included in Copilot license | Per-token billing | Per-token billing |
