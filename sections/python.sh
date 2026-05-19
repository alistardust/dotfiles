# shellcheck shell=bash
# Section: python
# shellcheck disable=SC2088,SC2015

# -- 9. Python (uv + uv-virtualenvwrapper + base virtualenv) ------------------

append_local_bin_hook() {
    local target="$1"
    [[ -f "$target" ]] || touch "$target"
    if grep -q "# >>> dotfiles local bin <<<" "$target" 2>/dev/null; then
        return 0
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] append local bin hook to %s\e[0m\n' "$target"
        return 0
    fi

    cat >> "$target" << 'LOCAL_BIN_HOOK'

# >>> dotfiles local bin <<<
export PATH="$HOME/.local/bin:$PATH"
[ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"
# <<< dotfiles local bin <<<
LOCAL_BIN_HOOK
}

ensure_local_bin_shell_path() {
    export PATH="$HOME/.local/bin:$PATH"
    append_local_bin_hook "$HOME/.profile"
    append_local_bin_hook "$HOME/.zprofile"
}

ensure_uv() {
    if command_exists uv; then
        ok "uv already installed: $(uv --version)"
        ensure_local_bin_shell_path
        return 0
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] install uv via curl | sh\e[0m\n'
        ensure_local_bin_shell_path
        return 0
    fi

    fetch_and_run "https://astral.sh/uv/install.sh"
    ensure_local_bin_shell_path

    command_exists uv || [[ -x "$HOME/.local/bin/uv" ]] || { warn "uv not found after install"; return 1; }
}

section_python() {
    log "Setting up Python (uv + uv-virtualenvwrapper + base virtualenv)..."

    ensure_uv || return 1

    # uv-virtualenvwrapper provides a shell script; install as a uv tool
    if [[ ! -f "$HOME/.local/bin/uv-virtualenvwrapper.sh" ]]; then
        run uv tool install uv-virtualenvwrapper
    else
        ok "uv-virtualenvwrapper already installed."
    fi

    # Create the base virtualenv (acts as a system-level scripting environment)
    local venv_home="${WORKON_HOME:-$HOME/.venvs}"
    run mkdir -p "$venv_home"
    local base_venv="$venv_home/base"
    if [[ ! -d "$base_venv" ]]; then
        run uv venv "$base_venv"
        ok "Created base virtualenv at $base_venv"
    else
        ok "Base virtualenv already exists at $base_venv"
    fi

    log "Installing packages into base virtualenv..."
    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] uv pip install packages into %s\e[0m\n' "$base_venv"
    else
        uv pip install --python "$base_venv/bin/python" \
            `# REPL / debugging` \
            ipython ipdb pexpect \
            `# HTTP / networking` \
            requests httpx paramiko fabric dnspython \
            `# CLI / TUI` \
            click typer rich tqdm tabulate prettytable \
            `# Data / config parsing` \
            pydantic python-dotenv PyYAML jinja2 \
            lxml "beautifulsoup4[lxml]" jsonpath-ng \
            `# PDF / document generation` \
            reportlab fpdf2 weasyprint pypdf \
            `# AWS / cloud` \
            boto3 \
            `# Kubernetes` \
            kubernetes \
            `# System utilities` \
            psutil sh watchdog \
            `# Database clients` \
            psycopg2-binary pymysql \
            `# Security / crypto` \
            cryptography \
            `# Monitoring / observability` \
            prometheus-client
    fi

    ok "Python base virtualenv configured."
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_python() {
    local uv_bin="${HOME}/.local/bin/uv"
    { command_exists uv || [[ -x "$uv_bin" ]]; } \
                                        && pass "uv installed"                                 || fail "uv not installed"
    [[ -f "$HOME/.local/bin/uv-virtualenvwrapper.sh" ]] \
                                        && pass "uv-virtualenvwrapper.sh present"              || fail "uv-virtualenvwrapper.sh missing"
    local venv="${WORKON_HOME:-$HOME/.venvs}/base"
    [[ -d "$venv" ]]                   && pass "base virtualenv exists"                        || { fail "base virtualenv missing ($venv)"; return; }
    [[ -x "$venv/bin/python" ]]        && pass "base venv python executable"                  || fail "base venv python not executable"
    local uv_bin="${HOME}/.local/bin/uv"
    local pkg
    for pkg in requests boto3 kubernetes rich ipython weasyprint cryptography prometheus_client paramiko; do
        "$uv_bin" pip show "$pkg" --python "$venv/bin/python" &>/dev/null \
                                        && pass "package: $pkg"                                || fail "package missing: $pkg"
    done
}
