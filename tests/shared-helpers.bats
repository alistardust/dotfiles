#!/usr/bin/env bats
# shellcheck shell=bash
# shellcheck disable=SC1090,SC2329

setup() {
    export SCRIPT_DIR="$BATS_TEST_DIRNAME/.."
    export HOME="$BATS_TEST_TMPDIR/home"
    mkdir -p "$HOME"

    DRY_RUN=false
    CLONE_VIA=ssh
    MOCK_COMMANDS=""
    MOCK_BUN_AFTER_FETCH=false

    command_exists() {
        [[ " ${MOCK_COMMANDS} " == *" $1 "* ]]
    }

    run_helper() {
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '[dry] %s\n' "$*"
        else
            "$@"
        fi
    }

    ok() {
        printf 'ok:%s\n' "$*"
    }

    warn() {
        printf 'warn:%s\n' "$*"
    }

    log() {
        printf 'log:%s\n' "$*"
    }

    fetch_and_run() {
        printf 'fetch:%s\n' "$1"
        if [[ "$MOCK_BUN_AFTER_FETCH" == "true" ]]; then
            mkdir -p "$HOME/.bun/bin"
            cat > "$HOME/.bun/bin/bun" <<'EOF'
#!/usr/bin/env bash
echo 1.2.3
EOF
            chmod +x "$HOME/.bun/bin/bun"
        fi
    }

    git_url() {
        local url="$1"
        if [[ "$CLONE_VIA" == "https" && "$url" == git@github.com:* ]]; then
            echo "https://github.com/${url#git@github.com:}"
        else
            echo "$url"
        fi
    }

    git() {
        if [[ "$1" == "clone" ]]; then
            local target="${*: -1}"
            printf 'git:%s\n' "$*"
            mkdir -p "$target"
            return 0
        fi
        command git "$@"
    }

    bash() {
        printf 'bash:%s\n' "$*"
    }

    source <(
        python3 - "$SCRIPT_DIR/sections/_helpers.sh" <<'PY'
from pathlib import Path
import re
import sys

source_path = Path(sys.argv[1])
content = source_path.read_text()
content = re.sub(r'\brun\b', 'run_helper', content)
print(content)
PY
    )
}

@test "ensure_bun: succeeds when bun is already on PATH" {
    MOCK_COMMANDS="bun"
    bun() {
        echo 1.2.3
    }

    run ensure_bun

    [[ "$status" -eq 0 ]]
    [[ "$output" == *"bun already installed"* ]]
}

@test "ensure_bun: succeeds when bun binary exists under HOME" {
    mkdir -p "$HOME/.bun/bin"
    cat > "$HOME/.bun/bin/bun" <<'EOF'
#!/usr/bin/env bash
echo 1.2.3
EOF
    chmod +x "$HOME/.bun/bin/bun"

    run ensure_bun

    [[ "$status" -eq 0 ]]
    [[ "$output" == *"bun already installed"* ]]
}

@test "ensure_bun: dry-run does not install bun" {
    DRY_RUN=true

    run ensure_bun

    [[ "$status" -eq 0 ]]
    [[ "$output" == *"[dry] install Bun via fetch_and_run"* ]]
    [[ ! -x "$HOME/.bun/bin/bun" ]]
}

@test "ensure_bun: installs bun via fetch_and_run when missing" {
    MOCK_BUN_AFTER_FETCH=true

    run ensure_bun

    [[ "$status" -eq 0 ]]
    [[ "$output" == *"fetch:https://bun.sh/install"* ]]
    [[ -x "$HOME/.bun/bin/bun" ]]
}

@test "ensure_bun: fails when bun is still missing after install attempt" {
    run ensure_bun

    [[ "$status" -eq 1 ]]
    [[ "$output" == *"warn:bun not found after install"* ]]
}

@test "install_instructions: copies the source file when destination is missing" {
    local dest_dir="$HOME/.copilot"
    local dest_file="$dest_dir/copilot-instructions.md"
    local src_file="$HOME/source.md"

    printf 'hello from source\n' > "$src_file"

    run install_instructions "$dest_dir" "$dest_file" "$src_file" "Copilot"

    [[ "$status" -eq 0 ]]
    [[ -f "$dest_file" ]]
    [[ "$(cat "$dest_file")" == "hello from source" ]]
}

@test "install_instructions: leaves an existing destination unchanged" {
    local dest_dir="$HOME/.claude"
    local dest_file="$dest_dir/CLAUDE.md"
    local src_file="$HOME/source.md"

    mkdir -p "$dest_dir"
    printf 'existing\n' > "$dest_file"
    printf 'replacement\n' > "$src_file"

    run install_instructions "$dest_dir" "$dest_file" "$src_file" "Claude Code"

    [[ "$status" -eq 0 ]]
    [[ "$(cat "$dest_file")" == "existing" ]]
    [[ "$output" == *"instructions already exist"* ]]
}

@test "install_instructions: dry-run does not copy the file" {
    local dest_dir="$HOME/.codex"
    local dest_file="$dest_dir/AGENTS.md"
    local src_file="$HOME/source.md"

    DRY_RUN=true
    printf 'codex\n' > "$src_file"

    run install_instructions "$dest_dir" "$dest_file" "$src_file" "Codex"

    [[ "$status" -eq 0 ]]
    [[ ! -f "$dest_file" ]]
    [[ "$output" == *"[dry] copy"* ]]
}

@test "install_gstack: dry-run prints clone and setup steps" {
    local gstack_dir="$HOME/.claude/skills/gstack"

    DRY_RUN=true

    run install_gstack "$gstack_dir" "--host copilot"

    [[ "$status" -eq 0 ]]
    [[ ! -d "$gstack_dir" ]]
    [[ "$output" == *"[dry] install Bun via fetch_and_run"* ]]
    [[ "$output" == *"[dry] cd $gstack_dir && ./setup --host copilot"* ]]
}

@test "install_gstack: returns early when gstack is already installed" {
    local gstack_dir="$HOME/.claude/skills/gstack"

    mkdir -p "$gstack_dir"

    run install_gstack "$gstack_dir" "--host copilot"

    [[ "$status" -eq 0 ]]
    [[ "$output" == *"gstack already installed"* ]]
}

@test "install_gstack: clones the repo and runs setup" {
    local gstack_dir="$HOME/.claude/skills/gstack"

    mkdir -p "$HOME/.bun/bin"
    cat > "$HOME/.bun/bin/bun" <<'EOF'
#!/usr/bin/env bash
echo 1.2.3
EOF
    chmod +x "$HOME/.bun/bin/bun"
    CLONE_VIA=https

    run install_gstack "$gstack_dir" "--host codex --quiet" "git@github.com:garrytan/gstack.git" "--branch add-copilot-cli-support"

    [[ "$status" -eq 0 ]]
    [[ -d "$gstack_dir" ]]
    [[ "$output" == *"git:clone --single-branch --depth 1 --branch add-copilot-cli-support https://github.com/garrytan/gstack.git $gstack_dir"* ]]
    [[ "$output" == *"bash:-c cd '$gstack_dir' && ./setup --host codex --quiet"* ]]
    [[ "$output" == *"gstack installed (--host codex --quiet)."* ]]
}
