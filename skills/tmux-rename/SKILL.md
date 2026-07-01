---
name: tmux-rename
description: Intelligently rename tmux windows and panes based on context. Use when the user says "rename my panes", "name this window", "what are my windows", or wants to set a semantic theme for a window.
---

# tmux Smart Rename

Rename tmux windows and panes based on what is happening in them.

## When to Use

- User asks to rename windows or panes
- User says "this is my X window" (theme labeling)
- User asks "what are my windows doing"
- User asks to rename all windows (bulk)

## Capabilities

### 1. Scan and Report

List all windows and panes with their current context:

```bash
tmux list-windows -F '#{window_index}: #{window_name} (#{window_panes} panes)'
tmux list-panes -a -F '#{window_index}.#{pane_index}: #{pane_current_path} [#{pane_current_command}]'
```

Present a summary of what each window/pane is doing.

### 2. Rename Window

Set a window name:

```bash
tmux rename-window -t :<window_index> "<name>"
```

### 3. Set Pane Title

Set a specific pane's title:

```bash
tmux select-pane -t :<window>.<pane> -T "<title>"
```

### 4. Theme Labeling (Manual Override)

When the user says "this is my X window", set both the name AND the manual
override environment variable so the shell hook does not overwrite it:

```bash
# Get current window ID
WINDOW_ID=$(tmux display-message -p '#{window_id}')

# Set the name
tmux rename-window "<user's theme name>"

# Set the override flag so shell hook skips this window
tmux set-environment -g "@manual_name_${WINDOW_ID}" "1"
```

### 5. Release Manual Override

When the user says "let the hook rename this window" or "auto-rename this":

```bash
WINDOW_ID=$(tmux display-message -p '#{window_id}')
tmux set-environment -g -u "@manual_name_${WINDOW_ID}"
```

The shell hook will resume auto-naming on the next prompt.

### 6. Bulk Rename

When asked to rename all windows, iterate through each:

```bash
# Get all pane info
tmux list-panes -a -F '#{window_index}|#{pane_current_path}|#{pane_current_command}'
```

For each window, determine the best name by looking at:
1. The CWD of the first/active pane
2. Git repo and branch (if applicable)
3. Running commands across panes

Then set names using `tmux rename-window -t :<index> "<name>"`.

### 7. Pane Differentiation

When naming panes within a window, use the running command or relative
directory to distinguish them:

| Running command | Suggested pane title |
|----------------|---------------------|
| vim, nvim | "editor" or "editor (<filename>)" |
| pytest, jest, go test | "tests" |
| tail -f, less +F | "logs" |
| node (copilot) | "copilot" |
| ssh <host> | "<hostname>" |
| python, ipython | "repl" |
| Default | CWD relative to repo root |

## Rules

- Always show the user what you intend to rename BEFORE doing it
- For bulk operations, present the proposed names and ask for confirmation
- Respect existing manual overrides (check `@manual_name_*` env vars)
- When uncertain about a name, ask the user
- Keep names concise: max 25 characters for windows, descriptive for panes

## Integration with Shell Hook

A zsh shell hook (`~/.config/zsh/hooks/tmux-rename.zsh`) handles automatic
renaming on every prompt. This skill provides:

- Manual overrides that persist (via tmux environment variables)
- Semantic/theme naming that the hook cannot derive from signals alone
- Bulk operations across all windows
- Pane-specific naming based on deeper context analysis
