#!/usr/bin/env bats
# Test that --dry-run mode does not create or modify files.

setup() {
    export SCRIPT_DIR="$BATS_TEST_DIRNAME/.."
    export HOME="$BATS_TEST_TMPDIR/fakehome"
    mkdir -p "$HOME"
}

@test "dry-run with python section does not create .profile or .zprofile" {
    "$SCRIPT_DIR/setup.sh" --dry-run --only python 2>&1 >/dev/null || true
    [[ ! -f "$HOME/.profile" ]]
    [[ ! -f "$HOME/.zprofile" ]]
}

@test "dry-run with tmux section does not create .tmux directory" {
    "$SCRIPT_DIR/setup.sh" --dry-run --only tmux 2>&1 >/dev/null || true
    [[ ! -d "$HOME/.tmux" ]]
}
