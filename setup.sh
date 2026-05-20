#!/usr/bin/env bash

# -- Bash version gate ---------------------------------------------------------
# Associative arrays require bash 4+. macOS ships bash 3.2 (/bin/bash).
# If running under bash < 4, re-exec with a newer bash if one exists.
if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
    for _candidate in /opt/homebrew/bin/bash /usr/local/bin/bash; do
        if [[ -x "$_candidate" ]] && "$_candidate" --version 2>/dev/null | grep -q 'version [4-9]'; then
            exec "$_candidate" "$0" "$@"
        fi
    done
    printf '\e[1;31mERROR: bash 4+ is required but only bash %s is available.\e[0m\n' "$BASH_VERSION" >&2
    printf 'On macOS, install a modern bash first:\n  brew install bash\n' >&2
    exit 1
fi
unset _candidate 2>/dev/null

set -euo pipefail

# Bootstrap a new machine with all personal dotfiles and tooling.
#
# Usage:
#   ./setup.sh                               # run all sections (AI CLIs excluded by default)
#   ./setup.sh --all                         # run everything, including AI CLIs
#   ./setup.sh --only zsh vim alacritty      # run only the listed sections
#   ./setup.sh --skip packages fonts         # skip the listed sections, run the rest
#   ./setup.sh --copilot                     # include copilot in the standard run
#   ./setup.sh --claude                      # include Claude Code in the standard run
#   ./setup.sh --chatgpt                     # include OpenAI Codex CLI in the standard run
#   ./setup.sh --shellgpt                    # include ShellGPT in the standard run
#   ./setup.sh --google-workspace            # include Google Workspace MCP in the standard run
#
# Sections: packages gnubin fonts tmux zsh vim alacritty wsl python keyd auto_cpufreq ddcutil copilot claude chatgpt shellgpt google_workspace copilot_skills

# -- Helpers -------------------------------------------------------------------

log()  { printf '\n\e[1;34m==> %s\e[0m\n' "$*"; }
ok()   { printf '\e[1;32m    ✓ %s\e[0m\n' "$*"; }
warn() { printf '\e[1;33mWARN: %s\e[0m\n' "$*" >&2; }

command_exists() { command -v "$1" &>/dev/null; }

DRY_RUN=false
CHECK_ONLY=false
CLONE_VIA=ssh    # ssh (default) or https; override with --https flag
_check_failed=false
_cleanup_paths=()

# Register a path for cleanup on exit (temp files/dirs).
register_cleanup() { _cleanup_paths+=("$1"); }

_global_cleanup() {
    [[ ${#_cleanup_paths[@]} -gt 0 ]] || return 0
    for p in "${_cleanup_paths[@]}"; do
        [[ -e "$p" ]] && rm -rf "$p"
    done
}
trap _global_cleanup EXIT

# In --dry-run mode, print command instead of executing it.
run() {
    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] %s\e[0m\n' "$*"
    else
        "$@"
    fi
}

# Convert a GitHub SSH URL to HTTPS when --https is active.
# Usage: git_url "git@github.com:owner/repo.git"
git_url() {
    local url="$1"
    if [[ "$CLONE_VIA" == "https" && "$url" == git@github.com:* ]]; then
        echo "https://github.com/${url#git@github.com:}"
    else
        echo "$url"
    fi
}

# Download a remote installer script, log its SHA-256, then execute.
# Usage: fetch_and_run <url> [bash_args...]
# Avoids pipe-to-shell by downloading to a temp file first.
fetch_and_run() {
    local url="$1"; shift
    local tmp_script
    tmp_script="$(mktemp)"
    register_cleanup "$tmp_script"

    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] fetch_and_run %s\e[0m\n' "$url"
        return 0
    fi

    curl -fsSL -o "$tmp_script" "$url" || { warn "Failed to download: $url"; return 1; }
    local sha256
    if command_exists sha256sum; then
        sha256="$(sha256sum "$tmp_script" | cut -d' ' -f1)"
    elif command_exists shasum; then
        sha256="$(shasum -a 256 "$tmp_script" | cut -d' ' -f1)"
    else
        sha256="(no hash tool available)"
    fi
    printf '\e[2;37m  [sha256: %s] %s\e[0m\n' "$sha256" "$url"
    bash "$tmp_script" "$@"
    rm -f "$tmp_script"
}

# --verify helpers
pass()       { printf '\e[1;32m  ✓ %s\e[0m\n' "$*"; }
fail()       { printf '\e[1;31m  ✗ %s\e[0m\n' "$*"; _check_failed=true; }
skip_check() { printf '\e[2;37m  – %s\e[0m\n' "$*"; }

# -- OS / distro detection -----------------------------------------------------

detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif grep -qiE "microsoft|wsl" /proc/version 2>/dev/null || [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
        echo "wsl"
    elif [[ "$OSTYPE" == "linux-gnu" || "$OSTYPE" == "linux-musl" ]]; then
        echo "linux"
    else
        echo "unknown"
    fi
}

detect_linux_distro() {
    if command_exists apt-get;   then echo "debian"
    elif command_exists dnf;     then echo "rhel"
    elif command_exists yum;     then echo "rhel-old"
    elif command_exists pacman;  then echo "arch"
    else                              echo "unknown"
    fi
}

# Detect OS and script location before argument parsing so defaults can be
# set correctly (e.g. gnubin defaults to enabled on macOS).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS="$(detect_os)"

# -- Argument parsing ----------------------------------------------------------

ALL_SECTIONS=(packages gnubin fonts tmux zsh vim alacritty wsl python keyd auto_cpufreq ddcutil copilot claude chatgpt shellgpt google_workspace copilot_skills)
declare -A RUN
for s in "${ALL_SECTIONS[@]}"; do RUN[$s]=true; done
RUN[copilot]=false                                    # opt-in; use --copilot or --all
RUN[claude]=false                                     # opt-in; use --claude or --all
RUN[chatgpt]=false                                    # opt-in; use --chatgpt or --all
RUN[shellgpt]=false                                   # opt-in; use --shellgpt or --all
RUN[google_workspace]=false                            # opt-in; use --google-workspace or --all
RUN[copilot_skills]=false                              # opt-in; use --skills-work / --skills-home or --all
if [[ "$OS" == "macos" ]]; then RUN[gnubin]=true; else RUN[gnubin]=false; fi  # macOS-only
if [[ "$OS" == "wsl"   ]]; then RUN[wsl]=true;   else RUN[wsl]=false;   fi   # WSL-only
if [[ "$OS" != "linux" ]]; then RUN[keyd]=false;        fi  # Linux-only (key remap daemon)
if [[ "$OS" != "linux" ]] || [[ "$OS" == "wsl" ]]; then RUN[auto_cpufreq]=false; fi  # Linux bare-metal only
if [[ "$OS" == "wsl" ]]; then RUN[ddcutil]=false; fi                                # not supported under WSL
if [[ "$(detect_linux_distro 2>/dev/null)" == "arch" ]]; then RUN[fonts]=false; fi  # Arch: fonts managed via pacman

# Copilot Skills profile selection (used by section_copilot_skills)
declare -A SKILLS_PROFILE
SKILLS_PROFILE[work]=false
SKILLS_PROFILE[home]=false

usage() {
    cat << EOF
Usage: $0 [options]

Options:
  --only <s> [s...]   Run only the listed sections
  --skip <s> [s...]   Skip the listed sections, run the rest
  --copilot           Include Copilot CLI setup (off by default)
  --claude            Include Claude Code setup (off by default)
  --chatgpt           Include OpenAI Codex CLI setup (off by default)
  --shellgpt          Include ShellGPT setup (off by default)
  --google-workspace  Include Google Workspace MCP setup (off by default)
  --skills-work       Install Copilot skills for infrastructure/work profile
  --skills-home       Install Copilot skills for personal/home profile
  --all               Run all sections including AI CLIs and MCP servers
  --dry-run           Simulate: print what would be done without making changes
  --https             Use HTTPS instead of SSH for git clones (for machines without SSH keys)
  --verify            Check post-conditions for each section (acts as test suite)
  --help              Show this help

Sections: ${ALL_SECTIONS[*]}
EOF
    exit "${1:-0}"
}

# Collect a space-separated list of section names after a flag, stopping at
# the next flag or end of args.  Sets COLLECTED (array) and SHIFT_BY (count).
collect_list() {
    COLLECTED=()
    SHIFT_BY=0
    while [[ $# -gt 0 && "$1" != --* ]]; do
        COLLECTED+=("$1")
        SHIFT_BY=$(( SHIFT_BY + 1 ))   # avoid (( )) with set -e when value is 0
        shift
    done
    [[ ${#COLLECTED[@]} -gt 0 ]] || { echo "Flag requires at least one section name." >&2; usage 1; }
}

is_valid_section() {
    local candidate="$1"
    local section
    for section in "${ALL_SECTIONS[@]}"; do
        [[ "$section" == "$candidate" ]] && return 0
    done
    return 1
}

validate_collected_sections() {
    local section
    for section in "${COLLECTED[@]}"; do
        if ! is_valid_section "$section"; then
            echo "Unknown section: $section" >&2
            usage 1
        fi
    done
}

# shellcheck disable=SC2034  # SKILLS_PROFILE is used in sections/copilot_skills.sh
while [[ $# -gt 0 ]]; do
    case "$1" in
        --only)
            shift
            collect_list "$@"
            validate_collected_sections
            for s in "${ALL_SECTIONS[@]}"; do RUN[$s]=false; done
            for s in "${COLLECTED[@]}";    do RUN[$s]=true;  done
            shift "$SHIFT_BY"
            ;;
        --skip)
            shift
            collect_list "$@"
            validate_collected_sections
            for s in "${COLLECTED[@]}"; do RUN[$s]=false; done
            shift "$SHIFT_BY"
            ;;
        --copilot) RUN[copilot]=true;                                    shift ;;
        --claude) RUN[claude]=true;                                      shift ;;
        --chatgpt) RUN[chatgpt]=true;                                    shift ;;
        --shellgpt) RUN[shellgpt]=true;                                  shift ;;
        --google-workspace) RUN[google_workspace]=true;                   shift ;;
        --skills-work) RUN[copilot_skills]=true; SKILLS_PROFILE[work]=true; shift ;;
        --skills-home) RUN[copilot_skills]=true; SKILLS_PROFILE[home]=true; shift ;;
        --all)     for s in "${ALL_SECTIONS[@]}"; do RUN[$s]=true; done;
                   SKILLS_PROFILE[work]=true; SKILLS_PROFILE[home]=true;   shift ;;
        --dry-run)  DRY_RUN=true;    shift ;;
        --https)    CLONE_VIA=https; shift ;;
        --verify)   CHECK_ONLY=true; shift ;;
        --help|-h) usage ;;
        *)         echo "Unknown option: $1" >&2; usage 1 ;;
    esac
done

should_run() { [[ "${RUN[${1}]:-false}" == "true" ]]; }


# -- Source section modules ----------------------------------------------------
for _section_file in "${SCRIPT_DIR}/sections/"*.sh; do
    # shellcheck source=/dev/null
    source "$_section_file"
done
unset _section_file

# -- Main ----------------------------------------------------------------------

log "Detected OS: ${OS}"
if [[ "$DRY_RUN" == "true" ]]; then
    log "Mode: DRY RUN  - no changes will be made"
elif [[ "$CHECK_ONLY" == "true" ]]; then
    log "Mode: VERIFY  - checking post-conditions only"
fi
log "Sections:$(for s in "${ALL_SECTIONS[@]}"; do [[ "${RUN[$s]}" == "true" ]] && printf ' %s' "$s"; done)"

dispatch() {
    if [[ "$CHECK_ONLY" == "true" ]]; then "verify_$1"; else "section_$1"; fi
}

should_run packages && dispatch packages
should_run gnubin   && dispatch gnubin

# On macOS, prepend all Homebrew GNU tool paths into PATH for this session so
# that gnu-sed (and friends) are used in subsequent sections rather than BSD tools.
# Skip in verify mode (read-only checks don't need GNU sed).
if [[ "$OS" == "macos" ]] && [[ "$CHECK_ONLY" != "true" ]] && command_exists brew; then
    _brew_prefix="$(brew --prefix)"
    for _gnu_dir in "${_brew_prefix}/opt"/*/libexec/gnubin; do
        [[ -d "$_gnu_dir" ]] && PATH="$_gnu_dir:$PATH"
    done
    export PATH
    unset _brew_prefix _gnu_dir
fi

should_run fonts         && dispatch fonts
should_run tmux          && dispatch tmux
should_run zsh           && dispatch zsh
should_run vim           && dispatch vim
should_run alacritty     && dispatch alacritty
should_run wsl           && dispatch wsl
should_run python        && dispatch python
should_run keyd          && dispatch keyd
should_run auto_cpufreq  && dispatch auto_cpufreq
should_run ddcutil       && dispatch ddcutil
should_run copilot       && dispatch copilot
should_run claude        && dispatch claude
should_run chatgpt       && dispatch chatgpt
should_run shellgpt      && dispatch shellgpt
should_run google_workspace && dispatch google_workspace
should_run copilot_skills   && dispatch copilot_skills

if [[ "$CHECK_ONLY" == "true" ]]; then
    if [[ "$_check_failed" == "true" ]]; then
        log "Verify complete  - some checks FAILED"
        exit 1
    else
        log "Verify complete  - all checks passed"
    fi
else
    log "Done! Start a new shell (or run: exec zsh -l) to apply changes."
    if ! [[ "$DRY_RUN" == "true" ]] && { should_run claude || should_run chatgpt || should_run google_workspace; }; then
        printf '\n\e[1;33m==> Manual steps required:\e[0m\n'
        if should_run claude; then
            printf '\e[1;33m  Claude Code — install Superpowers (run inside a Claude Code session):\e[0m\n'
            printf '    /plugin install superpowers@claude-plugins-official --global\n'
        fi
        if should_run chatgpt; then
            printf '\e[1;33m  Codex — install Superpowers (run inside a Codex session):\e[0m\n'
            printf '    /plugins  →  search "superpowers"  →  Install\n'
        fi
        if should_run google_workspace; then
            printf '\e[1;33m  Google Workspace MCP — configure OAuth credentials:\e[0m\n'
            printf '    1. Create a Google Cloud project with OAuth 2.0 Desktop client\n'
            printf '    2. Enable Gmail, Calendar, Drive, Docs, and Sheets APIs\n'
            printf '    3. Export GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET\n'
            printf '    4. Run: uvx workspace-mcp --tool-tier core\n'
        fi
    fi
fi
