# shellcheck shell=bash
# Section: tmux
# shellcheck disable=SC2088,SC2015

# -- 4. tmux -------------------------------------------------------------------

section_tmux() {
    log "Setting up tmux..."
    if [[ ! -d "$HOME/.tmux" ]]; then
        run git clone "$(git_url git@github.com:gpakosz/.tmux.git)" "$HOME/.tmux"
    fi
    # Per gpakosz/.tmux instructions: symlink main conf, copy local conf
    run ln -sf "$HOME/.tmux/.tmux.conf" "$HOME/.tmux.conf"
    if [[ ! -f "$HOME/.tmux.conf.local" ]]; then
        run cp "$HOME/.tmux/.tmux.conf.local" "$HOME/.tmux.conf.local"
    fi

    local conf="$HOME/.tmux.conf.local"

    # Enable Powerline/Nerd Font separators (idempotent: skip if already applied).
    # Two-pass sed: first comment out the plain/empty separator lines that ship in
    # upstream, then uncomment the \uE0Bx lines that upstream ships but leaves
    # commented. Uses GNU sed (-i without backup suffix) which is guaranteed in
    # PATH on macOS because gnu-sed is in brew_packages.txt and gnubin is prepended
    # to PATH before this section runs.
    if ! grep -q "uE0B0" "$conf" || grep -q '^tmux_conf_theme_left_separator_main=""' "$conf"; then
        run sed -i \
            -e 's@^tmux_conf_theme_left_separator_main=""$@#tmux_conf_theme_left_separator_main=""@' \
            -e 's@^tmux_conf_theme_left_separator_sub="|"$@#tmux_conf_theme_left_separator_sub="|"@' \
            -e 's@^tmux_conf_theme_right_separator_main=""$@#tmux_conf_theme_right_separator_main=""@' \
            -e 's@^tmux_conf_theme_right_separator_sub="|"$@#tmux_conf_theme_right_separator_sub="|"@' \
            "$conf"
        run sed -i \
            -e "s@^#\(tmux_conf_theme_left_separator_main='\\\\uE0B0'.*\)@\1@" \
            -e "s@^#\(tmux_conf_theme_left_separator_sub='\\\\uE0B1'.*\)@\1@" \
            -e "s@^#\(tmux_conf_theme_right_separator_main='\\\\uE0B2'.*\)@\1@" \
            -e "s@^#\(tmux_conf_theme_right_separator_sub='\\\\uE0B3'.*\)@\1@" \
            "$conf"
    fi

    # Use C-a as sole prefix; unbind C-b so it passes through to remote/nested
    # tmux sessions which reliably use C-b.
    if ! grep -q "^set -g prefix C-a" "$conf"; then
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] append prefix config to %s\e[0m\n' "$conf"
        else
            cat >> "$conf" << 'TMUX_PREFIX'

# Use C-a as the sole prefix; C-b is freed for remote/nested tmux sessions
set -gu prefix2
unbind C-b
set -g prefix C-a
bind C-a send-prefix
TMUX_PREFIX
        fi
    fi

    # Enable mouse mode by uncommenting the line the framework ships commented out.
    # Falls back to appending if the template line is absent (e.g. older installs).
    # The framework's bind-m toggle (<prefix>+m) and the #{mouse} status indicator
    # both work without any additional config once this is set.
    if ! grep -q "^set -g mouse on" "$conf"; then
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] enable mouse mode in %s\e[0m\n' "$conf"
        else
            sed -i 's/^#set -g mouse on$/set -g mouse on/' "$conf"
            # If the commented template line wasn't present, append directly.
            grep -q "^set -g mouse on" "$conf" || echo 'set -g mouse on' >> "$conf"
        fi
    fi

    # Window navigation bindings + manual focus-events toggle (C-a F)
    # The toggle is a fallback for tools outside the ssh/aws wrappers.
    if ! grep -q "bind a last-window" "$conf"; then
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] append bindings to %s\e[0m\n' "$conf"
        else
            cat >> "$conf" << 'TMUX_BINDINGS'

bind a last-window
bind n next-window
# Toggle focus-events on/off with <prefix>+F (fallback for non-ssh flows)
bind F run-shell "tmux set focus-events $(tmux show -gv focus-events | grep -q on && echo off || echo on) && tmux display-message 'focus-events: #{focus-events}'"
TMUX_BINDINGS
        fi
    fi

    # Enable pane border titles (works with tmux-rename hook for pane context)
    if grep -q 'tmux_conf_theme_pane_border_title=' "$conf" 2>/dev/null; then
        # Fork detected: use the framework variable
        if grep -q '^tmux_conf_theme_pane_border_title="disabled"' "$conf"; then
            run sed -i 's/^tmux_conf_theme_pane_border_title="disabled"$/tmux_conf_theme_pane_border_title="top"/' "$conf"
        fi
    else
        # Upstream Oh my tmux!: append raw tmux settings
        if ! grep -q "pane-border-format" "$conf"; then
            if [[ "$DRY_RUN" == "true" ]]; then
                printf '\e[2;37m  [dry] append pane border config to %s\e[0m\n' "$conf"
            else
                cat >> "$conf" << 'TMUX_PANE_BORDERS'

# pane border titles (shows pane title above each pane)
set -g pane-border-format " #{pane_title} " #!important
set -g pane-border-status top #!important
TMUX_PANE_BORDERS
            fi
        fi
    fi
    ok "tmux configured."
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_tmux() {
    [[ -d "$HOME/.tmux" ]]             && pass "~/.tmux cloned"                    || fail "~/.tmux not cloned"
    [[ -L "$HOME/.tmux.conf" ]]        && pass "~/.tmux.conf is a symlink"         || fail "~/.tmux.conf is not a symlink"
    [[ -f "$HOME/.tmux.conf.local" ]]  && pass "~/.tmux.conf.local exists"         || fail "~/.tmux.conf.local missing"
    local conf="$HOME/.tmux.conf.local"
    grep -q "uE0B0"               "$conf" 2>/dev/null && pass "Powerline separators configured"  || fail "Powerline separators not configured"
    grep -q "^set -g prefix C-a"  "$conf" 2>/dev/null && pass "C-a prefix configured"           || fail "C-a prefix not configured"
    grep -q "^unbind C-b"         "$conf" 2>/dev/null && pass "C-b unbound"                     || fail "C-b not unbound"
    grep -q "^bind a last-window" "$conf" 2>/dev/null && pass "bind a last-window set"          || fail "bind a last-window not set"
    grep -q "^bind n next-window" "$conf" 2>/dev/null && pass "bind n next-window set"          || fail "bind n next-window not set"
    grep -q "^bind F "            "$conf" 2>/dev/null && pass "bind F focus-events toggle set"  || fail "bind F focus-events toggle not set"
    grep -q "^set -g mouse on"    "$conf" 2>/dev/null && pass "mouse mode enabled"              || fail "mouse mode not enabled"
    { grep -q "pane-border-format" "$conf" || grep -q 'pane_border_title="top"' "$conf"; } \
        2>/dev/null && pass "pane border titles configured" || fail "pane border titles not configured"
}
