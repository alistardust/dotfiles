#!/usr/bin/env bats
# Test section module contract: every public sections/*.sh file must define
# both section_<name>() and verify_<name>() functions. Helper modules prefixed
# with an underscore are sourced privately by setup.sh and are excluded.

setup() {
    export SCRIPT_DIR="$BATS_TEST_DIRNAME/.."
}

@test "all section files define section_<name> function" {
    local failures=()
    for f in "$SCRIPT_DIR"/sections/[!_]*.sh; do
        local name
        name="$(basename "$f" .sh)"
        if ! grep -q "^section_${name}()" "$f"; then
            failures+=("$f missing section_${name}()")
        fi
    done
    if [[ ${#failures[@]} -gt 0 ]]; then
        printf '%s\n' "${failures[@]}"
        return 1
    fi
}

@test "all section files define verify_<name> function" {
    local failures=()
    for f in "$SCRIPT_DIR"/sections/[!_]*.sh; do
        local name
        name="$(basename "$f" .sh)"
        if ! grep -q "^verify_${name}()" "$f"; then
            failures+=("$f missing verify_${name}()")
        fi
    done
    if [[ ${#failures[@]} -gt 0 ]]; then
        printf '%s\n' "${failures[@]}"
        return 1
    fi
}

@test "all section files have shellcheck shell=bash directive" {
    local failures=()
    for f in "$SCRIPT_DIR"/sections/[!_]*.sh; do
        if ! head -1 "$f" | grep -q "# shellcheck shell=bash"; then
            failures+=("$f missing shellcheck directive")
        fi
    done
    if [[ ${#failures[@]} -gt 0 ]]; then
        printf '%s\n' "${failures[@]}"
        return 1
    fi
}

@test "ALL_SECTIONS in setup.sh matches section files on disk" {
    # Extract ALL_SECTIONS from setup.sh
    local declared
    declared="$(grep '^ALL_SECTIONS=' "$SCRIPT_DIR/setup.sh" | sed 's/ALL_SECTIONS=(//' | sed 's/)//' | tr ' ' '\n' | sort)"

    # List actual public section files
    local on_disk
    on_disk="$(
        for f in "$SCRIPT_DIR"/sections/[!_]*.sh; do
            basename "$f" .sh
        done | sort
    )"

    if [[ "$declared" != "$on_disk" ]]; then
        echo "Declared in ALL_SECTIONS:"
        echo "$declared"
        echo ""
        echo "Files in sections/:"
        echo "$on_disk"
        echo ""
        diff <(echo "$declared") <(echo "$on_disk") || true
        return 1
    fi
}
