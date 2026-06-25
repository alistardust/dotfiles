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
    local claude_src="${SCRIPT_DIR}/configs/claude-instructions.md"
    install_instructions "$claude_dir" "$claude_global" "$claude_src" "Claude Code"

    # Install local skills from this repo
    local skills_dir="${claude_dir}/skills"
    _install_local_skills "$skills_dir"
    ok "All local skills installed to ~/.claude/skills/"

    # gstack — virtual engineering team for Claude Code
    local gstack_dir="$HOME/.claude/skills/gstack"
    install_gstack "$gstack_dir" "--quiet"

    ok "Claude Code configured."
    log "To authenticate, run: claude"
    log "To install Superpowers, run inside a Claude Code session:"
    printf '    /plugin install superpowers@claude-plugins-official --global\n'
}

# -- 15. OpenAI Codex CLI (ChatGPT CLI) ---------------------------------------

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
