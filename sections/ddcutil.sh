# shellcheck shell=bash
# Section: ddcutil
# shellcheck disable=SC2088,SC2015

# -- 12. DDC/CI monitor control ------------------------------------------------

section_ddcutil() {
    if [[ "$OS" == "wsl" ]]; then
        log "ddcutil: skipping (not supported under WSL)"
        return 0
    fi

    case "$OS" in
        linux)
            log "Setting up ddcutil (DDC/CI monitor control)..."
            if ! command_exists ddcutil; then
                case "$(detect_linux_distro)" in
                    arch)   run sudo pacman -S --noconfirm ddcutil ;;
                    debian) run sudo apt-get install -y ddcutil ;;
                    *)      warn "Unknown distro -- install ddcutil manually." ; return 0 ;;
                esac
            else
                ok "ddcutil already installed."
            fi
            # Add user to i2c group for passwordless DDC/CI access
            if ! id -nG | grep -qw i2c; then
                run sudo usermod -aG i2c "$(whoami)"
                ok "Added $(whoami) to i2c group -- re-login for effect."
            else
                ok "User already in i2c group."
            fi
            ;;
        macos)
            log "Setting up m1ddc + displayplacer (DDC/CI monitor control for macOS)..."
            if ! command_exists m1ddc; then
                run brew install m1ddc
            else
                ok "m1ddc already installed."
            fi
            if ! command_exists displayplacer; then
                run brew install displayplacer
            else
                ok "displayplacer already installed."
            fi
            ;;
        *)
            warn "ddcutil: unsupported OS ($OS)"
            ;;
    esac

    # Inject monitor-switching aliases into ~/.zshrc (idempotent, OS-aware)
    local zshrc="$HOME/.zshrc"
    if [[ -f "$zshrc" ]] && grep -q "# >>> ddcutil aliases <<<" "$zshrc" 2>/dev/null; then
        ok "ddcutil aliases already present in $zshrc."
        return 0
    fi
    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] append ddcutil monitor aliases to %s\e[0m\n' "$zshrc"
        return 0
    fi

    case "$OS" in
        linux)
            cat >> "$zshrc" << 'EOF'

# >>> ddcutil aliases <<<
# Two-monitor setup via DDC/CI (ddcutil, KDE Wayland / kscreen-doctor).
#
# Physical layout (Linux mode):
#   [  Second: S34C65xU (DP-2) 3440x1440 @ 0,0      ]
#   [    Main: LC32G5xT (DP-3) 2560x1440 @ 364,1440  ]
#
# Input codes:
#   Main (bus 8): 0x0f=DisplayPort(Linux)  0x06=HDMI
#   Top  (bus 7): 0x0f=DisplayPort(Linux)  0x36=USB-C(MacBook)
if command -v ddcutil &>/dev/null; then
    # --- Individual input switches ---
    alias main-dp='ddcutil --bus=8 setvcp 60 0x0f'    # main → Linux (DP)
    alias main-hdmi='ddcutil --bus=8 setvcp 60 0x06'  # main → HDMI
    alias top-dp='ddcutil --bus=7 setvcp 60 0x0f'     # top  → Linux (DP)
    alias top-usbc='ddcutil --bus=7 setvcp 60 0x36'   # top  → MacBook (USB-C)

    # --- Brightness (top monitor) ---
    alias top-bright='ddcutil --bus=7 getvcp 10'
    top-set-bright() { ddcutil --bus=7 setvcp 10 "${1:?usage: top-set-bright <0-100>}"; }

    # --- Status ---
    mon-status() {
        echo "Main (LC32G5xT, bus 8): $(ddcutil --bus=8 getvcp 60 2>/dev/null)"
        echo "Top  (S34C65xU, bus 7): $(ddcutil --bus=7 getvcp 60 2>/dev/null)"
    }

    # --- Compound: switch both monitors + restore layout ---
    mon-linux() {
        echo "Switching monitors to Linux..."
        ddcutil --bus=8 setvcp 60 0x0f
        ddcutil --bus=7 setvcp 60 0x0f
        echo "Restoring KDE layout (waiting for monitors to wake)..."
        sleep 4
        kscreen-doctor \
            output.DP-2.enable \
            output.DP-2.mode.3440x1440@100 \
            output.DP-2.position.0,0 \
            output.DP-3.enable \
            output.DP-3.mode.2560x1440@144 \
            output.DP-3.position.364,1440
        echo "Done."
    }

    mon-mac() {
        echo "Handing monitors to MacBook..."
        ddcutil --bus=8 setvcp 60 0x06
        ddcutil --bus=7 setvcp 60 0x36
        echo "Done."
    }
fi
# <<< ddcutil aliases <<<
EOF
            ok "ddcutil aliases written to $zshrc."
            ;;
        macos)
            cat >> "$zshrc" << 'EOF'

# >>> ddcutil aliases <<<
# Two-monitor setup via DDC/CI (m1ddc) + display layout (displayplacer).
#
# Physical layout (Mac mode):
#   [  Top:  S34C65xU  ] (USB-C direct,       m1ddc display 3)
#   [  Main: LC32G5xT  ] (HDMI via USB-C,     m1ddc display 2)
#
# One-time setup: run 'mon-discover' to verify display numbers, then update
# MON_MAIN_NUM and MON_TOP_NUM in ~/.zshrc.local. Set MON_MAC_LAYOUT with
# the output of 'displayplacer list' for your preferred arrangement.
#
# Input codes (VCP 60, monitor-side):
#   Main: 15=DisplayPort(Linux)  6=HDMI(Mac via USB-C)
#   Top:  15=DisplayPort(Linux)  54=USB-C(MacBook)
MON_MAIN_NUM="${MON_MAIN_NUM:-2}"    # override in ~/.zshrc.local
MON_TOP_NUM="${MON_TOP_NUM:-3}"
MON_MAC_LAYOUT="${MON_MAC_LAYOUT:-}"  # set to 'displayplacer list' output

if command -v m1ddc &>/dev/null; then
    # --- Individual input switches ---
    alias main-dp="m1ddc display \$MON_MAIN_NUM set input 15"   # main → Linux (DP)
    alias main-hdmi="m1ddc display \$MON_MAIN_NUM set input 6"  # main → HDMI via USB-C (Mac)
    alias top-dp="m1ddc display \$MON_TOP_NUM set input 15"     # top  → Linux (DP)
    alias top-usbc="m1ddc display \$MON_TOP_NUM set input 54"   # top  → USB-C (Mac)

    # --- Brightness (top monitor) ---
    alias top-bright="m1ddc display \$MON_TOP_NUM get luminance"
    top-set-bright() { m1ddc display "$MON_TOP_NUM" set luminance "${1:?usage: top-set-bright <0-100>}"; }

    # --- Status ---
    mon-status() {
        echo "Displays seen by m1ddc:"
        m1ddc display list
    }

    # --- Discover display numbers ---
    mon-discover() {
        echo "Displays seen by m1ddc:"
        m1ddc display list
        echo ""
        echo "Set MON_MAIN_NUM and MON_TOP_NUM in ~/.zshrc.local once identified."
    }

    # --- Compound: switch both monitors + restore layout ---
    mon-mac() {
        echo "Taking monitors to MacBook..."
        m1ddc display "$MON_MAIN_NUM" set input 6   # main → HDMI via USB-C
        m1ddc display "$MON_TOP_NUM"  set input 54  # top  → USB-C
        if [[ -n "$MON_MAC_LAYOUT" ]] && command -v displayplacer &>/dev/null; then
            sleep 3
            eval "displayplacer $MON_MAC_LAYOUT"
        fi
        echo "Done."
    }

    mon-linux() {
        echo "Handing monitors to Linux..."
        m1ddc display "$MON_MAIN_NUM" set input 15  # main → DP
        m1ddc display "$MON_TOP_NUM"  set input 15  # top  → DP
        echo "Done."
    }
fi
# <<< ddcutil aliases <<<
EOF
            ok "m1ddc aliases written to $zshrc."
            ;;
    esac
}

verify_ddcutil() {
    if [[ "$OS" == "wsl" ]]; then skip_check "ddcutil section not applicable under WSL"; return; fi
    case "$OS" in
        linux)
            command_exists ddcutil          && pass "ddcutil installed"           || fail "ddcutil not installed"
            id -nG 2>/dev/null | grep -qw i2c \
                                            && pass "user in i2c group"           || fail "user not in i2c group (re-login required)"
            grep -q "# >>> ddcutil aliases <<<" "$HOME/.zshrc" 2>/dev/null \
                                            && pass "ddcutil aliases in .zshrc"   || fail "ddcutil aliases missing from .zshrc"
            ;;
        macos)
            command_exists m1ddc            && pass "m1ddc installed"             || fail "m1ddc not installed"
            command_exists displayplacer    && pass "displayplacer installed"     || fail "displayplacer not installed"
            grep -q "# >>> ddcutil aliases <<<" "$HOME/.zshrc" 2>/dev/null \
                                            && pass "ddcutil aliases in .zshrc"   || fail "ddcutil aliases missing from .zshrc"
            ;;
    esac
}
