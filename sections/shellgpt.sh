# shellcheck shell=bash
# Section: shellgpt
# shellcheck disable=SC2088,SC2015

# -- 16. ShellGPT (unofficial open-source ChatGPT CLI) ------------------------

section_shellgpt() {
    log "Setting up ShellGPT (unofficial chat-focused CLI)..."

    ensure_uv || return 1

    if [[ -x "$HOME/.local/bin/sgpt" ]] || command_exists sgpt; then
        ok "ShellGPT already installed."
    else
        run uv tool install shell-gpt
    fi

    ok "ShellGPT configured."
    log "To use it, set OPENAI_API_KEY and run: sgpt \"hello\""
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_shellgpt() {
    local uv_bin="${HOME}/.local/bin/uv"
    local sgpt_bin="${HOME}/.local/bin/sgpt"

    { command_exists uv || [[ -x "$uv_bin" ]]; } \
                                        && pass "uv installed"                                 || fail "uv not installed"
    { command_exists sgpt || [[ -x "$sgpt_bin" ]]; } \
                                        && pass "ShellGPT installed"                           || fail "ShellGPT not installed"
    grep -q "# >>> dotfiles local bin <<<" "$HOME/.profile" 2>/dev/null \
                                        && pass "~/.profile local bin hook present"            || fail "~/.profile local bin hook missing"
    grep -q "# >>> dotfiles local bin <<<" "$HOME/.zprofile" 2>/dev/null \
                                        && pass "~/.zprofile local bin hook present"           || fail "~/.zprofile local bin hook missing"
    { "$uv_bin" tool list 2>/dev/null || uv tool list 2>/dev/null; } | grep -q '^shell-gpt ' \
                                        && pass "uv tool list includes shell-gpt"              || fail "shell-gpt not registered as a uv tool"
}
