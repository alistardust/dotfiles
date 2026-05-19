# shellcheck shell=bash
# Section: google_workspace
# shellcheck disable=SC2088,SC2015

section_google_workspace() {
    log "Setting up Google Workspace MCP (taylorwilsdon/google_workspace_mcp)..."

    ensure_uv || return 1

    if { uv tool list 2>/dev/null || "$HOME/.local/bin/uv" tool list 2>/dev/null; } \
       | grep -q '^workspace-mcp '; then
        ok "workspace-mcp already installed."
    else
        run uv tool install workspace-mcp
    fi

    ok "Google Workspace MCP installed."
    log "Post-install: create a Google Cloud OAuth 2.0 Desktop client, then set"
    log "  GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in your environment."
    log "Run: uvx workspace-mcp --tool-tier core"
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_google_workspace() {
    local uv_bin="${HOME}/.local/bin/uv"

    { command_exists uv || [[ -x "$uv_bin" ]]; } \
                                        && pass "uv installed"                                 || fail "uv not installed"
    { "$uv_bin" tool list 2>/dev/null || uv tool list 2>/dev/null; } | grep -q '^workspace-mcp ' \
                                        && pass "workspace-mcp registered as a uv tool"        || fail "workspace-mcp not registered as a uv tool"
}
