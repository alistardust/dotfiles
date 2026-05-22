# Getting started

### Prerequisites

Before installing anything, make sure you have the following:

- Node.js 18+
- npm
- A GitHub account with an active Copilot license
- An Anthropic API key for Claude Code
- An OpenAI API key for Codex

### Install the CLIs

Install all three tools with npm. These commands work on Linux, macOS, and WSL2.

```bash
# GitHub Copilot CLI
npm install -g @github/copilot

# Claude Code
npm install -g @anthropic-ai/claude-code

# OpenAI Codex
npm install -g @openai/codex
```

> **Last verified:** 2026-05-19. See `cli-verification.md` for current status.

### Authenticate the tools

#### Recommended default: OAuth device flow

Use the built-in auth flow first when the tool supports it.

```bash
copilot login
claude auth
```

This is the cleanest default for local work. You do not have to manage raw secrets in shell startup files, and the tool handles token refresh for you.

#### PAT fallback: use an OS credential store first

If you need to use a personal access token or API key directly, store it in the platform credential store before you consider a dotfile export.

macOS Keychain example:

```bash
security add-generic-password -a "$USER" -s claude-code-api-key -w '<anthropic-api-key>'
security add-generic-password -a "$USER" -s codex-api-key -w '<openai-api-key>'
```

Linux options:

```bash
secret-tool store --label="Claude Code API key" service claude-code user "$USER"
pass insert ai/codex/api-key
```

Windows: use Credential Manager.

#### Last resort only: export from a shell dotfile

Only use shell exports when the tool has no better option for your setup. If you do this, lock down file permissions first and scope the token to the minimum permissions required. Never do this on shared hosts, bastions, or CI runners. See [Chapter 9](#chapter-9-credential-and-data-safety) for the full safety discussion.

```bash
chmod 600 ~/.bashrc ~/.zshrc ~/.config/fish/config.fish
```

Bash:

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export OPENAI_API_KEY="your-openai-api-key"
```

Zsh:

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export OPENAI_API_KEY="your-openai-api-key"
```

Fish:

```fish
set -x ANTHROPIC_API_KEY "your-anthropic-api-key"
set -x OPENAI_API_KEY "your-openai-api-key"
```

### First run smoke test

Once Copilot CLI is installed and authenticated, run a simple prompt from your normal shell.

```bash
copilot "what shell am I using?"
```

If the tool replies sensibly and does not error on auth, you have a working baseline.

### Set a preferred model

Pick a default model early so your results are predictable.

```bash
copilot config set model claude-sonnet-4-5
claude config set model claude-sonnet-4-5
codex --model gpt-5.4
```

For VSCode, open the Command Palette and run `Copilot: Select Model`.

### Editor integration

The CLI is useful on its own, but editor integration still matters for inline completion and chat.

VSCode extension install:

```bash
code --install-extension GitHub.copilot
```

For JetBrains IDEs, install the GitHub Copilot plugin.

### Platform coverage

These workflows are aimed at Linux native, macOS native, and WSL2 from Windows. Windows-native shells such as PowerShell or Git Bash are fine for editor integration, but the terminal examples in this guide assume Linux, macOS, or WSL2.

---

[< Introduction](index.md) | [The instruction system >](instructions.md)
