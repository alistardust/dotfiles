# shellcheck shell=bash
# Section: packages
# shellcheck disable=SC2088,SC2015

# -- 1. Packages ---------------------------------------------------------------

GH_APT_KEY_URL="https://cli.github.com/packages/githubcli-archive-keyring.gpg"
GH_RPM_REPO_URL="https://cli.github.com/packages/rpm/gh-cli.repo"

install_packages_macos() {
    if ! command_exists brew; then
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] install Homebrew\e[0m\n'
        else
            log "Installing Homebrew..."
            fetch_and_run "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
        fi
    fi
    if [[ -x /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -x /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    run brew update
    while IFS= read -r pkg || [[ -n "$pkg" ]]; do
        [[ -z "$pkg" || "$pkg" == \#* ]] && continue
        pkg_name="${pkg%% *}"
        if brew list --formula "$pkg_name" &>/dev/null \
           || brew list --cask "$pkg_name" &>/dev/null; then
            ok "Already installed: $pkg_name"
        else
            run brew install "$pkg_name" < /dev/null \
                || warn "brew install failed: $pkg_name (continuing)"
        fi
    done < "${SCRIPT_DIR}/brew_packages.txt"
    link_node_macos
}

# node@22 is keg-only, so brew install alone leaves it off PATH.
link_node_macos() {
    local node_link="${HOMEBREW_PREFIX:-/opt/homebrew}/bin/node"
    if [[ "$(readlink "$node_link" 2>/dev/null)" == *"/node@22/"* ]]; then
        ok "node@22 already linked"
    else
        run brew link --force node@22 \
            || warn "brew link failed: node@22 (continuing)"
    fi
}

install_packages_debian() {
    sudo apt-get update -y
    # shellcheck disable=SC2046
    run sudo apt-get install -y $(grep -v '^\s*#' "${SCRIPT_DIR}/apt-packages.txt" | xargs)
    install_gh_debian || warn "gh install failed (continuing)"
}

install_packages_rhel() {
    local mgr; command_exists dnf && mgr="dnf" || mgr="yum"
    # shellcheck disable=SC2046
    run sudo "$mgr" install -y $(grep -v '^\s*#' "${SCRIPT_DIR}/dnf-packages.txt" | xargs)
    install_gh_rhel "$mgr" || warn "gh install failed (continuing)"
}

# gh is installed from GitHub's own repo rather than the package lists: distro
# builds lag or are missing, and a missing name would fail the whole batch.
# set -e does not apply inside these (they run under ||), so check each step.
install_gh_debian() {
    local keyring="/etc/apt/keyrings/githubcli-archive-keyring.gpg"
    local list="/etc/apt/sources.list.d/github-cli.list"
    local key_file arch
    if [[ -f "$list" ]]; then
        ok "GitHub CLI apt repository already configured"
    elif [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] write %s and %s\e[0m\n' "$keyring" "$list"
    else
        key_file="$(mktemp)" || return 1
        register_cleanup "$key_file"
        curl -fsSL -o "$key_file" "$GH_APT_KEY_URL" || return 1
        sudo mkdir -p -m 755 /etc/apt/keyrings || return 1
        sudo install -m 644 "$key_file" "$keyring" || return 1
        arch="$(dpkg --print-architecture)" || return 1
        # The list file is the idempotency guard, so write it only after the key.
        printf 'deb [arch=%s signed-by=%s] https://cli.github.com/packages stable main\n' \
            "$arch" "$keyring" | sudo tee "$list" >/dev/null || return 1
        sudo apt-get update -y || return 1
    fi
    run sudo apt-get install -y gh
}

install_gh_rhel() {
    local mgr="$1" repo="/etc/yum.repos.d/gh-cli.repo" repo_file
    if [[ -f "$repo" ]]; then
        ok "GitHub CLI yum repository already configured"
    elif [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] write %s\e[0m\n' "$repo"
    else
        # Same file "dnf config-manager" would fetch, without its dnf4/dnf5 split.
        repo_file="$(mktemp)" || return 1
        register_cleanup "$repo_file"
        curl -fsSL -o "$repo_file" "$GH_RPM_REPO_URL" || return 1
        sudo install -m 644 "$repo_file" "$repo" || return 1
    fi
    run sudo "$mgr" install -y gh
}

install_packages_arch() {
    # shellcheck disable=SC2046
    run sudo pacman -S --needed --noconfirm $(grep -v '^\s*#' "${SCRIPT_DIR}/pacman-packages.txt" | xargs)
}

section_packages() {
    log "Installing packages..."
    case "$OS" in
        macos) install_packages_macos ;;
        linux|wsl)
            case "$(detect_linux_distro)" in
                debian)  install_packages_debian ;;
                rhel*)   install_packages_rhel ;;
                arch)    install_packages_arch ;;
                *) warn "Unsupported distro  - skipping package install" ;;
            esac ;;
        *) warn "Unsupported OS  - skipping package install" ;;
    esac
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_packages() {
    case "$OS" in
        macos)
            command_exists brew \
                && pass "Homebrew installed" \
                || fail "Homebrew not installed"
            command_exists node && [[ "$(node --version)" == v22.* ]] \
                && pass "Node.js 22 on PATH" \
                || fail "Node.js 22 not on PATH" ;;
        linux|wsl)
            case "$(detect_linux_distro)" in
                debian) command_exists apt-get && pass "apt-get available" || fail "apt-get not available" ;;
                rhel*)  { command_exists dnf || command_exists yum; } && pass "dnf/yum available" || fail "no package manager found" ;;
                arch)   command_exists pacman && pass "pacman available" || fail "pacman not available" ;;
                *)      skip_check "unknown distro  - cannot verify packages" ;;
            esac ;;
        *) skip_check "unknown OS  - cannot verify packages" ;;
    esac
    command_exists gh \
        && pass "gh installed" \
        || fail "gh not installed"
}
