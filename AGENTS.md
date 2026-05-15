# Agent Instructions

## Commands

```bash
./setup.sh                              # run all default sections
./setup.sh --only zsh vim               # run only specific sections
./setup.sh --skip packages fonts        # skip sections, run the rest
./setup.sh --dry-run --only tmux        # simulate a section without changes
./setup.sh --verify                     # check post-conditions (acts as test suite)
./setup.sh --verify --only zsh          # verify a single section
./setup.sh --copilot                    # standard run + GitHub Copilot CLI
./setup.sh --claude                     # standard run + Claude Code CLI
./setup.sh --chatgpt                    # standard run + OpenAI Codex CLI
./setup.sh --shellgpt                   # standard run + ShellGPT
./setup.sh --google-workspace           # standard run + Google Workspace MCP
./setup.sh --all                        # everything, including all AI CLIs
```

Sections: `packages gnubin fonts tmux zsh vim alacritty wsl python keyd auto_cpufreq copilot claude chatgpt shellgpt google_workspace`

Use `--dry-run --only <section>` to preview changes and `--verify --only <section>` as the nearest equivalent to a unit test for one area.

## Architecture

`setup.sh` is the single entry point containing all bootstrap logic. It:

1. Detects OS (`macos`, `wsl`, `linux`) and Linux distro (debian/rhel/arch) early in the script.
2. Builds a `RUN[section]=true/false` associative array based on platform defaults and CLI flags.
3. Runs either `section_<name>` functions (normal mode) or `verify_<name>` functions (`--verify` mode) for each enabled section.

The package list files (`brew_packages.txt`, `apt-packages.txt`, `dnf-packages.txt`, `pacman-packages.txt`) are pure data — `setup.sh` selects the right file for the detected platform.

Most other tracked files are artifacts consumed by setup: `terminal_configs/` for appearance, `vscode/` and `idea_ides/` for editor exports, `configs/keyd.conf` for the key remapping daemon, and `wslconfig.template` plus `terminal_configs/windows-terminal-settings.json` for Windows-side WSL setup.

## Key Conventions

**Idempotency:** Every section checks before acting. Setup is safe to re-run; add similar guards when extending sections.

**Config file strategy:** The script appends guarded blocks (e.g., `# >>> dotfiles customizations <<<`) to `~/.zshrc`, `~/.tmux.conf.local`, and `~/.vimrc.local` — it never replaces these files wholesale. `verify_*` functions check for the presence of these markers. Preserve this pattern.

**Shared vs. machine-local:** Shared artifacts like `terminal_configs/alacritty.toml` are symlinked into place. Machine-local files like `~/.vimrc.local` are copied then patched. Don't collapse this distinction.

**Platform defaults:** `copilot`, `claude`, `chatgpt`, and `shellgpt` are opt-in (off by default). `gnubin` is macOS-only. `wsl` is WSL2-only. `keyd` and `auto_cpufreq` are Linux bare-metal only. Preserve these defaults when adding new sections.

**Adding a section:** Add it to `ALL_SECTIONS` in `setup.sh`, implement `section_<name>()` and `verify_<name>()`, set a default in the `RUN[]` block, and use SSH remotes (`git@github.com:...`) for any new cloned dependencies.

**Terminal appearance:** Keep `terminal_configs/alacritty.toml` (macOS, font size 13.5), `terminal_configs/alacritty-linux.toml` (Linux/WSL, font size 10.5), and `terminal_configs/windows-terminal-settings.json` in sync for color scheme and font family. The two alacritty files are identical except for font size — color/font family changes must be applied to both.

## Bash Conventions (this repo)

- Use `run()` for all state-changing commands — it no-ops in `--dry-run` mode.
- Output: `log()` for section headers, `ok()` for success, `warn()` for non-fatal issues. In `--verify` mode: `pass()`, `fail()`, `skip_check()`.
- Use `command_exists()` to check for a tool — never bare `which` or `hash`.
- Guard every install with an existence check first (all sections must be idempotent).
- Always quote variable expansions: `"$var"`, `"${array[@]}"`. Use `[[ ]]` not `[ ]`.
- SSH remotes for all `git clone` calls: `git@github.com:...`.

## Commit Style

Conventional Commits: `<type>[scope]: <description>` (imperative mood, ≤72 chars). One logical change per commit; every commit must leave the repo in a working state. Branch naming: `feature/description`, `fix/description`, `chore/description`.
