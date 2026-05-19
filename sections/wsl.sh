# shellcheck shell=bash
# Section: wsl
# shellcheck disable=SC2088,SC2015

# -- 8. WSL2 ------------------------------------------------------------------

section_wsl() {
    if [[ "$OS" != "wsl" ]]; then
        warn "WSL section is WSL-only, skipping on $OS."
        return
    fi
    log "Configuring WSL2 environment..."

    # wslu provides wslview (open URLs/files in Windows), wslpath, etc.
    if ! command_exists wslview; then
        run sudo apt-get install -y wslu
    else
        ok "wslu already installed."
    fi

    # win32yank.exe  - bidirectional clipboard, handles CRLF automatically.
    # Better than clip.exe (write-only) + powershell paste (slow).
    if ! command_exists win32yank.exe; then
        log "Installing win32yank for clipboard integration..."
        command_exists unzip || run sudo apt-get install -y unzip
        local winy_tmp
        winy_tmp="$(mktemp)"
        register_cleanup "$winy_tmp"
        run curl -fsSL -o "$winy_tmp" \
            "https://github.com/equalsraf/win32yank/releases/latest/download/win32yank-x64.zip"
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] extract win32yank.exe to /usr/local/bin/win32yank.exe\e[0m\n'
        else
            unzip -p "$winy_tmp" win32yank.exe | sudo tee /usr/local/bin/win32yank.exe > /dev/null
        fi
        run sudo chmod +x /usr/local/bin/win32yank.exe
        rm -f "$winy_tmp"
        ok "win32yank installed at /usr/local/bin/win32yank.exe"
    else
        ok "win32yank already installed."
    fi

    # /etc/wsl.conf  - enable systemd, lock in the default user.
    # Only written if the file doesn't exist; never overwrites existing config.
    if [[ ! -f /etc/wsl.conf ]]; then
        log "Writing /etc/wsl.conf (systemd + interop settings)..."
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] write /etc/wsl.conf\e[0m\n'
        else
            sudo tee /etc/wsl.conf > /dev/null << EOF
[boot]
systemd=true

[interop]
# Keep clip.exe, explorer.exe, etc. available inside WSL
appendWindowsPath=true

[user]
default=${USER}
EOF
        fi
        ok "/etc/wsl.conf written. Run 'wsl --shutdown' from PowerShell to apply."
    else
        ok "/etc/wsl.conf already exists  - not overwriting."
    fi

    # ~/.tmux.conf.local  - true color + win32yank clipboard (idempotent)
    local tmux_conf="$HOME/.tmux.conf.local"
    if [[ -f "$tmux_conf" ]] && ! grep -q "# >>> WSL config <<<" "$tmux_conf"; then
        log "Patching ~/.tmux.conf.local for WSL2 (true color + clipboard)..."
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] append WSL config to %s\e[0m\n' "$tmux_conf"
        else
            cat >> "$tmux_conf" << 'TMUX_WSL'

# >>> WSL config <<<

# True color passthrough  - required for termguicolors in vim to render correctly
# in Windows Terminal. Must match what Windows Terminal reports as TERM.
set -g default-terminal "tmux-256color"
set -ga terminal-overrides ",xterm-256color:Tc"
set -ga terminal-overrides ",*256col*:Tc"

# Clipboard via win32yank  - bidirectional, strips CRLF on paste automatically.
# Overrides gpakosz framework's xsel/xclip path which requires X11.
if -b 'command -v win32yank.exe > /dev/null 2>&1' {
    set -s copy-command 'win32yank.exe -i --crlf'
    bind -T copy-mode-vi y     send -X copy-pipe-and-cancel 'win32yank.exe -i --crlf'
    bind -T copy-mode-vi Enter send -X copy-pipe-and-cancel 'win32yank.exe -i --crlf'
    bind -T copy-mode    y     send -X copy-pipe-and-cancel 'win32yank.exe -i --crlf'
    bind -T copy-mode    Enter send -X copy-pipe-and-cancel 'win32yank.exe -i --crlf'
}

# <<< WSL config <<<
TMUX_WSL
        fi
        ok "~/.tmux.conf.local patched."
    else
        ok "tmux WSL config already present."
    fi

    # ~/.vimrc.local  - true color + win32yank clipboard (idempotent)
    local vimrc_local="$HOME/.vimrc.local"
    if ! grep -q "\" >>> WSL config <<<" "$vimrc_local" 2>/dev/null; then
        log "Patching ~/.vimrc.local for WSL2 (true color + clipboard)..."
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] append WSL config to %s\e[0m\n' "$vimrc_local"
        else
            [[ -f "$vimrc_local" ]] || touch "$vimrc_local"
            cat >> "$vimrc_local" << 'VIM_WSL'

" >>> WSL config <<<

" True color  - vim is compiled with +termguicolors; Windows Terminal supports it.
" t_8f/t_8b sequences are required when not running a true GUI vim.
if has('termguicolors')
  let &t_8f = "\<Esc>[38;2;%lu;%lu;%lum"
  let &t_8b = "\<Esc>[48;2;%lu;%lu;%lum"
  set termguicolors
endif

" Bidirectional clipboard via win32yank.
" --crlf on copy: Windows apps expect CRLF.
" --lf on paste:  strip CRLF so pasting into vim doesn't leave ^M on every line.
if executable('win32yank.exe')
  let g:clipboard = {
    \ 'name': 'win32yank',
    \ 'copy':  { '+': 'win32yank.exe -i --crlf', '*': 'win32yank.exe -i --crlf' },
    \ 'paste': { '+': 'win32yank.exe -o --lf',   '*': 'win32yank.exe -o --lf'   },
    \ 'cache_enabled': 0,
    \ }
  set clipboard=unnamedplus
endif

" <<< WSL config <<<
VIM_WSL
        fi
        ok "~/.vimrc.local patched."
    else
        ok "vim WSL config already present."
    fi

    # Print the Windows-side steps that can't be scripted from inside WSL
    printf '\n'
    printf '  \e[1;33m┌- Windows-side steps (run these in PowerShell) --------------------------┐\e[0m\n'
    printf '  \e[1;33m│\e[0m                                                                          \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m  1. Install MesloLGM Nerd Font:                                         \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m     Invoke-WebRequest -Uri "https://github.com/ryanoasis/nerd-fonts/    \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m       releases/latest/download/Meslo.zip" -OutFile "$env:TEMP\Meslo.zip"\e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m     Expand-Archive "$env:TEMP\Meslo.zip" "$env:TEMP\Meslo" -Force       \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m     # Then right-click each .ttf -> Install for all users               \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m                                                                          \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m  2. Copy wslconfig.template -> %%USERPROFILE%%\\.wslconfig               \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m     (adjust memory/cpu values for your machine)                         \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m                                                                          \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m  3. Import Windows Terminal color scheme from:                          \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m     terminal_configs/windows-terminal-settings.json                     \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m     (Settings -> Open JSON -> merge "schemes" + "profiles.defaults")      \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m                                                                          \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m  4. Apply /etc/wsl.conf: run  wsl --shutdown  then reopen              \e[1;33m│\e[0m\n'
    printf '  \e[1;33m│\e[0m                                                                          \e[1;33m│\e[0m\n'
    printf '  \e[1;33m└--------------------------------------------------------------------------┘\e[0m\n'
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_wsl() {
    if [[ "$OS" != "wsl" ]]; then skip_check "WSL section not applicable on $OS"; return; fi
    command_exists wslview              && pass "wslu installed"                                || fail "wslu not installed"
    command_exists win32yank.exe        && pass "win32yank installed"                          || fail "win32yank not installed"
    [[ -f /etc/wsl.conf ]]             && pass "/etc/wsl.conf present"                        || fail "/etc/wsl.conf missing"
    grep -q "# >>> WSL config <<<" "$HOME/.tmux.conf.local" 2>/dev/null \
                                        && pass "tmux WSL config present"                      || fail "tmux WSL config not in ~/.tmux.conf.local"
    grep -q "\" >>> WSL config <<<" "$HOME/.vimrc.local" 2>/dev/null \
                                        && pass "vim WSL config present"                       || fail "vim WSL config not in ~/.vimrc.local"
}
