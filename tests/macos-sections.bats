#!/usr/bin/env bats
# shellcheck shell=bash
# shellcheck disable=SC1091,SC2034,SC2329

# Regression tests for the macOS packages and gnubin sections. Both run against
# a stubbed brew so they never touch the real Homebrew install.

setup() {
    export SCRIPT_DIR="$BATS_TEST_TMPDIR/repo"
    export HOME="$BATS_TEST_TMPDIR/home"
    mkdir -p "$HOME" "$SCRIPT_DIR"

    DRY_RUN=false
    OS=macos
    BREW_PREFIX="$BATS_TEST_TMPDIR/brew"
    INSTALL_LOG="$BATS_TEST_TMPDIR/installed.log"
    : > "$INSTALL_LOG"

    command_exists() { [[ "$1" == "brew" ]]; }
    run() { "$@"; }
    log()  { printf 'log:%s\n' "$*"; }
    ok()   { printf 'ok:%s\n' "$*"; }
    warn() { printf 'warn:%s\n' "$*"; }

    # Stub brew. `install` drains stdin the way some real installs do, which
    # used to swallow the rest of the package list fed to the read loop.
    brew() {
        case "$1" in
            --prefix) printf '%s\n' "$BREW_PREFIX" ;;
            list)     return 1 ;;
            install)  cat > /dev/null
                      [[ "$2" == "missing" ]] && return 1
                      printf '%s\n' "$2" >> "$INSTALL_LOG" ;;
            *)        return 0 ;;
        esac
    }

    source "$BATS_TEST_DIRNAME/../sections/packages.sh"
    source "$BATS_TEST_DIRNAME/../sections/gnubin.sh"
}

@test "packages: every listed formula is installed even if brew reads stdin" {
    printf '%s\n' alpha '# comment' '' beta gamma > "$SCRIPT_DIR/brew_packages.txt"

    install_packages_macos

    [[ "$(cat "$INSTALL_LOG")" == "$(printf '%s\n' alpha beta gamma)" ]]
}

@test "packages: a formula that fails to install warns and does not stop the list" {
    printf '%s\n' alpha missing beta > "$SCRIPT_DIR/brew_packages.txt"

    # `run` is stubbed as the repo's dry-run helper above, so capture directly;
    # a non-zero exit here fails the test under bats' errexit.
    local output
    output="$(install_packages_macos 2>&1)"

    [[ "$output" == *"warn:brew install failed: missing"* ]]
    [[ "$(cat "$INSTALL_LOG")" == "$(printf '%s\n' alpha beta)" ]]
}

@test "gnubin: links symlinked GNU tools as well as regular files" {
    local gnubin="$BREW_PREFIX/opt/gnu-sed/libexec/gnubin"
    mkdir -p "$gnubin" "$BREW_PREFIX/bin"
    printf '#!/bin/sh\n' > "$BREW_PREFIX/bin/gsed"
    ln -s ../../../../bin/gsed "$gnubin/sed"
    printf '#!/bin/sh\n' > "$gnubin/find"

    section_gnubin

    [[ -L "$HOME/.gnubin/sed" ]]
    [[ -L "$HOME/.gnubin/find" ]]
}
