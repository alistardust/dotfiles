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
    web-coder
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
SKILLS_LOCAL=(
    code-audit
    hunk-reviewer
    skill-conductor
    skill-conductor-decision
    skill-conductor-context
    skill-conductor-execution
)

section_copilot_skills() {
    log "Installing Copilot skills (profiles: work=${SKILLS_PROFILE[work]}, home=${SKILLS_PROFILE[home]})..."

    # Install local skills from this repo first
    local skill
    for skill in "${SKILLS_LOCAL[@]}"; do
        local src="${SCRIPT_DIR}/skills/${skill}"
        local dest="${HOME}/.copilot/skills/${skill}"
        if [[ ! -d "$src" ]]; then
            warn "Local skill source missing: ${src}"
            continue
        fi
        run mkdir -p "$dest"
        run cp -R "${src}/." "$dest/"
        ok "Installed local skill: ${skill}"
    done

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

    # Install GSD (Get Shit Done) context engineering skills
    _copilot_skills_install_gsd
}

_copilot_skills_install_gsd() {
    if [[ -f "${HOME}/.copilot/skills/gsd-new-project/SKILL.md" ]]; then
        ok "GSD core skills already installed (Copilot)"
    else
        if command_exists npx; then
            run npx get-shit-done-cc@latest --copilot --global --profile=core
            ok "Installed GSD core skills (Copilot)"
        else
            warn "npx not found; skipping GSD installation. Install Node.js first."
        fi
    fi

    if [[ -f "${HOME}/.claude/skills/gsd-new-project/SKILL.md" ]]; then
        ok "GSD core skills already installed (Claude Code)"
    else
        if command_exists npx; then
            run npx get-shit-done-cc@latest --claude --global --profile=core
            ok "Installed GSD core skills (Claude Code)"
        else
            warn "npx not found; skipping GSD installation for Claude Code."
        fi
    fi
}

# -- Verification (--verify mode) ---------------------------------------------
# shellcheck disable=SC2088  # Tilde in quoted strings is intentional display text
# shellcheck disable=SC2015  # A && B || C pattern is safe here (pass/fail always succeed)

verify_copilot_skills() {
    local skills_dir="${HOME}/.copilot/skills"

    [[ -d "$skills_dir" ]] \
        && pass "~/.copilot/skills/ directory exists" \
        || { fail "~/.copilot/skills/ directory missing"; return; }

    # Check local skills (always expected if copilot_skills was ever run)
    local skill
    for skill in "${SKILLS_LOCAL[@]}"; do
        [[ -f "${skills_dir}/${skill}/SKILL.md" ]] \
            && pass "Local skill installed: ${skill}" \
            || fail "Local skill missing: ${skill}"
    done

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

    # Verify GSD core skills are installed
    local gsd_core_skills=(gsd-new-project gsd-plan-phase gsd-discuss-phase gsd-execute-phase)
    for skill in "${gsd_core_skills[@]}"; do
        [[ -f "${skills_dir}/${skill}/SKILL.md" ]] \
            && pass "GSD skill installed: ${skill}" \
            || fail "GSD skill missing: ${skill} (run: npx get-shit-done-cc@latest --copilot --global --profile=core)"
    done

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
