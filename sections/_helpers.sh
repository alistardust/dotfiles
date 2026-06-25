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

install_instructions() {
    local dest_dir="$1"
    local dest_file="$2"
    local src_file="$3"
    local tool_name="$4"

    run mkdir -p "$dest_dir"
    if [[ -f "$dest_file" ]]; then
        ok "${tool_name} instructions already exist at ${dest_file}."
    else
        log "Writing ${tool_name} instructions..."
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] copy %s to %s\e[0m\n' "$src_file" "$dest_file"
        else
            cp "$src_file" "$dest_file"
        fi
        ok "${tool_name} instructions written to ${dest_file}."
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
