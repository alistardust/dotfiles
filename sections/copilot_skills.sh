# shellcheck shell=bash
# Section: copilot_skills
# shellcheck disable=SC2088,SC2015

# -- Copilot Skills (profile-based) -------------------------------------------

# Skills installed via: gh skills install github/awesome-copilot <name>
SKILLS_SOURCE="github/awesome-copilot"

SKILLS_WORK=(
    threat-model-analyst
    create-architectural-decision-record
    multi-stage-dockerfile
    secret-scanning
    postgresql-optimization
)

SKILLS_HOME=(
    playwright-generate-test
    agent-governance
    agentic-eval
    documentation-writer
)

SKILLS_SHARED=(
    python-pypi-package-builder
    sql-code-review
)

# Local skills shipped in this repo (skills/<name>/SKILL.md -> ~/.copilot/skills/<name>/)
# All directories in skills/ are installed automatically. No manual list needed.
# To add a new skill: create skills/<name>/SKILL.md and re-run setup.

# gstack ships a telemetry client that syncs skill usage, including repository
# names, to a third-party Supabase endpoint. It defaults to off, but the flag
# lives in gstack's own state directory where a package update can reset it.
# Reassert it here and clear any usage log that accumulated between runs.
_copilot_skills_harden_gstack() {
    local state_dir="${HOME}/.gstack"
    local config="${state_dir}/config.yaml"
    local analytics="${state_dir}/analytics"

    [[ -d "$state_dir" ]] || return 0

    if [[ ! -f "$config" ]]; then
        run tee "$config" <<< 'telemetry: off'
        ok "gstack telemetry set to off"
    elif grep -qE '^telemetry:[[:space:]]*off[[:space:]]*$' "$config"; then
        ok "gstack telemetry already off"
    elif grep -qE '^telemetry:' "$config"; then
        run sed -i.dotbak -E 's/^telemetry:.*/telemetry: off/' "$config"
        run rm -f "${config}.dotbak"
        warn "gstack telemetry was re-enabled; reset to off"
    else
        run tee -a "$config" <<< 'telemetry: off'
        ok "gstack telemetry set to off"
    fi

    # The skill preamble recreates these on every invocation, so clear them
    # rather than trying to prevent the write.
    local logs
    logs=$(find "$analytics" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$logs" -gt 0 ]]; then
        run find "$analytics" -maxdepth 1 -name '*.jsonl' -delete
        ok "Cleared ${logs} gstack usage log(s)"
    fi
}

section_copilot_skills() {
    log "Installing Copilot skills (profiles: work=${SKILLS_PROFILE[work]}, home=${SKILLS_PROFILE[home]})..."

    # Ensure ~/.copilot/settings.json exists with required defaults
    # The interface model routes work, adjudicates subagent output, and decides
    # what to escalate, so it is a judgment seat and must be frontier. Cheap
    # models earn their keep in subagents, not here. Both profiles get Opus;
    # cost control comes from delegation, not from a weaker interface.
    local settings_file="${HOME}/.copilot/settings.json"
    local default_model="claude-opus-5"
    run mkdir -p "${HOME}/.copilot"
    if [[ ! -f "$settings_file" ]]; then
        run tee "$settings_file" <<< '{"memory":{"enabled":true},"model":"'"${default_model}"'","experimental":true}'
        ok "Created settings.json (model: ${default_model})"
    else
        run python3 -c "
import json,sys
p=sys.argv[1]
model=sys.argv[2]
d=json.load(open(p))
changed=False
if not d.get('memory',{}).get('enabled'):
    d.setdefault('memory',{})['enabled']=True
    changed=True
if d.get('model')!=model:
    d['model']=model
    changed=True
if changed:
    json.dump(d,open(p,'w'),indent=2)
    sys.exit(0)
sys.exit(1)
" "$settings_file" "$default_model" && ok "Updated settings.json (model: ${default_model})" || true
    fi

    # Install local skills from this repo (all directories in skills/)
    _install_local_skills "$HOME/.copilot/skills"
    ok "All local skills installed to ~/.copilot/skills/"

    _copilot_skills_harden_gstack

    if ! command_exists gh && [[ "$DRY_RUN" != "true" ]]; then
        warn "gh CLI not found. Install GitHub CLI first: https://cli.github.com/"
        return 1
    fi

    # Build the list of remote skills to install based on selected profiles
    local -a selected_skills=()
    selected_skills+=("${SKILLS_SHARED[@]}")
    if [[ "${SKILLS_PROFILE[work]}" == "true" ]]; then
        selected_skills+=("${SKILLS_WORK[@]}")
    fi
    if [[ "${SKILLS_PROFILE[home]}" == "true" ]]; then
        selected_skills+=("${SKILLS_HOME[@]}")
    fi

    if [[ ${#selected_skills[@]} -eq 0 ]]; then
        warn "No skill profiles selected (use --skills-work and/or --skills-home)."
        return 0
    fi

    for skill in "${selected_skills[@]}"; do
        if [[ -d "${HOME}/.copilot/skills/${skill}" ]]; then
            ok "Skill already installed: ${skill}"
        else
            run gh skills install "${SKILLS_SOURCE}" "${skill}"
            ok "Installed skill: ${skill}"
        fi
    done

    ok "Copilot skills installation complete."
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_copilot_skills() {
    local skills_dir="${HOME}/.copilot/skills"

    [[ -d "$skills_dir" ]] \
        && pass "~/.copilot/skills/ directory exists" \
        || { fail "~/.copilot/skills/ directory missing"; return; }

    # Check memory is enabled in settings.json
    local settings_file="${HOME}/.copilot/settings.json"
    if python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d.get('memory',{}).get('enabled')" "$settings_file" 2>/dev/null; then
        pass "Copilot memory enabled in settings.json"
    else
        fail "Copilot memory not enabled in settings.json"
    fi

    # Check default model is set to Anthropic
    if python3 -c "import json,sys; d=json.load(open(sys.argv[1])); assert d.get('model','').startswith('claude-')" "$settings_file" 2>/dev/null; then
        pass "Default model is Anthropic ($(python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get('model','unset'))" "$settings_file"))"
    else
        fail "Default model is not Anthropic in settings.json"
    fi

    # Check local skills (all directories in skills/ should be installed)
    local skill src
    for src in "${SCRIPT_DIR}/skills"/*/; do
        [[ -d "$src" ]] || continue
        skill="$(basename "$src")"
        [[ -f "${skills_dir}/${skill}/SKILL.md" ]] \
            && pass "Local skill installed: ${skill}" \
            || fail "Local skill missing: ${skill}"
    done

    # Check a11y-review-deep phases directory
    local phases_dir="${skills_dir}/a11y-review-deep/phases"
    if [[ -d "$phases_dir" ]]; then
        local phase_count
        phase_count=$(find "$phases_dir" -name '*.md' | wc -l | tr -d ' ')
        [[ "$phase_count" -ge 6 ]] \
            && pass "a11y-review-deep phases: ${phase_count} documents" \
            || fail "a11y-review-deep phases incomplete: ${phase_count}/6 documents"
    else
        fail "a11y-review-deep/phases/ directory missing"
    fi

    # Check shared remote skills (always expected if copilot_skills was ever run)
    for skill in "${SKILLS_SHARED[@]}"; do
        [[ -f "${skills_dir}/${skill}/SKILL.md" ]] \
            && pass "Skill installed: ${skill}" \
            || fail "Skill missing: ${skill}"
    done

    if [[ "${SKILLS_PROFILE[work]}" == "true" ]]; then
        for skill in "${SKILLS_WORK[@]}"; do
            [[ -f "${skills_dir}/${skill}/SKILL.md" ]] \
                && pass "Skill installed: ${skill}" \
                || fail "Skill missing: ${skill}"
        done
    fi

    if [[ "${SKILLS_PROFILE[home]}" == "true" ]]; then
        for skill in "${SKILLS_HOME[@]}"; do
            [[ -f "${skills_dir}/${skill}/SKILL.md" ]] \
                && pass "Skill installed: ${skill}" \
                || fail "Skill missing: ${skill}"
        done
    fi

    # gstack telemetry syncs usage to a third-party endpoint; it must stay off
    if [[ -d "${HOME}/.gstack" ]]; then
        grep -qE '^telemetry:[[:space:]]*off[[:space:]]*$' "${HOME}/.gstack/config.yaml" 2>/dev/null \
            && pass "gstack telemetry is off" \
            || fail "gstack telemetry is not off"

        local stale_logs
        stale_logs=$(find "${HOME}/.gstack/analytics" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')
        [[ "$stale_logs" -eq 0 ]] \
            && pass "No gstack usage logs on disk" \
            || warn "${stale_logs} gstack usage log(s) present; re-run setup to clear"
    fi

    # Verify conductor registry is not stale (warn if installed skills exist outside registry)
    if [[ -f "${skills_dir}/skill-conductor/SKILL.md" ]]; then
        local registry_file="${skills_dir}/skill-conductor/SKILL.md"
        local unregistered=0
        for dir in "${skills_dir}"/gstack-*/; do
            [[ -d "$dir" ]] || continue
            local skill_name
            skill_name="$(basename "$dir" | sed 's/^gstack-//')"
            if ! grep -q "$skill_name" "$registry_file" 2>/dev/null; then
                warn "Unregistered skill in conductor: $(basename "$dir")"
                unregistered=$((unregistered + 1))
            fi
        done
        [[ $unregistered -eq 0 ]] \
            && pass "Conductor registry covers all installed gstack skills" \
            || warn "Conductor registry has ${unregistered} unregistered gstack skill(s)"
    fi
}
