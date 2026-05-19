# shellcheck shell=bash
# Section: auto_cpufreq
# shellcheck disable=SC2088,SC2015

# -- 11. auto-cpufreq (load-based CPU frequency scaling) -----------------------

section_auto_cpufreq() {
    if [[ "$OS" != "linux" ]] || [[ "$OS" == "wsl" ]]; then
        log "auto-cpufreq: skipping (bare-metal Linux only)"
        return 0
    fi
    log "Setting up auto-cpufreq..."

    if ! command_exists auto-cpufreq; then
        case "$(detect_linux_distro)" in
            arch)   run sudo pacman -S --noconfirm auto-cpufreq ;;
            debian) run sudo apt-get install -y auto-cpufreq ;;
            *)      warn "Unknown distro — install auto-cpufreq manually." ; return 0 ;;
        esac
    else
        ok "auto-cpufreq already installed."
    fi

    run sudo systemctl enable --now auto-cpufreq
    ok "auto-cpufreq active — CPU frequency scales automatically with load."
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_auto_cpufreq() {
    if [[ "$OS" != "linux" ]] || [[ "$OS" == "wsl" ]]; then skip_check "auto-cpufreq section not applicable on $OS"; return; fi
    command_exists auto-cpufreq           && pass "auto-cpufreq installed"                       || fail "auto-cpufreq not installed"
    systemctl is-active --quiet auto-cpufreq \
                                          && pass "auto-cpufreq service active"                  || fail "auto-cpufreq service not active"
}
