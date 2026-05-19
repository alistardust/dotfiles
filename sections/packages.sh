# shellcheck shell=bash
# Section: packages
# shellcheck disable=SC2088,SC2015

# -- 1. Packages ---------------------------------------------------------------

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
            run brew install "$pkg_name"
        fi
    done < "${SCRIPT_DIR}/brew_packages.txt"
}

install_packages_debian() {
    sudo apt-get update -y
    # shellcheck disable=SC2046
    run sudo apt-get install -y $(grep -v '^\s*#' "${SCRIPT_DIR}/apt-packages.txt" | xargs)
}

install_packages_rhel() {
    local mgr; command_exists dnf && mgr="dnf" || mgr="yum"
    # shellcheck disable=SC2046
    run sudo "$mgr" install -y $(grep -v '^\s*#' "${SCRIPT_DIR}/dnf-packages.txt" | xargs)
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
                || fail "Homebrew not installed" ;;
        linux|wsl)
            case "$(detect_linux_distro)" in
                debian) command_exists apt-get && pass "apt-get available" || fail "apt-get not available" ;;
                rhel*)  { command_exists dnf || command_exists yum; } && pass "dnf/yum available" || fail "no package manager found" ;;
                arch)   command_exists pacman && pass "pacman available" || fail "pacman not available" ;;
                *)      skip_check "unknown distro  - cannot verify packages" ;;
            esac ;;
        *) skip_check "unknown OS  - cannot verify packages" ;;
    esac
}
