# shellcheck shell=bash
# Section: zsh
# shellcheck disable=SC2088,SC2015

# -- 5. ZSH / Oh My Zsh -------------------------------------------------------

_zsh_install_omz() {
    if [[ ! -d "$HOME/.oh-my-zsh" ]]; then
        if [[ "$DRY_RUN" != "true" ]]; then
            local omz_script
            omz_script="$(mktemp)"
            register_cleanup "$omz_script"
            curl -fsSL -o "$omz_script" https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh
            RUNZSH=no CHSH=no sh "$omz_script"
            rm -f "$omz_script"
        else
            printf '\e[2;37m  [dry] install oh-my-zsh\e[0m\n'
        fi
    else
        ok "Oh My Zsh already installed."
    fi
}

_zsh_install_plugins() {
    local plugin_dir="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}/plugins/zsh-syntax-highlighting"

    if [[ ! -d "$plugin_dir" ]]; then
        run git clone --depth=1 \
            "$(git_url git@github.com:zsh-users/zsh-syntax-highlighting.git)" \
            "$plugin_dir"
    fi
}

_zsh_patch_theme_and_plugins() {
    local zshrc="$1"

    if [[ -f "$zshrc" ]]; then
        run sed -i.bak \
            -e 's/ZSH_THEME="robbyrussell"/ZSH_THEME="agnoster"/' \
            -e 's/^plugins=(git)$/plugins=(git zsh-syntax-highlighting)/' \
            "$zshrc"
        run rm -f "${zshrc}.bak"
    fi
}

_zsh_fix_legacy() {
    local zshrc="$1"

    if [[ -f "$zshrc" ]]; then
        # Fix bare unguarded 'tmux attach || tmux new' left by older setup runs.
        # Must use Python  - sed chokes on || in the match pattern.
        if command_exists python3; then
            python3 - "$zshrc" << 'PYFIX'
import sys
path = sys.argv[1]
with open(path) as f:
    content = f.read()
bare = 'tmux attach || tmux new\n'
guarded = 'if [[ -z "$TMUX" && -z "${CI:-}" && -t 1 ]]; then tmux attach 2>/dev/null || tmux new; fi\n'
changed = False
if bare in content and guarded not in content:
    content = content.replace(bare, guarded, 1)
    changed = True
    print('  fixed: bare tmux attach line guarded')

# Remove legacy literal-\n uv-virtualenvwrapper line written by older setups.
bad = r'\n# uv-virtualenvwrapper\nsource "$HOME/.local/bin/uv-virtualenvwrapper.sh"'
if bad in content:
    content = content.replace(bad, '')
    changed = True
    print('  fixed: removed literal-\\n uv-virtualenvwrapper line')

if changed:
    with open(path, 'w') as f:
        f.write(content)
PYFIX
        else
            warn "python3 not found  - skipping legacy zshrc cleanup (check for bare 'tmux attach || tmux new' manually)"
        fi
    fi
}

_zsh_append_customizations() {
    local zshrc="$1"

    if grep -q "# >>> dotfiles customizations <<<" "$zshrc" 2>/dev/null; then
        ok ".zshrc customizations already present."
    else
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] append dotfiles customizations to %s\e[0m\n' "$zshrc"
        else
            local path_prefix="\$HOME/.gnubin"
            if [[ "$OS" == "macos" ]]; then
                local brew_prefix
                brew_prefix="$(brew --prefix 2>/dev/null || echo '/opt/homebrew')"
                path_prefix="${brew_prefix}/bin:\$HOME/.gnubin"
            fi

            cat >> "$zshrc" << EOF

# >>> dotfiles customizations <<<

export PATH="${path_prefix}:\$PATH"

autoload -U +X bashcompinit && bashcompinit

if [[ -n "\$SSH_CONNECTION" ]]; then
    export EDITOR='vim'
else
    if command -v nvim &>/dev/null; then
        export EDITOR='nvim'
    else
        export EDITOR='vim'
    fi
fi

export SSH_KEY_PATH="\$HOME/.ssh/id_ed25519"
prompt_context() {}
export GPG_TTY=\$(tty)
bindkey '^R' history-incremental-search-backward
fpath+=\${ZDOTDIR:-~}/.zsh_functions

command -v kubectl &>/dev/null && source <(kubectl completion zsh)
command -v helm    &>/dev/null && source <(helm completion zsh)

[ -f "\$HOME/.fzf.zsh" ] && source "\$HOME/.fzf.zsh"

export PYENV_ROOT="\$HOME/.pyenv"
[[ -d "\$PYENV_ROOT/bin" ]] && export PATH="\$PYENV_ROOT/bin:\$PATH"
command -v pyenv &>/dev/null && eval "\$(pyenv init -)"

# uv
[ -f "\$HOME/.local/bin/env" ] && . "\$HOME/.local/bin/env"
export WORKON_HOME="\$HOME/.venvs"
[ -f "\$HOME/.local/bin/uv-virtualenvwrapper.sh" ] && source "\$HOME/.local/bin/uv-virtualenvwrapper.sh"

if [[ -z "\$TMUX" && -z "\${CI:-}" && -t 1 ]]; then
    tmux attach 2>/dev/null || tmux new
fi

# Disable tmux focus-events during SSH to prevent garbage characters (e.g. [[;)
# injected by terminal focus escape sequences when browser windows open for
# SSO/SSM authentication flows.
ssh() {
    if [[ -n "\$TMUX" ]]; then
        tmux set -g focus-events off
        command ssh "\$@"
        local _ret=\$?
        tmux set -g focus-events on
        return \$_ret
    else
        command ssh "\$@"
    fi
}

# Same guard for 'aws sso login' which also opens a browser popup.
# All other aws subcommands pass through unchanged.
aws() {
    if [[ -n "\$TMUX" && "\$1" == "sso" && "\$2" == "login" ]]; then
        tmux set -g focus-events off
        command aws "\$@"
        local _ret=\$?
        tmux set -g focus-events on
        return \$_ret
    else
        command aws "\$@"
    fi
}

# <<< dotfiles customizations <<<
EOF
        fi
    fi
}

_zsh_set_default_shell() {
    local zsh_path

    zsh_path="$(command -v zsh || true)"
    if [[ -z "$zsh_path" ]]; then
        warn "zsh not found in PATH  - skipping default shell change"
    elif [[ "$SHELL" != "$zsh_path" ]]; then
        grep -qxF "$zsh_path" /etc/shells || {
            if [[ "$DRY_RUN" == "true" ]]; then
                printf '\e[2;37m  [dry] add %s to /etc/shells\e[0m\n' "$zsh_path"
            else
                echo "$zsh_path" | sudo tee -a /etc/shells
            fi
        }
        run sudo chsh -s "$zsh_path" "$USER" \
            || warn "chsh failed  - run manually: chsh -s $zsh_path"
    fi
}

_zsh_set_default_editor() {
    if command_exists update-alternatives && command_exists vim; then
        local vim_path

        vim_path="$(command -v vim)"
        # Register vim in the alternatives system before selecting it.
        # --install is idempotent; without this, --set fails if vim was never registered.
        run sudo update-alternatives --install /usr/bin/editor editor "$vim_path" 50 \
            || warn "update-alternatives --install editor failed (non-fatal)"
        run sudo update-alternatives --set editor "$vim_path" \
            || warn "update-alternatives --set editor failed (non-fatal)"
    fi
}

_zsh_install_tmux_rename_hook() {
    local zshrc="$1"
    local hook_dir="$HOME/.config/zsh/hooks"
    local hook_file="${hook_dir}/tmux-rename.zsh"
    local hook_src="${SCRIPT_DIR}/scripts/tmux-rename.zsh"

    run mkdir -p "$hook_dir"

    if [[ -f "$hook_src" ]]; then
        run cp "$hook_src" "$hook_file"
    else
        warn "tmux-rename.zsh source not found at ${hook_src}; skipping hook install"
        return
    fi

    # Ensure .zshrc sources the hook
    if ! grep -q "tmux-rename.zsh" "$zshrc" 2>/dev/null; then
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] add tmux-rename hook source to %s\e[0m\n' "$zshrc"
        else
            cat >> "$zshrc" << 'TMUX_RENAME_HOOK'

# tmux smart window/pane naming
[ -f "$HOME/.config/zsh/hooks/tmux-rename.zsh" ] && source "$HOME/.config/zsh/hooks/tmux-rename.zsh"
TMUX_RENAME_HOOK
        fi
    fi
    ok "tmux-rename hook installed."
}

section_zsh() {
    local zshrc="$HOME/.zshrc"

    log "Setting up Zsh + Oh My Zsh..."

    _zsh_install_omz
    _zsh_install_plugins
    _zsh_patch_theme_and_plugins "$zshrc"
    _zsh_fix_legacy "$zshrc"
    _zsh_append_customizations "$zshrc"
    _zsh_install_tmux_rename_hook "$zshrc"
    _zsh_set_default_shell
    _zsh_set_default_editor

    ok "Zsh configured."
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_zsh() {
    [[ -d "$HOME/.oh-my-zsh" ]]         && pass "Oh My Zsh installed"                          || fail "Oh My Zsh not installed"
    local zshrc="$HOME/.zshrc"
    [[ -f "$zshrc" ]]                   && pass "~/.zshrc exists"                              || { fail "~/.zshrc missing"; return; }
    grep -q 'ZSH_THEME="agnoster"' "$zshrc"               && pass "agnoster theme set"         || fail "agnoster theme not set"
    grep -q "zsh-syntax-highlighting"   "$zshrc"           && pass "zsh-syntax-highlighting present" || fail "zsh-syntax-highlighting missing"
    grep -q "# >>> dotfiles customizations <<<" "$zshrc"   && pass "customization block present"     || fail "customization block missing"
    grep -q "^ssh()"    "$zshrc"  && pass "ssh() focus-events wrapper present"   || fail "ssh() focus-events wrapper missing"
    grep -q "^aws()"    "$zshrc"  && pass "aws() focus-events wrapper present"   || fail "aws() focus-events wrapper missing"
    grep -q "WORKON_HOME" "$zshrc" && pass "WORKON_HOME set in .zshrc"           || fail "WORKON_HOME not set in .zshrc"
    grep -q 'uv-virtualenvwrapper.sh' "$zshrc" && pass "uv-virtualenvwrapper sourced in .zshrc" || fail "uv-virtualenvwrapper not sourced in .zshrc"
    [[ -f "$HOME/.config/zsh/hooks/tmux-rename.zsh" ]] && pass "tmux-rename hook installed"    || fail "tmux-rename hook not installed"
    grep -q "tmux-rename.zsh" "$zshrc"  && pass "tmux-rename hook sourced in .zshrc"           || fail "tmux-rename hook not sourced in .zshrc"
}
