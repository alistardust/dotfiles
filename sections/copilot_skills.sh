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
}
