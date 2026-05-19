# shellcheck shell=bash
# Section: vim
# shellcheck disable=SC2088,SC2015

# -- 6. Vim --------------------------------------------------------------------

section_vim() {
    log "Setting up Vim..."
    if [[ ! -d "$HOME/.vim" ]]; then
        run git clone git@github.com:alistardust/.vim.git "$HOME/.vim"
    fi
    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] checkout Divine branch and update submodules in ~/.vim\e[0m\n'
    else
        (cd "$HOME/.vim" \
            && { git symbolic-ref --short HEAD 2>/dev/null | grep -qx "Divine" || git checkout Divine; } \
            && git submodule update --init --recursive)
    fi
    run ln -sf "$HOME/.vim/.vimrc" "$HOME/.vimrc"
    # .vimrc.local is machine-specific (WSL patches it at runtime); copy rather than
    # symlink so changes don't propagate back into the .vim git repo.
    if [[ ! -f "$HOME/.vimrc.local" ]]; then
        run cp "$HOME/.vim/.vimrc.local" "$HOME/.vimrc.local" 2>/dev/null || run touch "$HOME/.vimrc.local"
    fi
    ok "Vim configured."
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_vim() {
    [[ -d "$HOME/.vim" ]]               && pass "~/.vim cloned"                                || fail "~/.vim not cloned"
    [[ -L "$HOME/.vimrc" ]]             && pass "~/.vimrc symlinked"                           || fail "~/.vimrc not symlinked"
    [[ -f "$HOME/.vimrc.local" ]]       && pass "~/.vimrc.local exists"                        || fail "~/.vimrc.local missing"
    local branch
    branch="$(cd "$HOME/.vim" 2>/dev/null && git symbolic-ref --short HEAD 2>/dev/null || true)"
    [[ "$branch" == "Divine" ]]         && pass "~/.vim on Divine branch"                      || fail "~/.vim not on Divine branch (got: ${branch:-none})"
    local uninit
    uninit="$(cd "$HOME/.vim" 2>/dev/null && { git submodule status 2>/dev/null | { grep '^-' || true; } | wc -l | tr -d ' '; } || echo 0)"
    [[ "$uninit" -eq 0 ]]               && pass "All vim submodules initialized"               || fail "$uninit vim submodule(s) not initialized"
}
