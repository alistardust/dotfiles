# Dotfiles Migration Plan: setup.sh -> Nix + Home Manager + Agenix

## Problem statement

The current `setup.sh` approach uses grep-for-marker / sed-in-place / append-block
patterns to manage dotfiles across machines. This is fragile, has no visibility into
what would change before applying, and cannot safely handle machines that have drifted
from the desired state. The goal is to replace the configuration management layer with
Nix + Home Manager, while keeping a thin shell bootstrap for pre-reqs.

## Current state (as of 2026-05-01)

`setup.sh` has 15 sections:
`packages gnubin fonts tmux zsh vim alacritty wsl python keyd auto_cpufreq copilot claude chatgpt shellgpt`

New since original plan (from upstream commits c5abdf9 / 062f9a7 / 775cd69 / aa00e1a):
- **keyd** (section 10): Linux key-remapping daemon; writes `/etc/keyd/default.conf` (system-level)
- **auto_cpufreq** (section 11): Linux CPU freq scaling; installs/enables systemd service (system-level)
- **copilot** (section 12): now also writes `~/.copilot/settings.json` (preferred model) and
  installs the Superpowers community plugin (`~/.copilot/skills/superpowers`)
- **claude** (section 13): Claude Code CLI + writes `~/.claude/CLAUDE.md` global instructions;
  installs gstack (requires Bun) and wires it to both Claude and Codex hosts
- **chatgpt** (section 14): OpenAI Codex CLI via npm + writes `~/.codex/AGENTS.md` global instructions
- **shellgpt** (section 15): shell-gpt via `uv tool install`
- Three AI instruction files (`~/.copilot/copilot-instructions.md`, `~/.claude/CLAUDE.md`,
  `~/.codex/AGENTS.md`) share ~80% content -- good candidate for a single Nix template
- `CLAUDE.md` and `AGENTS.md` added at repo root (for Claude Code / Codex project context)
- Alacritty config is now split: `alacritty.toml` (macOS, 13.5pt), `alacritty-linux.toml` (Linux, 10.0pt)

## Target architecture

```
bootstrap.sh              # thin: installs Nix, then runs home-manager switch
flake.nix                 # Nix flake -- the entry point
hosts/
  macbook/default.nix     # macOS work laptop: base + gnubin + python + copilot + claude
  cachyos-home/default.nix  # CachyOS desktop: base + keyd + auto-cpufreq + claude + chatgpt
  <future>/default.nix
modules/
  base.nix                # always: zsh, tmux, vim, alacritty, fonts
  gnubin.nix              # GNU tools shadowing BSD on macOS (collapsed to package list)
  python-dev.nix          # uv, virtualenvwrapper, base venv packages
  copilot.nix             # Copilot CLI + instructions + settings.json + Superpowers skill
  claude.nix              # Claude Code + ~/.claude/CLAUDE.md + gstack (needs Bun)
  chatgpt.nix             # Codex CLI (npm) + ~/.codex/AGENTS.md + gstack codex host
  shellgpt.nix            # shell-gpt via uv tool install
  work.nix                # work-context tooling (no org-specific content in repo)
  secrets.nix             # Agenix secret declarations
  ai-instructions.nix     # shared template -> copilot-instructions.md + CLAUDE.md + AGENTS.md
secrets/
  <machine>.age           # encrypted per-machine secrets (committed)
  secrets.nix             # which public keys can decrypt which secrets
```

Key principles:
- Each host file is minimal: just a list of module imports + machine-specific values
- Machine-specific values (hostname, work vs personal, optional modules) live in the
  host file, not in modules. Modules must be unconditionally usable.
- Secrets (API tokens, SSH keys) are encrypted with Agenix; plaintexts never committed.
- `home-manager switch` is always safe: shows a diff, applies atomically, supports rollback.
- `keyd` and `auto_cpufreq` write to system paths (`/etc/`) -- these belong in system
  modules (nix-darwin / NixOS), NOT Home Manager (user-level only). On non-NixOS Linux
  (CachyOS), a thin wrapper script remains acceptable until a NixOS or nix-darwin path exists.

## Migration phases

### Phase 0: Commit current state, tag it

- [x] Commit tmux mouse mode
- [x] Commit alacritty platform font split (13.5 macOS / 10.0 Linux)
- [ ] Commit remaining in-progress work (glow, copilot instructions update, skills)
- [ ] Tag `pre-nix-migration` so there is a clean rollback point

### Phase 1: Nix bootstrap (new machines can use Nix; old machines unchanged)

- Add `bootstrap.sh` (entry point for new machines)
  - Installs Nix via Determinate Systems installer
  - Installs home-manager as a flake input
  - Runs `home-manager switch --flake .#<hostname>`
- Add `flake.nix` with minimal homeConfigurations stubs for macbook + cachyos-home
- Keep `setup.sh` fully intact -- existing machines are unaffected

### Phase 2: Base module (safest first pass)

Migrate pure symlinks and files with no machine-specific variation:

- `modules/base.nix`:
  - Alacritty: `home.file` symlink to platform-correct toml (13.5 macOS / 10.0 Linux)
    using `pkgs.stdenv.isDarwin` condition; eventually `programs.alacritty` when stable
  - Powerline/Nerd fonts via `fonts.fontconfig` + font packages
  - Git config basics
- `modules/gnubin.nix`:
  - GNU tools on macOS via `home.packages` -- collapses `section_gnubin` entirely
  - nixpkgs GNU tools install with unadorned names (`sed`, `awk`) unlike Homebrew's `gsed`/`gawk`
- Validate on one machine before rolling out

### Phase 3: Shell and tmux

- `programs.zsh`:
  - Oh My Zsh managed by Home Manager (`programs.zsh.oh-my-zsh`)
  - `programs.zsh.initExtra` replaces the sed/marker `.zshrc` append pattern
  - ssh(), aws() focus-events wrappers, kubectl/helm completions, fzf, uv, WORKON_HOME
- `programs.tmux` / gpakosz framework:
  - gpakosz/.tmux is a custom framework, not a standard tmux plugin
  - Keep as `home.file` managed source initially; `.tmux.conf.local` becomes a static
    template (mouse mode, prefix, bindings no longer need sed)
  - WSL-specific overrides move to a conditional block in the template

### Phase 4: Vim

- AXington/.vim repo stays as source of truth (now on `Divine` branch, not `heavenly`)
- Use `home.file` to symlink the whole `~/.vim` dir initially
- Full vim-in-Nix (plugins, config) is its own project; deferred

### Phase 5: Python environment

- `modules/python-dev.nix`:
  - `home.packages = [ pkgs.uv ]`
  - uv-virtualenvwrapper init in `programs.zsh.initExtra`
  - Base virtualenv creation: shell hook or post-switch activation script

### Phase 6: Optional modules -- AI tools

The three AI instruction files share ~80% content. Build from a single template in
`modules/ai-instructions.nix`, write each tool's variant via `home.file`.

- `modules/copilot.nix`:
  - Copilot CLI binary
  - `home.file.".copilot/copilot-instructions.md"` from shared AI template
  - `home.file.".copilot/settings.json"` with preferred model
  - `home.file.".copilot/skills/superpowers"` -- Superpowers plugin (curl | bash install;
    may need a fetchurl derivation or post-switch hook)
- `modules/claude.nix`:
  - Claude Code (`claude` CLI)
  - `home.file.".claude/CLAUDE.md"` from shared AI template
  - gstack: requires Bun -- add `pkgs.bun` to `home.packages`; clone + setup as
    `home.activation` hook
- `modules/chatgpt.nix`:
  - Codex CLI via npm (`@openai/codex`) -- `home.packages` with `pkgs.nodePackages`
    or overlay; or keep npm global install via `home.activation`
  - `home.file.".codex/AGENTS.md"` from shared AI template
  - Wire gstack codex host if claude module also enabled
- `modules/shellgpt.nix`:
  - `home.packages = [ pkgs.shell-gpt ]` (available in nixpkgs) or uv tool install
    via activation hook if nixpkgs version is stale
- `work.nix`:
  - --work flag becomes a boolean module option or a separate `work.nix` import
  - Work-specific Copilot instructions appended from a separate (possibly Agenix-encrypted) file

### Phase 7: System-level modules (keyd, auto_cpufreq)

These write to `/etc/` and manage systemd services -- they are system-level, not user-level.

- On NixOS (future): `services.keyd` and `services.auto-cpufreq` in `configuration.nix`
- On CachyOS (Arch, non-NixOS): keep as thin wrapper scripts called from `bootstrap.sh`
  until a NixOS path exists. Do NOT put these in Home Manager.
- `configs/keyd.conf` stays in the repo; `bootstrap.sh` copies it and enables the service
  on Linux bare-metal (same approach as today, just separated from `setup.sh`)

### Phase 8: 1Password

**Goal:** `op` CLI available on all machines, GUI app installed where appropriate,
shell integration in place, and a clear path to using 1Password as the Agenix key
store in Phase 8.

#### Dotfiles / setup.sh (pre-Nix, can land now)

- Add `1password-cli` to `brew_packages.txt` (macOS)
- Add install notes to `apt-packages.txt` / `dnf-packages.txt` / `pacman-packages.txt`:
  - Ubuntu/Debian: official apt repo (not in default apt)
  - CachyOS/Arch: AUR `1password-cli`
  - Note: `section_packages()` installs from the text files; package manager quirks
    may need a dedicated `section_1password()` for non-standard repos (like the apt case)
- 1Password GUI app:
  - macOS: Homebrew cask (`1password`) -- add to a casks list if one exists, or document
  - CachyOS: AUR `1password` or Flatpak -- system-level, out of scope for Home Manager

#### Nix module (`modules/onepassword.nix`)

```nix
{ config, pkgs, lib, ... }:
{
  home.packages = [ pkgs._1password-cli ];

  # Shell completions wired automatically via programs.zsh
  programs.zsh.initExtra = ''
    # 1Password CLI completions
    eval "$(op completion zsh)"; compdef _op op
  '';

  # Optional: configure op-agent socket for SSH (see SSH agent note below)
  # home.sessionVariables.SSH_AUTH_SOCK = "$HOME/.1password/agent.sock";
}
```

- macOS: `pkgs._1password-cli` is available in nixpkgs; GUI app stays as a cask (system)
- CachyOS: same nixpkgs package; GUI app stays as AUR/Flatpak (system)
- Add to `modules/base.nix` imports OR make it a per-host opt-in (probably opt-in,
  since it requires an account)

#### SSH agent: hybrid approach (deferred)

1Password has a built-in SSH agent that serves keys from the vault. Full adoption
requires consolidating SSH keys into the vault and pointing `SSH_AUTH_SOCK` at the
1Password socket. This intersects with work SSH setup complexity -- defer until a
dedicated SSH key audit is done.

Planned state (future):
- Personal keys: store in 1Password vault, serve via `~/.1password/agent.sock`
- Work keys: TBD -- depends on work SSH setup complexity
- `~/.ssh/config` `IdentityAgent` stanza will select the right agent per host

#### Agenix integration (Phase 8 enhancement)

The Agenix age private key can be stored in 1Password instead of on disk:

```bash
# bootstrap.sh, before home-manager switch:
op read "op://Personal/agenix-age-key/private key" > ~/.config/agenix/key.txt
chmod 600 ~/.config/agenix/key.txt
```

This means the only credential needed to bootstrap a new machine from scratch is
a 1Password sign-in -- all other secrets flow from there. Plan this integration
during Phase 8, not before.

#### LastPass migration

LastPass is currently only used in the browser on personal machines. The data
migration (export from LastPass, import to 1Password) is a separate personal task
and does not need to be tracked here. When ready: LastPass CSV export → 1Password
importer tool → verify → disable LastPass browser extension.

### Phase 9: Agenix secrets

- Identify secrets vs config:
  - SSH keys, API tokens: Agenix (age key stored in 1Password -- see Phase 8)
  - Work-context AI instructions (if sensitive): Agenix
- Set up `secrets/secrets.nix` with public key declarations
- Encrypt existing secrets and wire into home-manager via `age.secrets`
- Bootstrap flow: `op signin` → `op read` age key to disk → `home-manager switch`
  → shred key file after switch completes

### Phase 10: Retire setup.sh

- Once all machines are running Home Manager, `setup.sh` is reduced to `bootstrap.sh`
- Keep archived read-only copy for reference
- Update README

## What setup.sh currently does vs. where it goes

| Section | Current | Target |
|---------|---------|--------|
| packages | brew/apt/dnf/pacman | system pkg mgr stays; user tools -> `home.packages` |
| gnubin | symlink loop + PATH | `modules/gnubin.nix` (5 lines) |
| fonts | clone + install script | `fonts.fontconfig` + font packages |
| tmux | sed/append .tmux.conf.local | `home.file` for gpakosz + static .tmux.conf.local |
| zsh | sed + append markers | `programs.zsh` with `initExtra` |
| vim | git clone + submodules | `home.file` symlinks initially |
| alacritty | platform symlink | `home.file` with `isDarwin` condition |
| wsl | sed/append configs | WSL conditional in templates |
| python | uv install + venv | `modules/python-dev.nix` |
| keyd | cp config + systemctl | system-level; stays in bootstrap.sh for Arch |
| auto_cpufreq | install + systemctl | system-level; stays in bootstrap.sh for Arch |
| copilot | write instructions + settings | `modules/copilot.nix` |
| claude | install + write CLAUDE.md + gstack | `modules/claude.nix` |
| chatgpt | install codex + write AGENTS.md | `modules/chatgpt.nix` |
| shellgpt | uv tool install | `modules/shellgpt.nix` |
| 1password | manual / not managed | `modules/onepassword.nix` + cask/AUR for GUI |

## Decisions still needed

- [x] Stay with vim or migrate to neovim? → **Stay with Vim** (`home.file` symlink to AXington/.vim, `Divine` branch)
- [x] Stay with Oh My Zsh or move to something Home Manager manages natively? → **Keep OMZ** via `programs.zsh.oh-my-zsh`
- [x] Keep gpakosz/.tmux framework or use `programs.tmux` with custom config? → **Keep gpakosz** as `home.file` managed source; `.tmux.conf.local` becomes a static file
- [x] Password manager: **1Password** (decided; LastPass migration is a separate personal task)
- [x] Which machines are Phase 1 rollout targets? → **macbook first** (simpler, no system-level services)
- [x] Same repo restructured, or new `nix-config` repo + dotfiles stays for non-Nix files? → **Restructure in-place**
- [x] How to handle glow/md viewer: add to `brew_packages.txt`+package lists now, or defer to Phase 2? → **Add to package lists now** (pre-Nix quick win)
- [ ] SSH agent consolidation: when to move personal SSH keys into 1Password vault? → **Deferred until after Phase 8** (1Password) is stable

## What does NOT move to Nix

- OS-level packages (kernel, drivers, system libs): pacman on CachyOS, Homebrew casks for GUI apps
- WSL Windows-side setup (PowerShell script stays)
- Remote VM setup scripts (Fabric still useful here)
- `keyd` and `auto_cpufreq` until a NixOS or nix-darwin path is viable

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Breaking a working machine mid-migration | Phase-by-phase; setup.sh stays intact until Phase 9 |
| Nix store growing large | `nix-collect-garbage -d` periodically; accept the tradeoff |
| gpakosz/.tmux not playing nicely with Nix | Keep as `home.file` source initially |
| CachyOS + Nix friction (Arch-specific) | Test on a VM first; Determinate Systems handles most of it |
| gstack Bun dependency not in nixpkgs | Use `home.activation` hook for git clone + setup |
| Superpowers plugin install is curl/bash | Wrap in `home.activation` or pre-built fetchurl derivation |
| Three AI instruction files diverging | Build all three from shared `ai-instructions.nix` template |
| 1Password apt repo not in standard lists | May need dedicated `section_1password()` for non-standard apt repo |
| SSH agent consolidation scope creep | Explicitly deferred; tracked as an open decision |
| Learning curve during active work period | Do phases 1-2 first, pause, continue when time allows |
