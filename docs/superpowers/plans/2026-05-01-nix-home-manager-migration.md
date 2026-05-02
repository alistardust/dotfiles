# Nix + Home Manager Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents
> available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Migrate dotfiles management from `setup.sh` to Nix + Home Manager in-place in this repo,
starting with macOS, while keeping `setup.sh` fully intact for existing machines until Phase 10.

**Architecture:** `flake.nix` + `hosts/` + `modules/` are added to this repo alongside the
existing `setup.sh`. A thin `bootstrap.sh` installs Nix and runs `home-manager switch`. Migration
proceeds phase-by-phase; each phase is independently mergeable and leaves all machines working.
macOS (macbook) is the primary rollout target; CachyOS (cachyos-home) follows.

**Tech Stack:** Nix flakes, Home Manager, Agenix (secrets), Oh My Zsh, gpakosz/.tmux, Vim,
Alacritty, 1Password CLI (future), zsh/OMZ, uv, existing AI CLIs.

**Key decisions locked in:**
- Vim stays (no Neovim migration)
- Oh My Zsh kept via `programs.zsh.oh-my-zsh`
- gpakosz/.tmux framework kept as `home.file` managed source
- Restructure this repo in-place (no separate nix-config repo)
- macbook first rollout, then cachyos-home
- SSH agent consolidation deferred until after Phase 8

---

## Chunk 1: Phase 0 (pre-flight) + Phase 1 (Nix bootstrap)

### Task 0: Add glow to all package lists

**Files:**
- Modify: `brew_packages.txt`
- Modify: `apt-packages.txt`
- Modify: `dnf-packages.txt`
- Modify: `pacman-packages.txt`

> `glow` is a terminal markdown viewer. It belongs in package lists now (pre-Nix quick win)
> before the migration creates a new path for managing user tools.

- [ ] **Step 1: Add glow to brew_packages.txt**

  Add `glow` on its own line, in alphabetical order (after `gettext`, before `gnupg`):

  ```
  glow
  ```

- [ ] **Step 2: Add glow to apt-packages.txt and dnf-packages.txt**

  Deferred — apt and dnf support for glow (requires Charm's non-standard repo) will be
  addressed in a future pass covering Debian/Ubuntu and RHEL/Fedora platforms.

- [ ] **Step 3: Verify setup.sh --dry-run --only packages runs cleanly**

  ```bash
  ./setup.sh --dry-run --only packages
  ```

  Expected: no errors; glow appears in the package list output for the detected platform.

- [ ] **Step 4: Commit**

  ```bash
  git add brew_packages.txt pacman-packages.txt
  git commit -m "chore(packages): add glow markdown viewer to macOS and Arch package lists"
  ```

---

### Task 1: Commit remaining in-progress work and tag pre-nix-migration

**Files:** whatever is currently uncommitted in the working tree.

> The `pre-nix-migration` tag is the rollback anchor. It must point to a clean, fully-working
> state of setup.sh — no half-done work in the tag.

- [ ] **Step 1: Check what's uncommitted**

  ```bash
  git status
  git diff --stat
  ```

  Review each changed file. If there's work that isn't ready to commit, stash or finish it first.

- [ ] **Step 2: Commit any ready in-progress work**

  Commit logically grouped — don't bundle unrelated changes. Examples:

  ```bash
  # If copilot instructions were updated (these are files under ~/.copilot/, outside the repo):
  git add path/to/dotfiles-tracked-file && git commit -m "chore(copilot): update global instructions"

  # If skills were updated:
  git add <skills files> && git commit -m "chore(copilot): update superpowers skill"
  ```

- [ ] **Step 3: Run verify to confirm setup.sh is working**

  ```bash
  ./setup.sh --verify
  ```

  Expected: all enabled sections pass. Fix any failures before tagging.

- [ ] **Step 4: Tag the rollback point**

  ```bash
  git tag pre-nix-migration
  git push origin pre-nix-migration
  ```

---

### Task 2: Create flake.nix with homeConfigurations stubs

**Files:**
- Create: `flake.nix`
- Create: `hosts/macbook/default.nix`
- Create: `hosts/cachyos-home/default.nix`

> Phase 1 goal: Nix is wired up and `home-manager switch` runs successfully, but it manages
> almost nothing yet (just `programs.home-manager.enable = true`). Existing machines are
> completely unaffected.

- [ ] **Step 1: Create flake.nix**

  ```nix
  {
    description = "Alice's home-manager configuration";

    inputs = {
      nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
      home-manager = {
        url = "github:nix-community/home-manager";
        inputs.nixpkgs.follows = "nixpkgs";
      };
    };

    outputs = { nixpkgs, home-manager, ... }: {
      homeConfigurations = {
        "macbook" = home-manager.lib.homeManagerConfiguration {
          pkgs = nixpkgs.legacyPackages.aarch64-darwin;
          modules = [ ./hosts/macbook/default.nix ];
        };
        "cachyos-home" = home-manager.lib.homeManagerConfiguration {
          pkgs = nixpkgs.legacyPackages.x86_64-linux;
          modules = [ ./hosts/cachyos-home/default.nix ];
        };
      };
    };
  }
  ```

- [ ] **Step 2: Create hosts/macbook/default.nix**

  ```nix
  { ... }:
  {
    home.username = "alice";
    home.homeDirectory = "/Users/alice";
    home.stateVersion = "24.11";
    programs.home-manager.enable = true;
  }
  ```

- [ ] **Step 3: Create hosts/cachyos-home/default.nix**

  ```nix
  { ... }:
  {
    home.username = "alice";
    home.homeDirectory = "/home/alice";
    home.stateVersion = "24.11";
    programs.home-manager.enable = true;
  }
  ```

- [ ] **Step 4: Validate the flake evaluates (requires Nix installed)**

  ```bash
  nix flake check
  ```

  Expected: no errors. If Nix is not installed yet, skip this step and validate in Task 4.

- [ ] **Step 5: Commit**

  ```bash
  git add flake.nix hosts/ flake.lock
  git commit -m "feat(nix): add flake.nix with minimal homeConfiguration stubs"
  ```

---

### Task 3: Create bootstrap.sh

**Files:**
- Create: `bootstrap.sh`

> `bootstrap.sh` is the entry point for new machines. It installs Nix (Determinate Systems
> installer), then runs `home-manager switch`. It replaces `setup.sh` eventually, but for
> now both coexist. The script must be idempotent: safe to re-run on a machine that already
> has Nix installed.

- [ ] **Step 1: Create bootstrap.sh**

  ```bash
  #!/usr/bin/env bash
  set -euo pipefail

  HOSTNAME="${1:-$(hostname -s)}"

  log()  { printf '\033[0;34m==> %s\033[0m\n' "$*"; }
  ok()   { printf '\033[0;32m✓ %s\033[0m\n' "$*"; }
  warn() { printf '\033[0;33m! %s\033[0m\n' "$*"; }

  command_exists() { command -v "$1" &>/dev/null; }

  # --- Install Nix ---
  if command_exists nix; then
    ok "Nix already installed: $(nix --version)"
  else
    log "Installing Nix via Determinate Systems installer..."
    curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix \
      | sh -s -- install --no-confirm
    # Source Nix profile so nix is available in this shell
    # shellcheck source=/dev/null
    source /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
    ok "Nix installed: $(nix --version)"
  fi

  # --- Run home-manager switch ---
  log "Running home-manager switch for host: ${HOSTNAME}"
  nix run github:nix-community/home-manager/master -- switch --flake ".#${HOSTNAME}"
  ok "home-manager switch complete"
  ```

- [ ] **Step 2: Make it executable**

  ```bash
  chmod +x bootstrap.sh
  ```

- [ ] **Step 3: Dry-run test (parse check only, no Nix required)**

  ```bash
  bash -n bootstrap.sh
  ```

  Expected: no syntax errors.

- [ ] **Step 4: Commit**

  ```bash
  git add bootstrap.sh
  git commit -m "feat(nix): add bootstrap.sh -- thin Nix + home-manager entry point"
  ```

---

### Task 4: Validate Phase 1 end-to-end on macbook

> This is a live test on the macbook. The switch should succeed and manage almost nothing —
> just enough to confirm the plumbing works before adding real config in Phase 2.

- [ ] **Step 1: Run bootstrap.sh on macbook**

  ```bash
  ./bootstrap.sh macbook
  ```

  Expected:
  - Nix is installed (or skipped if already present)
  - `home-manager switch` runs and completes without errors
  - `home-manager generations | head -1` shows one generation

- [ ] **Step 2: Verify home-manager generations work**

  ```bash
  home-manager generations
  ```

  Expected: one generation listed.

- [ ] **Step 3: Verify rollback works**

  ```bash
  home-manager rollback
  home-manager switch --flake ".#macbook"
  ```

  Expected: both commands succeed. Confirms the generation mechanism is healthy.

- [ ] **Step 4: Commit validation notes (optional)**

  If any workarounds were needed (e.g., hostname didn't match), update `hosts/` or
  document in `bootstrap.sh` comments, then commit:

  ```bash
  git commit -m "fix(nix): adjust macbook host config after live validation"
  ```

---

## Chunk 2: Phase 2 (base module) + Phase 3 (shell and tmux)

### Task 5: modules/base.nix — fonts and git

**Files:**
- Create: `modules/base.nix`
- Modify: `hosts/macbook/default.nix` (add base.nix import)

> Start with the safest, most portable items: fonts and git. No platform conditionals yet.
> Alacritty is deferred to Task 6 because it needs a platform conditional.

- [ ] **Step 1: Create modules/base.nix with font packages**

  ```nix
  { pkgs, ... }:
  {
    fonts.fontconfig.enable = true;

    home.packages = with pkgs; [
      nerd-fonts.jetbrains-mono
      powerline-fonts
    ];

    programs.git = {
      enable = true;
      extraConfig = {
        core.editor = "vim";
        pull.rebase = false;
      };
    };
  }
  ```

  > Note: `nerd-fonts.jetbrains-mono` is the nixpkgs 24.x+ package name. If the build
  > fails with "attribute 'nerd-fonts' not found", use `(nerdfonts.override { fonts = [ "JetBrainsMono" ]; })`
  > instead (nixpkgs < 24.05 style).

- [ ] **Step 2: Import base.nix in macbook host**

  ```nix
  { ... }:
  {
    imports = [ ../../modules/base.nix ];

    home.username = "alice";
    home.homeDirectory = "/Users/alice";
    home.stateVersion = "24.11";
    programs.home-manager.enable = true;
  }
  ```

- [ ] **Step 3: Run home-manager switch and verify fonts are installed**

  ```bash
  home-manager switch --flake ".#macbook"
  fc-list | grep -i jetbrains
  ```

  Expected: JetBrains Mono appears in the font list.

- [ ] **Step 4: Commit**

  ```bash
  git add modules/base.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add modules/base.nix with fonts and git config"
  ```

---

### Task 6: modules/base.nix — Alacritty with platform conditional

**Files:**
- Modify: `modules/base.nix`

> `alacritty.toml` (macOS, 13.5pt) and `alacritty-linux.toml` (Linux, 10.0pt) are
> different files in this repo. Home Manager's `home.file` can select the right one
> using `pkgs.stdenv.isDarwin`. This replaces the symlink logic in `section_alacritty`.

- [ ] **Step 1: Add Alacritty home.file to base.nix**

  Add inside the `{ pkgs, ... }: { ... }` block:

  ```nix
  home.file.".config/alacritty/alacritty.toml".source =
    if pkgs.stdenv.isDarwin
    then ../terminal_configs/alacritty.toml
    else ../terminal_configs/alacritty-linux.toml;
  ```

- [ ] **Step 2: Switch and verify**

  ```bash
  home-manager switch --flake ".#macbook"
  ls -la ~/.config/alacritty/alacritty.toml
  ```

  Expected: symlink points to `terminal_configs/alacritty.toml` in the repo.

- [ ] **Step 3: Commit**

  ```bash
  git add modules/base.nix
  git commit -m "feat(nix): wire Alacritty config via home.file with platform conditional"
  ```

---

### Task 7: modules/gnubin.nix

**Files:**
- Create: `modules/gnubin.nix`
- Modify: `hosts/macbook/default.nix`

> On macOS, GNU tools (sed, awk, tar, grep, etc.) shadow the BSD variants on PATH.
> In nixpkgs, GNU tools install with their standard names (`sed`, `awk`) unlike Homebrew's
> `gsed`/`gawk`. This module replaces `section_gnubin` entirely.

- [ ] **Step 1: Create modules/gnubin.nix**

  ```nix
  { pkgs, lib, ... }:
  lib.mkIf pkgs.stdenv.isDarwin {
    home.packages = with pkgs; [
      coreutils
      findutils
      gawk
      gnugrep
      gnused
      gnutar
      gzip
    ];
  }
  ```

- [ ] **Step 2: Import gnubin.nix in macbook host**

  ```nix
  imports = [
    ../../modules/base.nix
    ../../modules/gnubin.nix
  ];
  ```

- [ ] **Step 3: Switch and verify**

  ```bash
  home-manager switch --flake ".#macbook"
  sed --version | head -1
  ```

  Expected: `sed` reports GNU sed (not BSD sed).

- [ ] **Step 4: Commit**

  ```bash
  git add modules/gnubin.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add modules/gnubin.nix -- GNU tools on macOS"
  ```

---

### Task 8: modules/shell.nix — zsh + Oh My Zsh

**Files:**
- Create: `modules/shell.nix`
- Modify: `hosts/macbook/default.nix`

> This replaces the `sed`/marker append pattern in `section_zsh`. All custom `.zshrc`
> content moves into `programs.zsh.initExtra`; OMZ is declared via `programs.zsh.oh-my-zsh`.
> The guarded block in `~/.zshrc` (`# >>> dotfiles customizations <<<`) will no longer be
> needed once this module is active.

- [ ] **Step 1: Extract current .zshrc customizations**

  Review the guarded block in `~/.zshrc` to capture what `section_zsh` currently appends:

  ```bash
  grep -A 200 '# >>> dotfiles customizations <<<' ~/.zshrc | head -100
  ```

  Also review `section_zsh` in `setup.sh` to see what it writes.

- [ ] **Step 2: Create modules/shell.nix**

  Translate the extracted zshrc content into `initExtra`. The values below are
  **structural examples only** — replace `theme`, `plugins`, and `initExtra` entirely
  with what was captured from `~/.zshrc` and `section_zsh` in Step 1. Do not commit
  placeholder values.

  ```nix
  { pkgs, ... }:
  {
    programs.zsh = {
      enable = true;

      oh-my-zsh = {
        enable = true;
        theme = "";    # set from Step 1 — check ZSH_THEME in ~/.zshrc
        plugins = [ ]; # set from Step 1 — check plugins=(...) in ~/.zshrc
      };

      initExtra = ''
        # paste the contents of the guarded block extracted in Step 1 here
      '';
    };
  }
  ```

- [ ] **Step 3: Import shell.nix in macbook host**

  ```nix
  imports = [
    ../../modules/base.nix
    ../../modules/gnubin.nix
    ../../modules/shell.nix
  ];
  ```

- [ ] **Step 4: Switch and verify zsh loads correctly**

  ```bash
  home-manager switch --flake ".#macbook"
  zsh -i -c "echo 'zsh ok'; omz version"
  ```

  Expected: no errors; OMZ version prints.

- [ ] **Step 5: Commit**

  ```bash
  git add modules/shell.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add modules/shell.nix -- zsh + Oh My Zsh via home-manager"
  ```

---

### Task 9: modules/tmux.nix — gpakosz framework

**Files:**
- Create: `modules/tmux.nix`
- Modify: `hosts/macbook/default.nix`

> gpakosz/.tmux is a custom framework, not a standard tmux plugin. It's kept as a
> `home.file` managed source; `.tmux.conf.local` becomes a static template committed
> to this repo. The sed/marker append pattern in `section_tmux` is replaced entirely.

- [ ] **Step 1: Export the current .tmux.conf.local as a static file**

  The current `~/.tmux.conf.local` has been built up by `section_tmux` over time.
  Before copying, check for any WSL-specific lines that should be conditional rather
  than baked in unconditionally:

  ```bash
  grep -n -i 'wsl\|clip\|xclip\|win32yank' ~/.tmux.conf.local
  ```

  If WSL-specific lines are found (e.g., clipboard integration using `win32yank`), wrap
  them in a shell conditional comment block so they're visible but inert on non-WSL machines:

  ```bash
  # WSL-only: uncomment on WSL machines
  # set -g @override_copy_command 'win32yank.exe -i'
  ```

  Then capture the file:

  ```bash
  cp ~/.tmux.conf.local configs/tmux.conf.local
  git add configs/tmux.conf.local
  git commit -m "chore(tmux): export current tmux.conf.local as static template"
  ```

- [ ] **Step 2: Create modules/tmux.nix**

  ```nix
  { pkgs, ... }:
  let
    gpakoszTmux = pkgs.fetchFromGitHub {
      owner = "gpakosz";
      repo = ".tmux";
      rev = "af33f07134b76134acca9d01eacbdecca9c9cda6";
      hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="; # fill in after first build
    };
  in
  {
    home.packages = [ pkgs.tmux ];

    home.file.".tmux.conf".source = "${gpakoszTmux}/.tmux.conf";
    home.file.".tmux.conf.local".source = ../configs/tmux.conf.local;
  }
  ```

  > The `hash` field is intentionally wrong. Run `home-manager switch` and Nix will
  > error with the correct hash — paste it as-is, including the `sha256-` prefix.

- [ ] **Step 3: Fill in the sha256 hash**

  Run the switch, grab the hash from the error:

  ```bash
  home-manager switch --flake ".#macbook" 2>&1 | grep 'got:'
  ```

  Paste the reported hash into `sha256` in `modules/tmux.nix`.

- [ ] **Step 4: Switch and verify**

  ```bash
  home-manager switch --flake ".#macbook"
  ls -la ~/.tmux.conf ~/.tmux.conf.local
  tmux -V
  ```

  Expected: both files are symlinks into the Nix store; `tmux` reports its version cleanly.

- [ ] **Step 5: Commit**

  ```bash
  git add modules/tmux.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add modules/tmux.nix -- gpakosz framework via home.file"
  ```

---

## Chunk 3: Phase 4 (Vim) + Phase 5 (Python)

### Task 10: modules/vim.nix — symlink ~/.vim

**Files:**
- Create: `modules/vim.nix`
- Modify: `hosts/macbook/default.nix`

> AXington/.vim repo stays as the source of truth (on the `Divine` branch). Home Manager
> symlinks the whole `~/.vim` directory. Full vim-in-Nix (plugins, config fully declarative)
> is a separate future project — deferred.

- [ ] **Step 1: Create modules/vim.nix**

  ```nix
  { pkgs, ... }:
  let
    vimConfig = pkgs.fetchFromGitHub {
      owner = "AXington";
      repo = ".vim";
      rev = "94859054788ad511442c54847df2fbc49c923b6c";
      hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="; # fill in after first build
      fetchSubmodules = true;
    };
  in
  {
    home.packages = [ pkgs.vim ];

    home.file.".vim".source = vimConfig;
    home.file.".vimrc".source = "${vimConfig}/.vimrc";
  }
  ```

- [ ] **Step 2: Run switch, fill in hash, run switch again**

  ```bash
  home-manager switch --flake ".#macbook" 2>&1 | grep 'got:'
  # paste the reported hash (including sha256- prefix) into modules/vim.nix hash field
  home-manager switch --flake ".#macbook"
  ```

- [ ] **Step 3: Verify**

  ```bash
  vim --version | head -3
  ls ~/.vim/
  ```

  Expected: vim opens cleanly with the expected plugins/config.

- [ ] **Step 4: Commit**

  ```bash
  git add modules/vim.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add modules/vim.nix -- symlink ~/.vim to AXington/.vim Divine branch"
  ```

---

### Task 11: modules/python-dev.nix

**Files:**
- Create: `modules/python-dev.nix`
- Modify: `hosts/macbook/default.nix`

> This installs `uv` via nixpkgs, installs `uv-virtualenvwrapper` as a uv tool via an
> activation hook, and wires the shell init into `initExtra`. This matches exactly what
> `section_python` in `setup.sh` does.

- [ ] **Step 1: Create modules/python-dev.nix**

  ```nix
  { pkgs, ... }:
  {
    home.packages = [ pkgs.uv ];

    home.activation.installUvVirtualenvwrapper = ''
      if [[ ! -f "$HOME/.local/bin/uv-virtualenvwrapper.sh" ]]; then
        $DRY_RUN_CMD ${pkgs.uv}/bin/uv tool install uv-virtualenvwrapper
      fi
    '';

    programs.zsh.initExtra = ''
      export WORKON_HOME="$HOME/.venvs"
      [ -f "$HOME/.local/bin/uv-virtualenvwrapper.sh" ] && \
        source "$HOME/.local/bin/uv-virtualenvwrapper.sh"
    '';
  }
  ```

- [ ] **Step 2: Import in macbook host and switch**

  ```bash
  home-manager switch --flake ".#macbook"
  zsh -i -c "workon --help"
  ```

  Expected: virtualenvwrapper commands are available.

- [ ] **Step 3: Commit**

  ```bash
  git add modules/python-dev.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add modules/python-dev.nix -- uv + virtualenvwrapper"
  ```

---

## Chunk 4: Phase 6 (AI tools)

### Task 12: modules/ai-instructions.nix — shared template

**Files:**
- Create: `modules/ai-instructions.nix`
- Modify: `hosts/macbook/default.nix` (import here, NOT inside per-tool modules)

> The three AI instruction files (`~/.copilot/copilot-instructions.md`, `~/.claude/CLAUDE.md`,
> `~/.codex/AGENTS.md`) share ~80% content. This module generates all three from a single
> Nix template to prevent drift. **Import this module at the host level only** — importing
> it inside copilot.nix, claude.nix, etc. would cause duplicate-attribute conflicts when
> multiple tool modules are active together.

- [ ] **Step 1: Identify the shared content**

  Snapshot the current files before the switch (used for verification in Step 4).
  Use `~/.dotfiles-backup/` rather than `/tmp/` so they survive a reboot between steps:

  ```bash
  mkdir -p ~/.dotfiles-backup
  cp ~/.copilot/copilot-instructions.md ~/.dotfiles-backup/copilot-instructions.md.bak
  cp ~/.claude/CLAUDE.md ~/.dotfiles-backup/CLAUDE.md.bak
  cp ~/.codex/AGENTS.md ~/.dotfiles-backup/AGENTS.md.bak
  ```

  Diff to find shared vs. tool-specific content:

  ```bash
  diff ~/.copilot/copilot-instructions.md ~/.claude/CLAUDE.md | head -60
  diff ~/.claude/CLAUDE.md ~/.codex/AGENTS.md | head -60
  ```

- [ ] **Step 2: Create modules/ai-instructions.nix**

  ```nix
  { lib, ... }:
  let
    sharedRules = ''
      # paste the shared content here (extracted from Step 1)
    '';
    copilotExtra = ''
      # paste copilot-specific additions here
    '';
    claudeExtra = ''
      # paste claude-specific additions here
    '';
    codexExtra = ''
      # paste codex-specific additions here
    '';
  in
  {
    home.file.".copilot/copilot-instructions.md".text = sharedRules + copilotExtra;
    home.file.".claude/CLAUDE.md".text = sharedRules + claudeExtra;
    home.file.".codex/AGENTS.md".text = sharedRules + codexExtra;
  }
  ```

  > Do not leave the `# paste ...` comments in the committed file. Replace them with
  > the actual content extracted in Step 1 before committing.

- [ ] **Step 3: Import ai-instructions.nix in macbook host (not in tool modules)**

  ```nix
  imports = [
    ../../modules/base.nix
    ../../modules/gnubin.nix
    ../../modules/shell.nix
    ../../modules/tmux.nix
    ../../modules/vim.nix
    ../../modules/python-dev.nix
    ../../modules/ai-instructions.nix  # import once here; never inside tool modules
  ];
  ```

- [ ] **Step 4: Switch and verify files match pre-switch snapshots**

  ```bash
  home-manager switch --flake ".#macbook"
  diff ~/.dotfiles-backup/copilot-instructions.md.bak ~/.copilot/copilot-instructions.md
  diff ~/.dotfiles-backup/CLAUDE.md.bak ~/.claude/CLAUDE.md
  diff ~/.dotfiles-backup/AGENTS.md.bak ~/.codex/AGENTS.md
  ```

  Expected: no meaningful diff (only whitespace/formatting may differ).

- [ ] **Step 5: Commit**

  ```bash
  git add modules/ai-instructions.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add modules/ai-instructions.nix -- shared AI instruction template"
  ```

---

### Task 13: modules/copilot.nix

**Files:**
- Create: `modules/copilot.nix`
- Modify: `hosts/macbook/default.nix`

- [ ] **Step 1: Create modules/copilot.nix**

  ```nix
  { pkgs, lib, ... }:
  {
    # ai-instructions.nix is imported at the host level — do NOT import it here

    home.packages = [ pkgs.gh ];

    home.file.".copilot/settings.json".text = builtins.toJSON {
      model = "claude-sonnet-4.6";
    };

    home.activation.installCopilotCli = lib.hm.dag.entryAfter ["writeBoundary"] ''
      if ! ${pkgs.gh}/bin/gh extension list 2>/dev/null | grep -q copilot; then
        $DRY_RUN_CMD ${pkgs.gh}/bin/gh extension install github/gh-copilot
      fi
    '';

    home.activation.installSuperpowers = lib.hm.dag.entryAfter ["writeBoundary"] ''
      SKILLS_DIR="$HOME/.copilot/skills/superpowers"
      if [[ ! -d "$SKILLS_DIR" ]]; then
        $DRY_RUN_CMD mkdir -p "$(dirname "$SKILLS_DIR")"
        $DRY_RUN_CMD git clone git@github.com:superpowers-community/superpowers-copilot.git "$SKILLS_DIR"
      fi
    '';
  }
  ```

- [ ] **Step 2: Switch and verify**

  ```bash
  home-manager switch --flake ".#macbook"
  cat ~/.copilot/settings.json
  ls ~/.copilot/skills/superpowers
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add modules/copilot.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add modules/copilot.nix -- Copilot CLI + settings + Superpowers"
  ```

---

### Task 14: modules/claude.nix

**Files:**
- Create: `modules/claude.nix`
- Modify: `hosts/macbook/default.nix`

> Claude Code installs via npm. gstack requires Bun. Both are handled via `home.activation`
> since they're not in nixpkgs as installable Home Manager programs. gstack installs to
> `~/.claude/skills/gstack` and is set up via its own `./setup --quiet` script.

- [ ] **Step 1: Create modules/claude.nix**

  ```nix
  { pkgs, lib, ... }:
  {
    # ai-instructions.nix is imported at the host level — do NOT import it here

    home.packages = [
      pkgs.bun
      pkgs.nodejs
    ];

    home.activation.installClaudeCli = lib.hm.dag.entryAfter ["writeBoundary"] ''
      if ! command -v claude &>/dev/null; then
        $DRY_RUN_CMD ${pkgs.nodejs}/bin/npm install -g @anthropic-ai/claude-code
      fi
    '';

    home.activation.installGstack = lib.hm.dag.entryAfter ["writeBoundary"] ''
      GSTACK_DIR="$HOME/.claude/skills/gstack"
      if [[ ! -d "$GSTACK_DIR" ]]; then
        # HTTPS intentional: SSH keys may not be configured yet at activation time
        $DRY_RUN_CMD git clone --single-branch --depth 1 \
          https://github.com/garrytan/gstack.git "$GSTACK_DIR"
        $DRY_RUN_CMD bash -c "cd '$GSTACK_DIR' && ./setup --quiet"
      fi
    '';
  }
  ```

- [ ] **Step 2: Switch and verify**

  ```bash
  home-manager switch --flake ".#macbook"
  claude --version
  command -v gstack || ls ~/.claude/skills/gstack/
  cat ~/.claude/CLAUDE.md | head -5
  ```

  Expected: `claude` reports its version; gstack directory exists; `CLAUDE.md` contains content.

- [ ] **Step 3: Commit**

  ```bash
  git add modules/claude.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add modules/claude.nix -- Claude Code + gstack via activation"
  ```

---

### Task 15: modules/chatgpt.nix and modules/shellgpt.nix

**Files:**
- Create: `modules/chatgpt.nix`
- Create: `modules/shellgpt.nix`
- Modify: `hosts/macbook/default.nix`

- [ ] **Step 1: Create modules/chatgpt.nix**

  ```nix
  { pkgs, lib, ... }:
  {
    # ai-instructions.nix is imported at the host level — do NOT import it here

    home.packages = [ pkgs.nodejs ];

    home.activation.installCodexCli = lib.hm.dag.entryAfter ["writeBoundary"] ''
      if ! command -v codex &>/dev/null; then
        $DRY_RUN_CMD ${pkgs.nodejs}/bin/npm install -g @openai/codex
      fi
    '';
  }
  ```

- [ ] **Step 2: Create modules/shellgpt.nix**

  ```nix
  { pkgs, lib, ... }:
  {
    home.packages = [ pkgs.uv ];  # uv already in python-dev.nix; harmless to repeat

    home.activation.installShellGpt = lib.hm.dag.entryAfter ["writeBoundary"] ''
      if ! command -v sgpt &>/dev/null; then
        $DRY_RUN_CMD ${pkgs.uv}/bin/uv tool install shell-gpt
      fi
    '';
  }
  ```

- [ ] **Step 3: Switch and verify all three outputs**

  ```bash
  home-manager switch --flake ".#macbook"
  codex --version
  sgpt --version
  cat ~/.codex/AGENTS.md | head -5
  ```

  Expected: both CLIs report versions; `AGENTS.md` contains content (written by `ai-instructions.nix`).

- [ ] **Step 4: Commit**

  ```bash
  git add modules/chatgpt.nix modules/shellgpt.nix hosts/macbook/default.nix
  git commit -m "feat(nix): add chatgpt and shellgpt modules"
  ```

---

## Chunk 5: Phase 7–10 (system-level, 1Password, Agenix, retire setup.sh)

> Phases 7–10 are outlined here at medium granularity. Detail each task fully when
> you are about to execute it — by then the earlier phases will have revealed
> any surprises that affect the approach.

### Phase 7: System-level modules (keyd, auto_cpufreq)

These write to `/etc/` and manage systemd services. They are **NOT Home Manager scope**.

> **Constraint:** Do NOT put keyd or auto_cpufreq in any Home Manager module.

- [ ] Create `scripts/setup-system-linux.sh` by extracting `section_keyd` and
  `section_auto_cpufreq` logic from `setup.sh` verbatim. (`configs/keyd.conf` stays
  in the repo unchanged.)
- [ ] Add a Linux dispatch call in `bootstrap.sh`:
  ```bash
  if [[ "$(uname)" == "Linux" ]]; then
    ./scripts/setup-system-linux.sh
  fi
  ```
- [ ] Verify on cachyos-home: `systemctl is-active keyd && systemctl is-active auto-cpufreq`

**Future NixOS path** (when/if migrating cachyos-home to NixOS — out of scope for this plan):
- `services.keyd.enable = true;` in `configuration.nix`
- `services.auto-cpufreq.enable = true;` in `configuration.nix`

---

### Phase 8: 1Password

**pre-Nix (can land in parallel with any earlier phase):**
- [ ] `brew_packages.txt`: add `1password-cli`
- [ ] `pacman-packages.txt`: add `1password-cli` (available in Arch repos)
- [ ] apt/dnf: deferred (same pattern as glow — non-standard repos)

**Nix module (`modules/onepassword.nix`):**
- [ ] Create `modules/onepassword.nix`:
  ```nix
  { pkgs, ... }:
  {
    home.packages = [ pkgs._1password-cli ];
    programs.zsh.initExtra = ''
      eval "$(op completion zsh)"; compdef _op op
    '';
  }
  ```
- [ ] Import in macbook host; run `home-manager switch --flake ".#macbook"`
- [ ] Verify: `op --version`

**Agenix bootstrap (Phase 8 enhancement):**
- [ ] Add to `bootstrap.sh` before the `home-manager switch` call:
  ```bash
  op read "op://Personal/agenix-age-key/private key" > ~/.config/agenix/key.txt
  chmod 600 ~/.config/agenix/key.txt
  ```

> **SSH agent consolidation:** Deferred. Do a dedicated SSH key audit first;
> then plan 1Password agent integration separately.

---

### Phase 9: Agenix secrets

- [ ] Identify secrets vs. config:
  - SSH keys, API tokens → Agenix (age key stored in 1Password)
  - Work-context AI instructions (if sensitive) → Agenix
- [ ] Create `secrets/secrets.nix` with public key declarations for each machine
- [ ] Encrypt each secret: `agenix -e secrets/<name>.age`
- [ ] Wire into home-manager via `age.secrets.<name>.file`; run `home-manager switch`
- [ ] Verify: confirm each secret appears at its expected path with correct permissions
  ```bash
  # Note: `home-manager option` output format varies by version — validate this command
  # against your HM version before running. Fall back to manual `ls -la <path>` if needed.
  ls -la $(home-manager option age.secrets | grep path | awk '{print $2}')
  age --decrypt -i ~/.config/agenix/key.txt secrets/<name>.age
  ```
- [ ] Bootstrap flow smoke test on a fresh shell: `op signin` → run `bootstrap.sh` →
  confirm `home-manager switch` decrypts secrets successfully → shred key file:
  ```bash
  shred -u ~/.config/agenix/key.txt
  ```

---

### Phase 10: Retire setup.sh

- [ ] Confirm all machines are running Home Manager and all sections are covered
- [ ] Move `setup.sh` to `archive/setup.sh` (keeps git history, clearly out of PATH):
  ```bash
  mkdir -p archive
  git mv setup.sh archive/setup.sh
  git commit -m "chore: archive setup.sh -- all machines on home-manager"
  ```
- [ ] Update `README.md`:
  - New machines: `./bootstrap.sh <hostname>`
  - Note `archive/setup.sh` kept for historical reference
- [ ] Final verification: `./bootstrap.sh macbook` on a clean shell completes without errors

---

## Open decisions (resolved)

| Decision | Choice |
|----------|--------|
| Vim vs Neovim | **Stay with Vim** — `home.file` symlink to AXington/.vim (`Divine` branch) |
| Oh My Zsh | **Keep OMZ** via `programs.zsh.oh-my-zsh` (theme + plugins + initExtra) |
| gpakosz/.tmux | **Keep framework** as `home.file` managed source; static `.tmux.conf.local` |
| Repo structure | **Restructure in-place** — no separate nix-config repo |
| Rollout target | **macbook first** (simpler, no system-level services) |
| glow | **Add to package lists now** (pre-Nix quick win) |
| SSH agent | **Defer** until after Phase 8 (1Password) is stable |
