# shellcheck shell=bash
# Section: chatgpt
# shellcheck disable=SC2088,SC2015,SC2010

# -- 15. OpenAI Codex CLI (ChatGPT CLI) ---------------------------------------

ensure_npm() {
    if command_exists npm; then
        ok "npm already installed: $(npm --version)"
        return 0
    fi

    log "Installing Node.js + npm for OpenAI Codex CLI..."
    case "$OS" in
        macos)
            if ! command_exists brew; then
                if [[ "$DRY_RUN" == "true" ]]; then
                    printf '\e[2;37m  [dry] install Homebrew\e[0m\n'
                else
                    fetch_and_run "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
                fi
            fi
            if [[ -x /opt/homebrew/bin/brew ]]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            elif [[ -x /usr/local/bin/brew ]]; then
                eval "$(/usr/local/bin/brew shellenv)"
            fi
            run brew install node
            ;;
        linux|wsl)
            case "$(detect_linux_distro)" in
                debian)
                    run sudo apt-get update -y
                    run sudo apt-get install -y nodejs npm
                    ;;
                rhel*)
                    local mgr; command_exists dnf && mgr="dnf" || mgr="yum"
                    run sudo "$mgr" install -y nodejs npm
                    ;;
                arch)
                    run sudo pacman -S --needed --noconfirm nodejs npm
                    ;;
                *)
                    warn "Unsupported distro  - install Node.js and npm manually for Codex CLI"
                    return 1
                    ;;
            esac
            ;;
        *)
            warn "Unsupported OS  - install Node.js and npm manually for Codex CLI"
            return 1
            ;;
    esac

    if [[ "$DRY_RUN" == "true" ]]; then
        ok "Node.js + npm install queued."
        return 0
    fi

    if ! command_exists npm; then
        warn "npm not found after install attempt"
        return 1
    fi
}

install_npm_global_package() {
    local package="$1"
    local prefix
    local brew_prefix=""
    prefix="$(npm prefix -g 2>/dev/null || true)"
    if [[ "$OS" == "macos" ]] && command_exists brew; then
        brew_prefix="$(brew --prefix 2>/dev/null || true)"
    fi

    if [[ "$prefix" == "$HOME"* ]] || [[ -n "$brew_prefix" && "$prefix" == "$brew_prefix"* ]]; then
        run npm i -g "$package"
    else
        run sudo npm i -g "$package"
    fi
}

section_chatgpt() {
    log "Setting up OpenAI Codex CLI (ChatGPT CLI)..."

    ensure_npm || return 1

    if command_exists codex; then
        ok "OpenAI Codex CLI already installed."
    else
        install_npm_global_package @openai/codex
    fi

    local agents_dir="$HOME/.codex"
    local agents_file="${agents_dir}/AGENTS.md"
    local codex_src="${SCRIPT_DIR}/configs/codex-instructions.md"
    install_instructions "$agents_dir" "$agents_file" "$codex_src" "Codex"

    # gstack — register skills with Codex (clone first if not yet present)
    local gstack_dir="$HOME/.claude/skills/gstack"
    if [[ -d "$gstack_dir" ]]; then
        log "Registering gstack with Codex..."
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] cd %s && ./setup --host codex --quiet\e[0m\n' "$gstack_dir"
        else
            bash -c "cd '$gstack_dir' && ./setup --host codex --quiet"
        fi
        ok "gstack registered with Codex."
    else
        install_gstack "$gstack_dir" "--host codex --quiet"
    fi

    ok "OpenAI Codex CLI configured."
    log "To authenticate, run: codex"
    log "To install Superpowers, run inside a Codex session: /plugins → search 'superpowers'"
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_chatgpt() {
    command_exists npm                  && pass "npm installed"                                || fail "npm not installed"
    command_exists codex                && pass "OpenAI Codex CLI installed"                   || fail "OpenAI Codex CLI not installed"
    if command_exists codex; then
        codex --version &>/dev/null     && pass "codex --version works"                        || fail "codex --version failed"
    fi
    [[ -f "$HOME/.codex/AGENTS.md" ]]   && pass "Codex instructions written"                  || fail "Codex instructions missing"
    { command_exists bun || [[ -x "$HOME/.bun/bin/bun" ]]; } \
                                        && pass "bun installed (gstack dependency)"            || fail "bun not installed (required by gstack)"
    { [[ -d "$HOME/.codex/skills" ]] && ls "$HOME/.codex/skills/" 2>/dev/null | grep -q gstack; } \
                                        && pass "gstack registered with Codex"                || fail "gstack not registered with Codex"
}
