#!/usr/bin/env bats
# Test that --dry-run mode does not create or modify files.

setup() {
    export SCRIPT_DIR="$BATS_TEST_DIRNAME/.."
    export HOME="$BATS_TEST_TMPDIR/fakehome"
    mkdir -p "$HOME"
}

@test "dry-run with python section does not create .profile or .zprofile" {
    run "$SCRIPT_DIR/setup.sh" --dry-run --only python
    [ "$status" -eq 0 ]
    [[ ! -f "$HOME/.profile" ]]
    [[ ! -f "$HOME/.zprofile" ]]
}

@test "dry-run with tmux section does not create .tmux directory" {
    run "$SCRIPT_DIR/setup.sh" --dry-run --only tmux
    [ "$status" -eq 0 ]
    [[ ! -d "$HOME/.tmux" ]]
}
