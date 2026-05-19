# shellcheck shell=bash
# Section: keyd
# shellcheck disable=SC2088,SC2015

# -- 10. keyd (Linux key-remapping daemon) -------------------------------------

section_keyd() {
    if [[ "$OS" != "linux" ]]; then
        log "keyd: skipping (Linux only)"
        return 0
    fi
    log "Setting up keyd (Mac-like key remapping)..."

    if ! command_exists keyd; then
        case "$(detect_linux_distro)" in
            arch)   run sudo pacman -S --noconfirm keyd ;;
            debian) run sudo apt-get install -y keyd ;;
            rhel*)  warn "keyd not in default RHEL repos — install manually." ; return 0 ;;
            *)      warn "Unknown distro — install keyd manually." ; return 0 ;;
        esac
    else
        ok "keyd already installed."
    fi

    # Deploy config (needs root — copy rather than symlink so keyd's root daemon can read it)
    local src="${SCRIPT_DIR}/configs/keyd.conf"
    local dst="/etc/keyd/default.conf"
    if [[ ! -f "$src" ]]; then
        warn "configs/keyd.conf not found in dotfiles — skipping keyd config deploy"
    elif ! diff -q "$src" "$dst" &>/dev/null; then
        run sudo mkdir -p /etc/keyd
        run sudo cp "$src" "$dst"
        ok "keyd config deployed."
    else
        ok "keyd config already up to date."
    fi

    run sudo systemctl enable --now keyd
    run sudo usermod -aG keyd "$(whoami)"
    ok "keyd active. Re-login for group membership to take effect."
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_keyd() {
    if [[ "$OS" != "linux" ]]; then skip_check "keyd section not applicable on $OS"; return; fi
    command_exists keyd                && pass "keyd installed"                                 || fail "keyd not installed"
    [[ -f /etc/keyd/default.conf ]]   && pass "/etc/keyd/default.conf present"                 || fail "/etc/keyd/default.conf missing"
    grep -q '\[meta\]' /etc/keyd/default.conf 2>/dev/null \
                                       && pass "keyd meta layer configured"                     || fail "keyd [meta] layer not found in config"
    systemctl is-active --quiet keyd  && pass "keyd service active"                            || fail "keyd service not active"
    id -nG 2>/dev/null | grep -qw keyd \
                                       && pass "user in keyd group"                             || fail "user not in keyd group (re-login required)"
}
