#!/usr/bin/env bats
# Test helper functions from setup.sh
# Requires: bats-core (brew install bats-core / apt install bats)

# Source only the helper functions by extracting them from setup.sh.
# We define the functions inline to avoid executing the full script.
setup() {
    export TEST_DIR="$BATS_TEST_TMPDIR"

    # Minimal state needed by helpers
    DRY_RUN=false
    CLONE_VIA=ssh
    _cleanup_paths=()

    # Define helpers as they appear in setup.sh
    command_exists() { command -v "$1" &>/dev/null; }

    register_cleanup() { _cleanup_paths+=("$1"); }

    _global_cleanup() {
        [[ ${#_cleanup_paths[@]} -gt 0 ]] || return 0
        for p in "${_cleanup_paths[@]}"; do
            [[ -e "$p" ]] && rm -rf "$p"
        done
    }

    run_helper() {
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] %s\e[0m\n' "$*"
        else
            "$@"
        fi
    }

    git_url() {
        local url="$1"
        if [[ "$CLONE_VIA" == "https" && "$url" == git@github.com:* ]]; then
            echo "https://github.com/${url#git@github.com:}"
        else
            echo "$url"
        fi
    }
}

# -- git_url() tests ----------------------------------------------------------

@test "git_url: SSH mode returns URL unchanged" {
    CLONE_VIA=ssh
    result="$(git_url "git@github.com:owner/repo.git")"
    [[ "$result" == "git@github.com:owner/repo.git" ]]
}

@test "git_url: HTTPS mode converts SSH to HTTPS" {
    CLONE_VIA=https
    result="$(git_url "git@github.com:owner/repo.git")"
    [[ "$result" == "https://github.com/owner/repo.git" ]]
}

@test "git_url: HTTPS mode leaves non-GitHub URLs unchanged" {
    CLONE_VIA=https
    result="$(git_url "https://example.com/repo.git")"
    [[ "$result" == "https://example.com/repo.git" ]]
}

# -- command_exists() tests ----------------------------------------------------

@test "command_exists: finds bash" {
    command_exists bash
}

@test "command_exists: fails for nonexistent command" {
    ! command_exists __this_command_does_not_exist_12345__
}

# -- run() tests ---------------------------------------------------------------

@test "run: executes command in normal mode" {
    DRY_RUN=false
    result="$(run_helper echo hello)"
    [[ "$result" == "hello" ]]
}

@test "run: prints but does not execute in dry-run mode" {
    DRY_RUN=true
    result="$(run_helper touch "$TEST_DIR/should-not-exist")"
    [[ ! -f "$TEST_DIR/should-not-exist" ]]
    [[ "$result" == *"[dry]"* ]]
}

# -- register_cleanup / _global_cleanup tests ----------------------------------

@test "register_cleanup: adds path to cleanup array" {
    _cleanup_paths=()
    register_cleanup "/tmp/test-path"
    [[ "${_cleanup_paths[0]}" == "/tmp/test-path" ]]
}

@test "_global_cleanup: removes registered paths" {
    _cleanup_paths=()
    local tmp_file="$TEST_DIR/cleanup-test-$$"
    touch "$tmp_file"
    register_cleanup "$tmp_file"
    _global_cleanup
    [[ ! -f "$tmp_file" ]]
}

@test "_global_cleanup: handles empty array without error" {
    _cleanup_paths=()
    _global_cleanup
}
