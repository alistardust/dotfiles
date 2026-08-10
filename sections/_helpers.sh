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

# True (0) when the file has exactly one BEGIN and one END marker with BEGIN
# strictly before END. Guards the splice against a hand-corrupted dest (missing,
# duplicated, or reversed markers) that would otherwise produce a garbled file.
_markers_well_formed() {
    local file="$1"
    awk -v b="$INSTRUCTIONS_MANAGED_BEGIN" -v e="$INSTRUCTIONS_MANAGED_END" '
        $0==b{nb++; if(bpos==0) bpos=NR}
        $0==e{ne++; if(epos==0) epos=NR}
        END{ exit !(nb==1 && ne==1 && bpos>0 && epos>bpos) }
    ' "$file"
}

# Print the octal permission bits of a file, or nothing (return 1) if neither
# stat dialect yields a clean octal value. Tries GNU (-c %a) then BSD (-f %Lp);
# each result is validated as octal so a wrong-dialect stat that "succeeds" with
# garbage (e.g. GNU stat treating -f as --file-system) is rejected, not chmod'd.
_file_perms() {
    local file="$1" perms
    perms="$(stat -c '%a' "$file" 2>/dev/null)"
    if [[ "$perms" =~ ^[0-7]+$ ]]; then printf '%s' "$perms"; return 0; fi
    perms="$(stat -f '%Lp' "$file" 2>/dev/null)"
    if [[ "$perms" =~ ^[0-7]+$ ]]; then printf '%s' "$perms"; return 0; fi
    return 1
}

# Replace dest's managed block with the seed's managed block, preserving every
# line outside the markers (the local-overrides section). Splices via file
# concatenation so backslashes/code samples in the content are never mangled.
_sync_managed_block() {
    local src_file="$1" dest_file="$2"
    local head tail block out perms
    # head/tail/block are scratch; out MUST live in dest's directory so the final
    # mv is a same-filesystem atomic rename (a cross-fs mv degrades to a
    # copy-then-unlink that can truncate dest and destroy local overrides).
    # The whole chain runs inside `if !` so a failure of the final mktemp (e.g.
    # dest dir not writable) is caught here rather than aborting under `set -e`.
    if ! { head="$(mktemp)" && tail="$(mktemp)" && block="$(mktemp)" \
        && out="$(mktemp "$(dirname "$dest_file")/.dotfiles-instr.XXXXXX")"; }; then
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
    if ! cat "$head" "$block" "$tail" > "$out"; then
        warn "failed to assemble managed block; leaving ${dest_file} untouched."
        rm -f "$head" "$tail" "$block" "$out"
        return 1
    fi
    # Preserve the destination's permissions across the atomic replace (mv from a
    # 0600 mktemp would otherwise reset them).
    if perms="$(_file_perms "$dest_file")"; then
        chmod "$perms" "$out" 2>/dev/null || true
    fi
    if ! mv "$out" "$dest_file"; then
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
        elif _markers_well_formed "$dest_file"; then
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
        elif grep -qxF "$INSTRUCTIONS_MANAGED_BEGIN" "$dest_file" 2>/dev/null \
            || grep -qxF "$INSTRUCTIONS_MANAGED_END" "$dest_file" 2>/dev/null; then
            warn "${tool_name} instructions at ${dest_file} have malformed managed markers (missing, duplicated, or reversed); leaving untouched. Fix the markers to a single ordered BEGIN/END pair to re-enable managed sync."
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

# -- Copilot settings.json -----------------------------------------------------
# Both the `copilot` and `copilot_skills` sections can create this file and each
# is independently opt-in, so the defaults live here to stop them drifting apart.
# Two classes of key, deliberately distinguished:
#
#   seed    written only when the key is absent, so deliberate per-machine
#           choices survive every subsequent setup run
#   enforce reasserted on every run; capabilities dotfiles genuinely owns
#
# `model` is seeded, not enforced. Rewriting it on every run silently reverted
# deliberate per-machine version pins, which is the behaviour the old
# creation-time-only guard existed to prevent. The Anthropic-primary guarantee
# is kept by verify_copilot_settings, which fails loudly on drift instead.
COPILOT_DEFAULT_MODEL="claude-opus-5"

install_copilot_settings() {
    local settings_file="${HOME}/.copilot/settings.json"

    run mkdir -p "${HOME}/.copilot"

    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] apply Copilot settings defaults to %s\e[0m\n' "$settings_file"
        return 0
    fi

    local result
    if ! result=$(python3 - "$settings_file" "$COPILOT_DEFAULT_MODEL" <<'PYEOF' 2>&1
import json
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
model = sys.argv[2]

seed = [
    (("model",), model),
    (("experimental",), True),
    (("sidebar", "showResumableSessions"), False),
]
enforce = [
    (("memory", "enabled"), True),
]


def read(data, keys):
    for key in keys[:-1]:
        data = data.get(key)
        if not isinstance(data, dict):
            return None, False
    return data.get(keys[-1]), keys[-1] in data


def write(data, keys, value):
    for key in keys[:-1]:
        nxt = data.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            data[key] = nxt
        data = nxt
    data[keys[-1]] = value


def identical(current, value):
    # Type-exact, recursively. JSON `1` must not satisfy an enforced `True`, and
    # `"false"` must not satisfy an enforced `False`, because bool is a subclass
    # of int and `1 == True` in Python. Containers recurse so that a future
    # nested default is held to the same standard as a scalar one.
    if isinstance(value, bool):
        return current is value
    if type(current) is not type(value):
        return False
    if isinstance(value, dict):
        return current.keys() == value.keys() and all(
            identical(current[k], v) for k, v in value.items()
        )
    if isinstance(value, list):
        return len(current) == len(value) and all(
            identical(c, v) for c, v in zip(current, value)
        )
    return current == value


created = not path.exists()
if created:
    data = {}
else:
    try:
        data = json.loads(path.read_text() or "{}")
    except json.JSONDecodeError as exc:
        sys.exit(f"invalid JSON: {exc}")
    if not isinstance(data, dict):
        sys.exit("settings.json is not a JSON object")

changed = []
for keys, value in seed:
    if not read(data, keys)[1]:
        write(data, keys, value)
        changed.append(".".join(keys))
for keys, value in enforce:
    current, present = read(data, keys)
    if not present or not identical(current, value):
        write(data, keys, value)
        changed.append(".".join(keys))

if created or changed:
    # Write via a temp file in the same directory then rename, so an interrupted
    # or out-of-space run cannot leave a truncated settings.json behind. Mode is
    # carried over from the existing file; new files get 0600 to match what the
    # Copilot CLI itself creates.
    mode = 0o600 if created else path.stat().st_mode & 0o777
    handle, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(json.dumps(data, indent=2) + "\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

if created:
    print("created")
elif changed:
    print("updated:" + ",".join(changed))
else:
    print("unchanged")
PYEOF
    ); then
        # Non-fatal on purpose. A hand-corrupted settings.json should not abort
        # the remaining sections under `set -e`, and verify_copilot_settings
        # fails on it, so the problem is reported rather than swallowed.
        warn "Could not apply Copilot settings defaults to ${settings_file}: ${result:-unknown error}"
        warn "Leaving ${settings_file} untouched. Fix it by hand, then re-run setup."
        return 0
    fi

    case "$result" in
        created)   ok "Created ${settings_file} (model: ${COPILOT_DEFAULT_MODEL})." ;;
        updated:*) ok "Copilot settings updated (${result#updated:})." ;;
        *)         ok "Copilot settings already correct (left unchanged)." ;;
    esac
}

# Shared by verify_copilot and verify_copilot_skills, since either section may
# have been the one to create the file. Seeded keys report neutrally when they
# have been overridden on purpose; enforced keys fail.
verify_copilot_settings() {
    local settings_file="${HOME}/.copilot/settings.json"

    if [[ ! -f "$settings_file" ]]; then
        fail "Copilot settings missing (${settings_file})"
        return 0
    fi

    # One python call reports on every key. Checks are type-exact: a string
    # "false" is not a boolean false and must not be allowed to pass. The
    # classification is done in python and only fixed tokens are handed back, so
    # a hostile or malformed model string cannot forge a verdict. The model is
    # echoed separately for display and is stripped of anything outside printable
    # ASCII, which keeps it from injecting extra lines or fields. Every
    # invocation is guarded against a non-zero exit, because `set -e` is active
    # and a bare failing command substitution would abort the whole verify run
    # instead of reporting a failed check.
    local report
    report=$(python3 - "$settings_file" <<'PYEOF' 2>/dev/null
import json
import re
import sys
from pathlib import Path

try:
    data = json.loads(Path(sys.argv[1]).read_text() or "{}")
except (OSError, ValueError):
    print("status\tinvalid")
    raise SystemExit(0)

if not isinstance(data, dict):
    print("status\tnotobject")
    raise SystemExit(0)

print("status\tok")

model = data.get("model")
print("model\t" + ("anthropic" if isinstance(model, str) and model.startswith("claude-") else "other"))
shown = model if isinstance(model, str) and model else "unset"
print("display\t" + (re.sub(r"[^\x20-\x7e]", "?", shown)[:60] or "unset"))

memory = data.get("memory")
if not isinstance(memory, dict):
    print("memory\t" + ("unset" if memory is None else "invalid"))
else:
    print("memory\t" + ("true" if memory.get("enabled") is True else "false"))

sidebar = data.get("sidebar")
if sidebar is None:
    print("sidebar\tunset")
elif not isinstance(sidebar, dict):
    print("sidebar\tinvalid")
else:
    restore = sidebar.get("showResumableSessions")
    if restore is False:
        print("sidebar\tdisabled")
    elif restore is True:
        print("sidebar\tenabled")
    elif restore is None:
        print("sidebar\tunset")
    else:
        print("sidebar\tinvalid")
PYEOF
    ) || report=$'status\tcrashed'

    local status model display memory sidebar
    status=$(printf '%s\n'  "$report" | awk -F'\t' '$1=="status"{print $2}')
    model=$(printf '%s\n'   "$report" | awk -F'\t' '$1=="model"{print $2}')
    display=$(printf '%s\n' "$report" | awk -F'\t' '$1=="display"{print $2}')
    memory=$(printf '%s\n'  "$report" | awk -F'\t' '$1=="memory"{print $2}')
    sidebar=$(printf '%s\n' "$report" | awk -F'\t' '$1=="sidebar"{print $2}')

    case "$status" in
        ok)        pass "Copilot settings present and valid JSON" ;;
        invalid)   fail "Copilot settings is not valid JSON"; return 0 ;;
        notobject) fail "Copilot settings is not a JSON object"; return 0 ;;
        *)         fail "Copilot settings could not be read"; return 0 ;;
    esac

    if [[ "$model" == "anthropic" ]]; then
        pass "Primary model is Anthropic (${display})"
    else
        fail "Primary model is not Anthropic (${display})"
    fi

    if [[ "$memory" == "true" ]]; then
        pass "Copilot memory enabled"
    else
        fail "Copilot memory not enabled"
    fi

    case "$sidebar" in
        disabled) pass "Sidebar session restore disabled" ;;
        enabled)  skip_check "Sidebar session restore enabled (per-machine override)" ;;
        unset)    skip_check "Sidebar session restore unset (CLI default: on)" ;;
        *)        fail "Sidebar session restore is not a boolean" ;;
    esac
}
