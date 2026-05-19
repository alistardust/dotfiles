#!/usr/bin/env bats
# Test argument parsing produces the correct RUN[] array state.

setup() {
    export SCRIPT_DIR="$BATS_TEST_DIRNAME/.."
}

# Helper: run setup.sh with given args, extract which sections are enabled.
# Uses --dry-run to prevent actual execution; parses the "Sections:" output line.
get_enabled_sections() {
    "$SCRIPT_DIR/setup.sh" --dry-run "$@" 2>&1 | grep "Sections:" | sed 's/.*Sections://' | sed $'s/\033\\[[0-9;]*m//g' | xargs
}

@test "default run includes packages, tmux, zsh, vim but not copilot" {
    local sections
    sections="$(get_enabled_sections)"
    [[ "$sections" == *"packages"* ]]
    [[ "$sections" == *"tmux"* ]]
    [[ "$sections" == *"zsh"* ]]
    [[ "$sections" == *"vim"* ]]
    [[ "$sections" != *"copilot"* ]]
    [[ "$sections" != *"claude"* ]]
    [[ "$sections" != *"chatgpt"* ]]
    [[ "$sections" != *"shellgpt"* ]]
}

@test "--only restricts to listed sections" {
    local sections
    sections="$(get_enabled_sections --only zsh vim)"
    [[ "$sections" == "zsh vim" ]]
}

@test "--skip removes listed sections" {
    local sections
    sections="$(get_enabled_sections --skip packages fonts)"
    [[ "$sections" != *"packages"* ]]
    [[ "$sections" != *"fonts"* ]]
    [[ "$sections" == *"tmux"* ]]
}

@test "--copilot enables copilot section" {
    local sections
    sections="$(get_enabled_sections --copilot)"
    [[ "$sections" == *"copilot"* ]]
}

@test "--all enables all sections" {
    local sections
    sections="$(get_enabled_sections --all)"
    [[ "$sections" == *"copilot"* ]]
    [[ "$sections" == *"claude"* ]]
    [[ "$sections" == *"chatgpt"* ]]
    [[ "$sections" == *"shellgpt"* ]]
    [[ "$sections" == *"copilot_skills"* ]]
}

@test "--https flag is accepted without error" {
    local output
    output="$(get_enabled_sections --only packages --https)"
    [[ "$output" == *"packages"* ]]
}

@test "invalid section name causes error" {
    run "$SCRIPT_DIR/setup.sh" --dry-run --only nonexistent_section
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"Unknown section"* ]]
}

@test "invalid flag causes error" {
    run "$SCRIPT_DIR/setup.sh" --dry-run --bogus-flag
    [[ "$status" -ne 0 ]]
    [[ "$output" == *"Unknown option"* ]]
}
