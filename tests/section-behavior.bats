#!/usr/bin/env bats
# shellcheck shell=bash
# shellcheck disable=SC1091,SC2034,SC2329

setup() {
    export SCRIPT_DIR="$BATS_TEST_DIRNAME/.."
    export HOME="$BATS_TEST_TMPDIR/home"
    mkdir -p "$HOME"

    DRY_RUN=true
    OS=macos
    SHELL=/bin/zsh
    USER=tester

    command_exists() {
        return 1
    }

    log() {
        printf 'log:%s\n' "$*"
    }

    ok() {
        printf 'ok:%s\n' "$*"
    }

    warn() {
        printf 'warn:%s\n' "$*"
    }

    pass() {
        printf 'pass:%s\n' "$*"
    }

    fail() {
        printf 'fail:%s\n' "$*"
        return 0
    }

    skip_check() {
        printf 'skip:%s\n' "$*"
    }

    detect_linux_distro() {
        echo debian
    }

    source "$SCRIPT_DIR/sections/zsh.sh"
    source "$SCRIPT_DIR/sections/wsl.sh"
    source "$SCRIPT_DIR/sections/ddcutil.sh"
}

@test "zsh helpers exist and a decomposed helper is callable" {
    declare -F _zsh_install_omz >/dev/null
    declare -F _zsh_install_plugins >/dev/null
    declare -F _zsh_patch_theme_and_plugins >/dev/null
    declare -F _zsh_fix_legacy >/dev/null
    declare -F _zsh_append_customizations >/dev/null
    declare -F _zsh_set_default_shell >/dev/null
    declare -F _zsh_set_default_editor >/dev/null

    run _zsh_append_customizations "$HOME/.zshrc"

    [[ "$status" -eq 0 ]]
}

@test "wsl helpers exist and a decomposed helper is callable" {
    declare -F _wsl_install_packages >/dev/null
    declare -F _wsl_write_system_config >/dev/null
    declare -F _wsl_patch_user_configs >/dev/null
    declare -F _wsl_print_windows_steps >/dev/null

    run _wsl_print_windows_steps

    [[ "$status" -eq 0 ]]
}

@test "ddcutil helpers exist and a decomposed helper is callable" {
    declare -F _ddcutil_install_linux_tools >/dev/null
    declare -F _ddcutil_install_macos_tools >/dev/null
    declare -F _ddcutil_write_linux_aliases >/dev/null
    declare -F _ddcutil_write_macos_aliases >/dev/null
    declare -F _ddcutil_write_aliases >/dev/null

    run _ddcutil_write_aliases "$HOME/.zshrc"

    [[ "$status" -eq 0 ]]
}

@test "verify_zsh can be invoked without shell errors" {
    run verify_zsh

    [[ "$status" -eq 0 ]]
}

@test "verify_wsl can be invoked without shell errors on macOS" {
    run verify_wsl

    [[ "$status" -eq 0 ]]
}

@test "verify_ddcutil can be invoked without shell errors" {
    run verify_ddcutil

    [[ "$status" -eq 0 ]]
}
