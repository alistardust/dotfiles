# Command cheat sheet

| Task | Copilot CLI | Claude Code | Codex |
|------|-------------|-------------|-------|
| Start session | `copilot` | `claude` | `codex` |
| Set model | `copilot config set model <name>` | `claude config set model <name>` or `/model <name>` | `codex --model <name>` |
| Auth | `copilot auth` | `claude auth` | Set `OPENAI_API_KEY` env var |
| List models | `copilot config list-models` | `/model` (shows available) | `codex --list-models` |
| Non-interactive | `copilot -m "prompt"` | `claude -p "prompt"` | `codex "prompt"` |
| Resume session | (sessions persist) | `claude --continue` | (sessions persist) |
| Add context | Mention file paths in prompt | `/add file.py` or mention paths | Mention paths or use `--file` |
| Run in repo | `cd repo && copilot` | `cd repo && claude` | `cd repo && codex` |
| Check version | `copilot --version` | `claude --version` | `codex --version` |
| Update | `npm update -g @github/copilot` | `npm update -g @anthropic-ai/claude-code` | `npm update -g @openai/codex` |

Last verified: 2026-05-19

## GitHub Copilot CLI

| Field | Value |
|-------|-------|
| Package | `@github/copilot` (npm global) |
| Install | `npm install -g @github/copilot` |
| Binary | `/opt/homebrew/bin/copilot` |
| Version | 1.0.49 |
| Auth | `copilot login` (opens browser OAuth flow) |
| Auth check | `gh auth status` (shared with gh CLI) |
| Model selection | `copilot --model gpt-5.2` (per-session flag) |
| Interactive | `copilot` or `copilot -i "prompt"` |
| Non-interactive | `copilot -p "prompt" --allow-all-tools` |
| Update | `copilot update` |
| Init instructions | `copilot init` |
| Resume session | `copilot --continue` or `copilot --resume` |

### gh copilot extension

Also accessible via `gh copilot` (preview). If Copilot CLI is in PATH, `gh` executes
it directly. Otherwise downloads to `~/.local/share/gh/copilot`.

| Field | Value |
|-------|-------|
| Check | `gh extension list \| grep copilot` |
| Version | Part of gh 2.92.0 integration |
| Usage | `gh copilot [flags] [args]` |

### Key subcommands

- `copilot completion <shell>`: generate shell completions
- `copilot mcp`: manage MCP servers
- `copilot plugin`: manage plugins
- `copilot login`: authenticate

### Permission flags (for non-interactive/scripting)

- `--allow-all-tools`: auto-approve all tool use
- `--allow-all-paths`: disable file path restrictions
- `--allow-all-urls`: allow all URL access
- `--allow-all` / `--yolo`: enable everything
- `--allow-tool='shell(git:*)'`: granular tool permissions
- `--deny-tool='shell(git push)'`: granular denials

### Config and help topics

Run `copilot help <topic>` for: commands, config, environment, logging,
monitoring, permissions, providers.

## Claude Code CLI

| Field | Value |
|-------|-------|
| Status | **NOT INSTALLED** |
| Install method | `npm install -g @anthropic-ai/claude-code` (per Anthropic docs) |
| Reason not verified | Not installed on this machine |
| Fallback | Use web chat at claude.ai for Tier 3 examples |

UNVERIFIED: install command, auth flow, model selection, config syntax.
Install and re-verify before writing CLI-specific examples for Claude Code.

## OpenAI Codex CLI

| Field | Value |
|-------|-------|
| Status | **NOT INSTALLED** |
| Install method | `npm install -g @openai/codex` (per OpenAI docs) |
| Reason not verified | Not installed on this machine |
| Fallback | Use web chat at chatgpt.com for Tier 3 examples |

UNVERIFIED: install command, auth flow, model selection, config syntax.
Install and re-verify before writing CLI-specific examples for Codex.

## Readability scoring tool

| Field | Value |
|-------|-------|
| Tool | `npx readable` |
| Status | **NOT AVAILABLE** (package not found) |
| Fallback | readabilityformulas.com (manual, paste text into web form) |
| Alternative | `npx textstat` or Python `textstat` library |

Need to identify a working CLI readability scorer before Phase 3 writing begins.

## Summary

| Tool | Status | Verified |
|------|--------|----------|
| GitHub Copilot CLI | Installed, authenticated, working | 2026-05-19 |
| gh copilot extension | Installed via gh 2.92.0 | 2026-05-19 |
| Claude Code CLI | NOT INSTALLED | - |
| OpenAI Codex CLI | NOT INSTALLED | - |
| Readability scorer | NOT AVAILABLE (need alternative) | - |

## Action items

1. Install Claude Code CLI and re-verify (needed for Tier 2 examples)
2. Install OpenAI Codex CLI and re-verify (needed for Tier 2 examples)
3. Find working readability scoring tool for Tier 3 validation
4. All three are non-blocking for Phase 0 completion (web chat fallback exists)
