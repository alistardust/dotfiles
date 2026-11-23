# shellcheck shell=bash
# Section: cloud_tools
# shellcheck disable=SC2015

# -- Cloud tools (gcloud, GKE auth plugin, kubectl, helm, tfenv) ---------------
# macOS gets gcloud-cli, kubernetes-cli, helm and tfenv from brew_packages.txt;
# this section only adds the GKE auth plugin there. Linux has no single source,
# so each tool comes from the channel its vendor documents for that distro.
#
# Every helper returns non-zero on failure and section_cloud_tools turns that
# into a warning. Note that set -e does not apply inside a function called from
# an || list, so each helper checks its own commands explicitly.

GCLOUD_APT_KEY_URL="https://packages.cloud.google.com/apt/doc/apt-key.gpg"
GCLOUD_APT_KEYRING="/usr/share/keyrings/cloud.google.gpg"
GCLOUD_APT_LIST="/etc/apt/sources.list.d/google-cloud-sdk.list"
GCLOUD_YUM_REPO="/etc/yum.repos.d/google-cloud-sdk.repo"
GCLOUD_TARBALL_BASE="https://dl.google.com/dl/cloudsdk/channels/rapid/downloads"
GCLOUD_USER_SDK="$HOME/google-cloud-sdk"
GCLOUD_REPO_PACKAGES=(google-cloud-cli google-cloud-cli-gke-gcloud-auth-plugin kubectl)
HELM_INSTALL_SCRIPT_URL="https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4"
TFENV_DIR="$HOME/.tfenv"

_cloud_brew_prefix() {
    brew --prefix 2>/dev/null || echo "/opt/homebrew"
}

# Directories an install method can put cloud binaries in, beyond PATH.
# Setup runs in a shell that may predate the PATH changes it makes.
_cloud_bin_dirs() {
    printf '%s\n' \
        "$(_cloud_brew_prefix)/share/google-cloud-sdk/bin" \
        "$GCLOUD_USER_SDK/bin" \
        /usr/lib/google-cloud-sdk/bin \
        /usr/lib64/google-cloud-sdk/bin \
        "$HOME/.local/bin"
}

# Print the path of a cloud tool, checking PATH and then the install dirs.
_cloud_tool_path() {
    local tool="$1" dir
    if command_exists "$tool"; then
        command -v "$tool"
        return 0
    fi
    while IFS= read -r dir; do
        if [[ -x "$dir/$tool" ]]; then
            printf '%s\n' "$dir/$tool"
            return 0
        fi
    done < <(_cloud_bin_dirs)
    return 1
}

# Directories on PATH for every shell, not just interactive zsh. The SDK's own
# bin dir is only added by .zshrc, which scripts, kubectl exec plugins and
# agent shells never read, so tools must also be linked into one of these.
_shared_bin_dirs() {
    printf '%s\n' \
        "$(_cloud_brew_prefix)/bin" \
        /usr/local/bin \
        /usr/bin \
        "$HOME/.local/bin"
}

# Print the path of a tool reachable from a shared bin dir. Ignores the
# current PATH on purpose: setup often runs from a shell that has .zshrc's.
_shared_tool_path() {
    local tool="$1" dir
    while IFS= read -r dir; do
        if [[ -x "$dir/$tool" ]]; then
            printf '%s\n' "$dir/$tool"
            return 0
        fi
    done < <(_shared_bin_dirs)
    return 1
}

# Symlink target to link, idempotently. An optional third argument "sudo"
# creates the link as root, for system bin dirs.
_link_tool() {
    local target="$1" link="$2" as_root="${3:-}"
    local -a ln_cmd=(ln -s)
    [[ "$as_root" == "sudo" ]] && ln_cmd=(sudo ln -s)
    if [[ "$(readlink "$link" 2>/dev/null)" == "$target" ]]; then
        ok "${link} already links to ${target}"
    elif [[ -e "$link" || -L "$link" ]]; then
        warn "${link} exists and does not link to ${target}; leaving it." \
            "Remove it and re-run to relink."
        return 1
    elif [[ "$DRY_RUN" != "true" && ! -x "$target" ]]; then
        warn "${target} not found; cannot link ${link}"
        return 1
    else
        run "${ln_cmd[@]}" "$target" "$link"
    fi
}

_os_release_field() {
    local field="$1"
    [[ -r /etc/os-release ]] || return 1
    # shellcheck source=/dev/null
    (. /etc/os-release && printf '%s\n' "${!field:-}")
}

# For SDK installs that own their component manager (Homebrew cask, tarball).
# Package-manager installs disable components, so they use a package instead.
_install_gke_auth_plugin_component() {
    local gcloud_bin="$1"
    if _cloud_tool_path gke-gcloud-auth-plugin >/dev/null; then
        ok "gke-gcloud-auth-plugin already installed"
        return 0
    fi
    if [[ "$DRY_RUN" != "true" && ! -x "$gcloud_bin" ]]; then
        warn "gcloud not found at ${gcloud_bin}; skipping gke-gcloud-auth-plugin"
        return 1
    fi
    run "$gcloud_bin" components install gke-gcloud-auth-plugin --quiet
}

_add_gcloud_apt_repo() {
    if [[ -f "$GCLOUD_APT_LIST" ]]; then
        ok "Google Cloud apt repository already configured"
        return 0
    fi
    log "Adding Google Cloud apt repository..."
    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] write %s and %s\e[0m\n' \
            "$GCLOUD_APT_KEYRING" "$GCLOUD_APT_LIST"
        return 0
    fi
    local key_file
    key_file="$(mktemp)" || return 1
    register_cleanup "$key_file"
    curl -fsSL -o "$key_file" "$GCLOUD_APT_KEY_URL" || return 1
    sudo gpg --dearmor --yes -o "$GCLOUD_APT_KEYRING" "$key_file" || return 1
    # The list file is the idempotency guard, so write it only after the key.
    printf 'deb [signed-by=%s] https://packages.cloud.google.com/apt cloud-sdk main\n' \
        "$GCLOUD_APT_KEYRING" | sudo tee "$GCLOUD_APT_LIST" >/dev/null
}

_install_gcloud_debian() {
    _add_gcloud_apt_repo || return 1
    run sudo apt-get update -y || return 1
    run sudo apt-get install -y "${GCLOUD_REPO_PACKAGES[@]}" || return 1
    _link_packaged_auth_plugin
}

# Google publishes separate el9 (RHEL 7-9) and el10 repos, each with its own key.
_gcloud_yum_repo_content() {
    local version_id release key arch
    version_id="$(_os_release_field VERSION_ID)" || return 1
    case "$(uname -m)" in
        x86_64)        arch="x86_64" ;;
        aarch64|arm64) arch="aarch64" ;;
        *) warn "unsupported architecture for gcloud: $(uname -m)"; return 1 ;;
    esac
    if [[ "${version_id%%.*}" =~ ^[0-9]+$ ]] && (( ${version_id%%.*} >= 10 )); then
        release="el10"; key="rpm-package-key-v10.gpg"
    else
        release="el9";  key="rpm-package-key.gpg"
    fi
    cat << EOM
[google-cloud-cli]
name=Google Cloud CLI
baseurl=https://packages.cloud.google.com/yum/repos/cloud-sdk-${release}-${arch}
enabled=1
gpgcheck=1
repo_gpgcheck=0
gpgkey=https://packages.cloud.google.com/yum/doc/${key}
EOM
}

_install_gcloud_rhel() {
    local mgr repo_content
    command_exists dnf && mgr="dnf" || mgr="yum"
    if [[ -f "$GCLOUD_YUM_REPO" ]]; then
        ok "Google Cloud yum repository already configured"
    else
        log "Adding Google Cloud yum repository..."
        repo_content="$(_gcloud_yum_repo_content)" || return 1
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] write %s\e[0m\n' "$GCLOUD_YUM_REPO"
        else
            printf '%s\n' "$repo_content" \
                | sudo tee "$GCLOUD_YUM_REPO" >/dev/null || return 1
        fi
    fi
    run sudo "$mgr" install -y libxcrypt-compat "${GCLOUD_REPO_PACKAGES[@]}" \
        || return 1
    _link_packaged_auth_plugin
}

# Google's user-local SDK, for distros without a documented Google repo.
# It keeps the component manager, so the plugin (and kubectl) come from it.
_install_gcloud_tarball() {
    local extra_components=("$@") arch tmp_dir
    if [[ -x "$GCLOUD_USER_SDK/bin/gcloud" ]]; then
        ok "Google Cloud SDK already installed at ${GCLOUD_USER_SDK}"
    else
        case "$(uname -m)" in
            x86_64)        arch="x86_64" ;;
            aarch64|arm64) arch="arm" ;;
            *) warn "unsupported architecture for gcloud: $(uname -m)"; return 1 ;;
        esac
        log "Installing Google Cloud SDK to ${GCLOUD_USER_SDK}..."
        if [[ "$DRY_RUN" == "true" ]]; then
            printf '\e[2;37m  [dry] download and extract google-cloud-cli-linux-%s.tar.gz\e[0m\n' \
                "$arch"
        else
            tmp_dir="$(mktemp -d)" || return 1
            register_cleanup "$tmp_dir"
            curl -fsSL -o "$tmp_dir/sdk.tar.gz" \
                "$GCLOUD_TARBALL_BASE/google-cloud-cli-linux-${arch}.tar.gz" || return 1
            tar -xzf "$tmp_dir/sdk.tar.gz" -C "$HOME" || return 1
            "$GCLOUD_USER_SDK/install.sh" --quiet --usage-reporting false \
                --path-update false --command-completion false || return 1
        fi
    fi
    _install_gke_auth_plugin_component "$GCLOUD_USER_SDK/bin/gcloud" || return 1
    if (( ${#extra_components[@]} > 0 )); then
        run "$GCLOUD_USER_SDK/bin/gcloud" components install \
            "${extra_components[@]}" --quiet || return 1
    fi
    ensure_local_bin_shell_path
    run mkdir -p "$HOME/.local/bin" || return 1
    local tool
    for tool in gcloud gke-gcloud-auth-plugin "${extra_components[@]}"; do
        _link_tool "$GCLOUD_USER_SDK/bin/$tool" "$HOME/.local/bin/$tool" || return 1
    done
}

# Package installs keep the SDK under /usr/lib*/google-cloud-sdk. Link the
# plugin into /usr/local/bin unless the package already put it in /usr/bin.
_link_packaged_auth_plugin() {
    local sdk_bin
    if [[ -x /usr/bin/gke-gcloud-auth-plugin ]]; then
        ok "gke-gcloud-auth-plugin already in /usr/bin"
        return 0
    fi
    for sdk_bin in /usr/lib/google-cloud-sdk/bin /usr/lib64/google-cloud-sdk/bin; do
        if [[ -x "$sdk_bin/gke-gcloud-auth-plugin" ]]; then
            _link_tool "$sdk_bin/gke-gcloud-auth-plugin" \
                /usr/local/bin/gke-gcloud-auth-plugin sudo
            return
        fi
    done
    if [[ "$DRY_RUN" == "true" ]]; then
        printf '\e[2;37m  [dry] link gke-gcloud-auth-plugin into /usr/local/bin\e[0m\n'
        return 0
    fi
    warn "gke-gcloud-auth-plugin not found under /usr/lib*/google-cloud-sdk/bin"
    return 1
}

_install_helm_script() {
    if command_exists helm; then
        ok "helm already installed: $(helm version --short 2>/dev/null)"
        return 0
    fi
    fetch_and_run "$HELM_INSTALL_SCRIPT_URL"
}

_install_tfenv_linux() {
    local tool
    if [[ -d "$TFENV_DIR/.git" ]]; then
        ok "tfenv already cloned at ${TFENV_DIR}"
    else
        run git clone --depth=1 \
            "$(git_url git@github.com:tfutils/tfenv.git)" "$TFENV_DIR" || return 1
    fi
    ensure_local_bin_shell_path
    run mkdir -p "$HOME/.local/bin" || return 1
    for tool in tfenv terraform; do
        _link_tool "$TFENV_DIR/bin/$tool" "$HOME/.local/bin/$tool" || return 1
    done
}

_install_cloud_tools_linux() {
    case "$(detect_linux_distro)" in
        debian)
            _install_gcloud_debian || warn "gcloud apt install failed (continuing)"
            _install_helm_script   || warn "helm install failed (continuing)" ;;
        rhel*)
            if [[ "$(_os_release_field ID)" == "fedora" ]]; then
                _install_gcloud_tarball kubectl \
                    || warn "gcloud SDK install failed (continuing)"
            else
                _install_gcloud_rhel || warn "gcloud yum install failed (continuing)"
            fi
            _install_helm_script || warn "helm install failed (continuing)" ;;
        arch)
            # kubectl and helm come from pacman-packages.txt.
            _install_gcloud_tarball \
                || warn "gcloud SDK install failed (continuing)" ;;
        *)
            warn "Unsupported distro  - skipping cloud tools"
            return 0 ;;
    esac
    _install_tfenv_linux || warn "tfenv install failed (continuing)"
}

# The cask links gcloud into Homebrew's bin but not components installed later.
# Link to share/google-cloud-sdk, the SDK root gcloud updates in place; the
# versioned Caskroom path is a symlink to it and changes on every upgrade.
_install_cloud_tools_macos() {
    local prefix
    prefix="$(_cloud_brew_prefix)"
    _install_gke_auth_plugin_component "${prefix}/bin/gcloud" \
        || { warn "gke-gcloud-auth-plugin install failed (continuing)"; return 0; }
    _link_tool "${prefix}/share/google-cloud-sdk/bin/gke-gcloud-auth-plugin" \
        "${prefix}/bin/gke-gcloud-auth-plugin" \
        || warn "gke-gcloud-auth-plugin link failed (continuing)"
}

section_cloud_tools() {
    log "Installing cloud tools (gcloud, GKE auth plugin, kubectl, helm, tfenv)..."
    case "$OS" in
        macos) _install_cloud_tools_macos ;;
        linux|wsl) _install_cloud_tools_linux ;;
        *) warn "Unsupported OS  - skipping cloud tools" ;;
    esac
}

# -- Verification (--verify mode) ---------------------------------------------

verify_cloud_tools() {
    local tool
    for tool in gcloud gke-gcloud-auth-plugin kubectl helm tfenv; do
        _shared_tool_path "$tool" >/dev/null \
            && pass "${tool} on PATH for all shells" \
            || fail "${tool} not in a shared bin dir (brew bin, /usr/local/bin, /usr/bin, ~/.local/bin)"
    done
}
