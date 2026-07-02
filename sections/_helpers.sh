# shellcheck shell=bash
# Shared helper functions sourced by setup.sh before other section modules.

ensure_bun() {
    local bun_bin="$HOME/.bun/bin/bun"
    if command_exists bun || [[ -x "$bun_bin" ]]; then
        ok "bun already installed: $(bun --version 2>/dev/null || "$bun_bin" --version)"
        return 0
    fi

    log "Installing Bun..."
    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] install Bun via fetch_and_run\e[0m\n'
        return 0
    fi

    fetch_and_run "https://bun.sh/install"

    command_exists bun || [[ -x "$bun_bin" ]] || { warn "bun not found after install"; return 1; }
    export PATH="$HOME/.bun/bin:$PATH"
}

# Markers that delimit the repo-managed region of an instructions file. Content
# between these lines is owned by this repo and re-synced on every run. Anything
# outside the markers (local overrides) is authored per-machine and never touched.
INSTRUCTIONS_MANAGED_BEGIN="# >>> dotfiles-managed (do not edit; setup.sh overwrites this block) <<<"
INSTRUCTIONS_MANAGED_END="# <<< dotfiles-managed >>>"

# Print the managed block (begin..end markers inclusive) from a file.
_managed_block() {
    local file="$1"
    awk -v b="$INSTRUCTIONS_MANAGED_BEGIN" -v e="$INSTRUCTIONS_MANAGED_END" \
        '$0==b{inblk=1} inblk{print} $0==e && inblk{exit}' "$file"
}

# True (0) when the seed's managed block differs from the dest's managed block.
_managed_block_differs() {
    local src_file="$1" dest_file="$2"
    [[ "$(_managed_block "$src_file")" != "$(_managed_block "$dest_file")" ]]
}

# Replace dest's managed block with the seed's managed block, preserving every
# line outside the markers (the local-overrides section). Splices via file
# concatenation so backslashes/code samples in the content are never mangled.
_sync_managed_block() {
    local src_file="$1" dest_file="$2"
    local head tail block out
    # head/tail/block are scratch; out MUST live in dest's directory so the final
    # mv is a same-filesystem atomic rename (a cross-fs mv degrades to a
    # copy-then-unlink that can truncate dest and destroy local overrides).
    head="$(mktemp)" && tail="$(mktemp)" && block="$(mktemp)" \
        && out="$(mktemp "$(dirname "$dest_file")/.dotfiles-instr.XXXXXX")"
    if [[ ! -e "$head" || ! -e "$tail" || ! -e "$block" || ! -e "$out" ]]; then
        warn "mktemp failed; leaving ${dest_file} untouched."
        rm -f "$head" "$tail" "$block" "$out" 2>/dev/null
        return 1
    fi
    # Read all three pieces; abort without writing if any read fails, so a
    # silent awk/IO error can never overwrite dest with an incomplete splice.
    if ! awk -v b="$INSTRUCTIONS_MANAGED_BEGIN" '$0==b{exit} {print}' "$dest_file" > "$head" \
        || ! awk -v e="$INSTRUCTIONS_MANAGED_END" 'found{print} $0==e{found=1}' "$dest_file" > "$tail" \
        || ! _managed_block "$src_file" > "$block"; then
        warn "failed to read managed block; leaving ${dest_file} untouched."
        rm -f "$head" "$tail" "$block" "$out"
        return 1
    fi
    if ! { cat "$head" "$block" "$tail" > "$out" && mv "$out" "$dest_file"; }; then
        warn "failed to write managed block; leaving ${dest_file} untouched."
        rm -f "$head" "$tail" "$block" "$out"
        return 1
    fi
    rm -f "$head" "$tail" "$block"
}

# Install or update a tool's instructions file.
#
# If the seed carries the managed markers, the file is split into a repo-managed
# block (re-synced every run) and a local-overrides section (never touched):
#   - dest absent          -> write the seed verbatim (managed block + scaffold)
#   - dest has markers      -> re-sync only the managed block; keep local content
#   - dest lacks markers    -> warn and skip (never clobber a pre-split file)
#
# If the seed has no markers (legacy tools), the file is install-once: written
# only when absent, never overwritten.
install_instructions() {
    local dest_dir="$1"
    local dest_file="$2"
    local src_file="$3"
    local tool_name="$4"

    run mkdir -p "$dest_dir"

    if grep -qxF "$INSTRUCTIONS_MANAGED_BEGIN" "$src_file" 2>/dev/null \
        && grep -qxF "$INSTRUCTIONS_MANAGED_END" "$src_file" 2>/dev/null; then
        if [[ ! -f "$dest_file" ]]; then
            log "Writing ${tool_name} instructions (first-time bootstrap)..."
            if [[ "$DRY_RUN" == "true" ]]; then
                printf '\e[2;37m  [dry] copy %s to %s\e[0m\n' "$src_file" "$dest_file"
            else
                cp "$src_file" "$dest_file"
            fi
            ok "${tool_name} instructions written to ${dest_file}."
        elif grep -qxF "$INSTRUCTIONS_MANAGED_BEGIN" "$dest_file" 2>/dev/null \
            && grep -qxF "$INSTRUCTIONS_MANAGED_END" "$dest_file" 2>/dev/null; then
            if _managed_block_differs "$src_file" "$dest_file"; then
                log "Re-syncing ${tool_name} managed block..."
                if [[ "$DRY_RUN" == "true" ]]; then
                    printf '\e[2;37m  [dry] re-sync managed block in %s (local overrides preserved)\e[0m\n' "$dest_file"
                    ok "${tool_name} managed block re-synced in ${dest_file}."
                elif _sync_managed_block "$src_file" "$dest_file"; then
                    ok "${tool_name} managed block re-synced in ${dest_file}."
                fi
            else
                ok "${tool_name} managed block up to date at ${dest_file}."
            fi
        else
            warn "${tool_name} instructions at ${dest_file} predate the managed/local split; leaving untouched. Add the marker blocks manually to enable managed sync."
        fi
    else
        if [[ -f "$dest_file" ]]; then
            ok "${tool_name} instructions already present at ${dest_file}; leaving local copy untouched."
        else
            log "Writing ${tool_name} instructions..."
            if [[ "$DRY_RUN" == "true" ]]; then
                printf '\e[2;37m  [dry] copy %s to %s\e[0m\n' "$src_file" "$dest_file"
            else
                cp "$src_file" "$dest_file"
            fi
            ok "${tool_name} instructions written to ${dest_file}."
        fi
    fi
}

_install_local_skills() {
    local target_dir="$1"
    local skill src dest
    run mkdir -p "$target_dir"
    for src in "${SCRIPT_DIR}/skills"/*/; do
        [[ -d "$src" ]] || continue
        skill="$(basename "$src")"
        dest="${target_dir}/${skill}"
        # Remove existing symlink (e.g., from superpowers/plugins) so repo version wins
        if [[ -L "$dest" ]]; then
           run rm "$dest"
        fi
        run mkdir -p "$dest"
        run cp -R "${src}/." "$dest/"
    done
}

install_gstack() {
    local gstack_dir="$1"
    local host_flag="$2"
    local clone_url="${3:-git@github.com:garrytan/gstack.git}"
    local clone_opts="${4:-}"

    if [[ -d "$gstack_dir" ]]; then
        ok "gstack already installed at ${gstack_dir}."
        return 0
    fi

    ensure_bun || return 1
    log "Installing gstack..."
    if [[ ! -d "$gstack_dir" ]]; then
        # shellcheck disable=SC2086  # clone_opts needs word splitting
        run git clone --single-branch --depth 1 $clone_opts "$(git_url "$clone_url")" "$gstack_dir"
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] cd %s && ./setup %s\e[0m\n' "$gstack_dir" "$host_flag"
        ok "gstack installed (${host_flag})."
        return 0
    fi

    if [[ -d "$gstack_dir" ]]; then
        bash -c "cd '$gstack_dir' && ./setup $host_flag"
        ok "gstack installed (${host_flag})."
    fi
}
