# shellcheck shell=bash
# Section: alacritty
# shellcheck disable=SC2088,SC2015

# -- 7. Alacritty -------------------------------------------------------------

_alacritty_install_mac() {
    command_exists brew || fetch_and_run "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
    if [[ -x /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [[ -x /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    run brew install --cask alacritty
}

_alacritty_install_debian() {
    sudo apt-get update -y
    # alacritty is available via snap on Ubuntu; fall back to cargo build on Debian
    if command_exists snap; then
        run sudo snap install alacritty --classic
    else
        warn "alacritty not in default apt repos. Install via cargo or your distro's method."
    fi
}

_alacritty_install_rhel() {
    local m; command_exists dnf && m=dnf || m=yum
    # alacritty is not in standard RHEL/Fedora/CentOS repos; use flatpak if available
    if command_exists flatpak; then
        run flatpak install --user -y flathub io.github.alacritty.Alacritty
    elif command_exists cargo; then
        warn "alacritty not in dnf repos. Building from source via cargo (slow)..."
        run sudo "$m" install -y cmake freetype-devel fontconfig-devel libxcb-devel \
            libxkbcommon-devel g++
        run cargo install alacritty
    else
        warn "alacritty not in dnf repos and flatpak/cargo not available."
        warn "Install flatpak first: sudo $m install -y flatpak && flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo"
        return 1
    fi
}

_alacritty_install_arch() {
    run sudo pacman -S --needed --noconfirm alacritty
}

section_alacritty() {
    log "Setting up Alacritty..."

    if command_exists alacritty; then
        ok "Alacritty already installed."
    else
        case "$OS" in
            macos)    _alacritty_install_mac ;;
            linux|wsl)
                case "$(detect_linux_distro)" in
                    debian)  _alacritty_install_debian ;;
                    rhel*)   _alacritty_install_rhel ;;
                    arch)    _alacritty_install_arch ;;
                    *) warn "Unsupported distro  - install alacritty manually." ;;
                esac ;;
            *) warn "Unsupported OS  - install alacritty manually." ;;
        esac
    fi

    # Bail out early if alacritty still isn't available (install step warned already)
    if ! command_exists alacritty; then
        warn "alacritty not found after install attempt  - skipping man page, completions, and terminfo"
        return 0
    fi

    # Man page
    local man_path="/usr/local/share/man/man1"
    if command_exists man && man -w alacritty &>/dev/null; then
        ok "Alacritty man page already available."
    elif [[ ! -f "${man_path}/alacritty.1.gz" ]]; then
        warn "Alacritty man page is not installed locally; skipping manual install (upstream path changed)."
    fi

    # Zsh completions
    local zsh_fn_dir="${ZDOTDIR:-$HOME}/.zsh_functions"
    if [[ ! -f "${zsh_fn_dir}/_alacritty" ]]; then
        run mkdir -p "$zsh_fn_dir"
        if ! run curl -fsSL -o "${zsh_fn_dir}/_alacritty" \
            https://raw.githubusercontent.com/alacritty/alacritty/master/extra/completions/_alacritty; then
            warn "Failed to download Alacritty zsh completions  - skipping"
        fi
    fi

    # terminfo  - requires tic (ncurses); present on macOS and most Linux distros
    if infocmp alacritty &>/dev/null; then
        ok "Alacritty terminfo already available."
    elif command_exists tic; then
        local terminfo_tmp
        terminfo_tmp="$(mktemp)"
        register_cleanup "$terminfo_tmp"
        if run curl -fsSL -o "$terminfo_tmp" \
            https://raw.githubusercontent.com/alacritty/alacritty/master/extra/alacritty.info; then
            run sudo tic -xe alacritty,alacritty-direct "$terminfo_tmp"
        else
            warn "Failed to download Alacritty terminfo  - skipping"
        fi
        rm -f "$terminfo_tmp"
    else
        warn "tic not found  - skipping alacritty terminfo install (run: sudo tic -xe alacritty,alacritty-direct alacritty.info)"
    fi

    # Symlink config -- macOS uses alacritty.toml (font size 13.5);
    # Linux/WSL uses alacritty-linux.toml (font size 10.5 for HiDPI displays).
    run mkdir -p "$HOME/.config/alacritty"
    local toml_src
    if [[ "$OS" == "macos" ]]; then
        toml_src="${SCRIPT_DIR}/terminal_configs/alacritty.toml"
    else
        toml_src="${SCRIPT_DIR}/terminal_configs/alacritty-linux.toml"
    fi
    run ln -sf "$toml_src" "$HOME/.config/alacritty/alacritty.toml"

    ok "Alacritty configured."
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_alacritty() {
    { command_exists alacritty || [[ -d "/Applications/Alacritty.app" ]]; } \
                                        && pass "alacritty installed"                           || fail "alacritty not installed"
    local cfg="$HOME/.config/alacritty/alacritty.toml"
    [[ -L "$cfg" ]]                    && pass "alacritty.toml symlinked"                      || fail "alacritty.toml not symlinked"
    local target; target="$(readlink "$cfg" 2>/dev/null || true)"
    [[ "$target" == *"terminal_configs/alacritty.toml" || "$target" == *"terminal_configs/alacritty-linux.toml" ]] \
                                        && pass "alacritty.toml points to dotfiles ($target)"  || fail "alacritty.toml symlink target unexpected: $target"
}
