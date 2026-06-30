# tmux-rename.zsh - Automatically rename tmux windows/panes from context
# Hooks: precmd, chpwd
# Guard: only runs inside tmux, only in interactive shells

# Bail early if not in tmux or not interactive
[[ -z "$TMUX" ]] && return
[[ ! -o interactive ]] && return

# --- Configuration ---
_tmux_rename_max_repo=15
_tmux_rename_max_total=25
_tmux_rename_ticket_pattern='([A-Z]{2,10}-[0-9]+)'
_tmux_rename_default_branches='main|master|develop|dev'

# --- Helper functions ---

_tmux_rename_shorten_repo() {
  local name="$1"
  # Strip known suffixes
  name=$(printf '%s' "$name" | sed -E "s/(-playbooks|-config|-infrastructure|-automation)$//")
  # Truncate if still too long
  if (( ${#name} > _tmux_rename_max_repo )); then
    name="${name:0:$(( _tmux_rename_max_repo - 3 ))}..."
  fi
  printf '%s' "$name"
}

_tmux_rename_extract_ticket() {
  local branch="$1"
  if [[ "$branch" =~ $_tmux_rename_ticket_pattern ]]; then
    printf '%s' "${match[1]}"
  fi
}

_tmux_rename_compute_name() {
  local git_toplevel git_repo_name branch ticket short_repo window_name

  # Accept cached git_toplevel as argument; detect if not provided
  git_toplevel="${1:-$(git rev-parse --show-toplevel 2>/dev/null)}"

  if [[ -z "$git_toplevel" || ! -d "$git_toplevel/.git" ]]; then
    # Not a git repo: use directory-based naming
    local cwd="${PWD/#$HOME/~}"
    local depth=$(echo "$cwd" | tr '/' '\n' | wc -l)
    if (( depth <= 3 )); then
      # Shallow path: last segment
      printf '%s' "${PWD:t}"
    else
      # Deep path: last 2 segments
      printf '%s' "$(basename "$(dirname "$PWD")")/$(basename "$PWD")"
    fi
    return
  fi

  # Git repo detected
  git_repo_name=$(basename "$git_toplevel")
  short_repo=$(_tmux_rename_shorten_repo "$git_repo_name")
  branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null)

  # Guard: if branch detection failed entirely, show repo name only
  if [[ -z "$branch" ]]; then
    printf '%s' "$short_repo"
    return
  fi

  # Check if on a default branch
  if [[ "$branch" =~ ^($_tmux_rename_default_branches)$ ]]; then
    window_name="$short_repo"
  else
    # Try to extract ticket ID
    ticket=$(_tmux_rename_extract_ticket "$branch")
    if [[ -n "$ticket" ]]; then
      window_name="${short_repo}:${ticket}"
    else
      # Non-default branch, no ticket: use branch slug (truncated)
      local branch_slug="${branch##*/}"  # strip prefix like feature/
      if (( ${#branch_slug} > 12 )); then
        branch_slug="${branch_slug:0:9}..."
      fi
      window_name="${short_repo}:${branch_slug}"
    fi
  fi

  # Enforce max total length (truncate repo, never ticket)
  if (( ${#window_name} > _tmux_rename_max_total )); then
    if [[ -n "$ticket" ]]; then
      local available=$(( _tmux_rename_max_total - ${#ticket} - 1 ))  # -1 for colon
      if (( available < 3 )); then
        available=3
      fi
      short_repo="${short_repo:0:$available}"
      window_name="${short_repo}:${ticket}"
    else
      window_name="${window_name:0:$(( _tmux_rename_max_total - 3 ))}..."
    fi
  fi

  printf '%s' "$window_name"
}

_tmux_rename_compute_pane_title() {
  # Accept cached git_toplevel as argument
  local git_toplevel="${1:-}"

  if [[ -z "$git_toplevel" || ! -d "$git_toplevel/.git" ]]; then
    # Not a git repo: just use directory name
    printf '%s' "${PWD:t}"
    return
  fi

  # Relative path from repo root
  local rel_path="${PWD#$git_toplevel}"
  rel_path="${rel_path#/}"  # strip leading slash

  if [[ -z "$rel_path" ]]; then
    # At repo root
    printf '%s' "$(basename "$git_toplevel")"
  else
    printf '%s' "$rel_path"
  fi
}

_tmux_rename_update() {
  # Check for manual name override (set by Copilot skill)
  local window_id
  window_id=$(tmux display-message -p '#{window_id}' 2>/dev/null)
  local manual_name
  manual_name=$(tmux show-environment -g "@manual_name_${window_id}" 2>/dev/null)
  if [[ "$manual_name" == *"=1" ]]; then
    # Manual name is set and active; skip auto-rename
    return
  fi

  # Cache git toplevel once for both functions
  local git_toplevel
  git_toplevel=$(git rev-parse --show-toplevel 2>/dev/null) || git_toplevel=""

  # Only rename the WINDOW if this is the sole pane (multi-pane windows keep their name)
  local pane_count
  pane_count=$(tmux display-message -p '#{window_panes}' 2>/dev/null)
  if [[ "$pane_count" == "1" ]]; then
    local name
    name=$(_tmux_rename_compute_name "$git_toplevel")
    if [[ -n "$name" ]]; then
      tmux rename-window "$name" 2>/dev/null
    fi
  fi

  # Always set pane title (per-pane, no conflict)
  local pane_title
  pane_title=$(_tmux_rename_compute_pane_title "$git_toplevel")
  if [[ -n "$pane_title" ]]; then
    printf '\033]2;%s\033\\' "$pane_title"
  fi
}

# --- Hook registration ---
autoload -Uz add-zsh-hook
add-zsh-hook precmd _tmux_rename_update
add-zsh-hook chpwd _tmux_rename_update
