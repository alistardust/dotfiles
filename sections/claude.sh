# shellcheck shell=bash
# Section: claude
# shellcheck disable=SC2088,SC2015

# -- 14. Claude Code -----------------------------------------------------------

section_claude() {
    log "Setting up Claude Code..."

    if command_exists claude; then
        ok "Claude Code already installed."
    else
        case "$OS" in
            macos|linux|wsl)
                if [[ "$DRY_RUN" == "true" ]]; then
                    printf '\e[2;37m  [dry] install Claude Code via fetch_and_run\e[0m\n'
                else
                    fetch_and_run "https://claude.ai/install.sh"
                fi
                ;;
            *)
                warn "Unsupported OS. Install manually: https://docs.anthropic.com/en/docs/claude-code/getting-started"
                return 1
                ;;
        esac
    fi

    local claude_dir="$HOME/.claude"
    local claude_global="${claude_dir}/CLAUDE.md"
    run mkdir -p "$claude_dir"

    if [[ -f "$claude_global" ]]; then
        ok "Global Claude Code instructions already exist at ${claude_global}."
    else
        log "Writing global Claude Code instructions..."
        local claude_src="${SCRIPT_DIR}/configs/claude-instructions.md"
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] copy %s to %s\e[0m\n' "$claude_src" "$claude_global"
        else
            cp "$claude_src" "$claude_global"
        fi
        ok "Global Claude Code instructions written to ${claude_global}."
    fi

    # gstack — virtual engineering team for Claude Code
    local gstack_dir="$HOME/.claude/skills/gstack"
    if [[ -d "$gstack_dir" ]]; then
        ok "gstack already installed at ${gstack_dir}."
    else
        ensure_bun || return 1
        log "Installing gstack..."
        run git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git "$gstack_dir"
        if [[ "$DRY_RUN" != "true" ]]; then
            bash -c "cd '$gstack_dir' && ./setup --quiet"
        fi
        ok "gstack installed at ${gstack_dir}."
    fi

    ok "Claude Code configured."
    log "To authenticate, run: claude"
    log "To install Superpowers, run inside a Claude Code session:"
    printf '    /plugin install superpowers@claude-plugins-official --global\n'
}

# -- 15. OpenAI Codex CLI (ChatGPT CLI) ---------------------------------------

ensure_bun() {
    local bun_bin="$HOME/.bun/bin/bun"
    if command_exists bun || [[ -x "$bun_bin" ]]; then
        ok "bun already installed: $(bun --version 2>/dev/null || "$bun_bin" --version)"
        return 0
    fi

    log "Installing Bun..."
    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] install Bun via fetch_and_run\e[0m\n'
        return 0
    fi

    fetch_and_run "https://bun.sh/install"

    command_exists bun || [[ -x "$bun_bin" ]] || { warn "bun not found after install"; return 1; }
    export PATH="$HOME/.bun/bin:$PATH"
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_claude() {
    command_exists claude               && pass "Claude Code installed"                         || fail "Claude Code not installed"
    if command_exists claude; then
        claude --version &>/dev/null    && pass "claude --version works"                       || fail "claude --version failed"
    fi
    [[ -f "$HOME/.claude/CLAUDE.md" ]]  && pass "Claude Code instructions written"             || fail "Claude Code instructions missing"
    { command_exists bun || [[ -x "$HOME/.bun/bin/bun" ]]; } \
                                        && pass "bun installed (gstack dependency)"            || fail "bun not installed (required by gstack)"
    [[ -d "$HOME/.claude/skills/gstack" ]] \
                                        && pass "gstack installed"                             || fail "gstack not installed"
}
