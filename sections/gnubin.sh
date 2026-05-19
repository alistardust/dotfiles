# shellcheck shell=bash
# Section: gnubin
# shellcheck disable=SC2088,SC2015

# -- 2. GNU tools (macOS only) -------------------------------------------------

section_gnubin() {
    if [[ "$OS" != "macos" ]]; then
        warn "gnubin is macOS-only, skipping on $OS."
        return
    fi
    log "Symlinking GNU tools into ~/.gnubin..."
    run mkdir -p "$HOME/.gnubin"
    local brew_prefix
    brew_prefix="$(brew --prefix)"
    for dir in "${brew_prefix}/opt"/*/libexec/gnubin; do
        [[ -d "$dir" ]] || continue
        while IFS= read -r -d '' bin; do
            run ln -sf "$bin" "$HOME/.gnubin/$(basename "$bin")"
        done < <(find "$dir" -maxdepth 1 -type f -print0)
    done
    ok "GNU tools linked in ~/.gnubin"
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_gnubin() {
    if [[ "$OS" != "macos" ]]; then skip_check "gnubin is macOS-only"; return; fi
    [[ -d "$HOME/.gnubin" ]]        && pass "~/.gnubin directory exists"       || fail "~/.gnubin directory missing"
    [[ -L "$HOME/.gnubin/sed" ]]    && pass "GNU sed linked in ~/.gnubin"      || fail "GNU sed not linked in ~/.gnubin"
    [[ -L "$HOME/.gnubin/find" ]]   && pass "GNU find linked in ~/.gnubin"     || fail "GNU find not linked in ~/.gnubin"
}
