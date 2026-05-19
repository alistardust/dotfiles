# shellcheck shell=bash
# Section: fonts
# shellcheck disable=SC2088,SC2015

# -- 3. Powerline fonts --------------------------------------------------------

section_fonts() {
    log "Installing Powerline fonts..."

    # fc-list is Linux (fontconfig); on macOS check font dirs directly
    local has_fonts=false
    if command_exists fc-list && fc-list 2>/dev/null | grep -qi "powerline\|MesloLGM\|Nerd Font"; then
        has_fonts=true
    elif [[ "$OS" == "macos" ]] && \
         find ~/Library/Fonts /Library/Fonts \
              \( -name "*Powerline*" -o -name "*MesloLGM*" -o -name "*NerdFont*" \) \
              -print 2>/dev/null | grep -q .; then
        has_fonts=true
    fi

    if [[ "$has_fonts" == "true" ]]; then
        ok "Powerline/Nerd fonts already installed."
        return
    fi

    local tmp_dir
    tmp_dir="$(mktemp -d)"
    register_cleanup "$tmp_dir"

    run git clone --depth=1 "$(git_url git@github.com:powerline/fonts.git)" "$tmp_dir/fonts"
    run bash "$tmp_dir/fonts/install.sh"
    rm -rf "$tmp_dir"
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_fonts() {
    if command_exists fc-list && fc-list 2>/dev/null | grep -qi "powerline\|MesloLGM\|Nerd Font"; then
        pass "Powerline/Nerd fonts installed"
    elif [[ "$OS" == "macos" ]] && \
         find ~/Library/Fonts /Library/Fonts \
              \( -name "*Powerline*" -o -name "*MesloLGM*" -o -name "*NerdFont*" \) \
              -print 2>/dev/null | grep -q .; then
        pass "Powerline/Nerd fonts installed"
    else
        fail "No Powerline/Nerd fonts found"
    fi
}
