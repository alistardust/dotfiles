# Quick start checklist

This is the short path to a usable AI-assisted workflow. Each item gives you the action and the reason.

### Day 1: Get running

1. **Install your tool of choice**: Start with Copilot CLI if you already have a GitHub Copilot license.

```bash
npm install -g @github/copilot
```

2. **Authenticate**: Use OAuth device flow when the tool supports it so you do not have to manage raw tokens in shell startup files.

```bash
copilot login
```

3. **Set your preferred model**: Pick a default early so your results are predictable. Claude Sonnet is a solid default for terminal-first infrastructure work.

```bash
copilot config set model claude-sonnet-4-5
```

4. **Create a global instruction file**: Put your safety rules, coding preferences, and workflow defaults in one place so you do not repeat them in every session.

```bash
mkdir -p ~/.github
cat > ~/.github/copilot-instructions.md << 'EOF'
# Global instructions

## Safety rules
- Never run destructive commands without explicit confirmation.
- Always use --dry-run or plan before apply.
- Do not paste secrets into conversations.

## Preferences
- Use snake_case for Python and Terraform.
- Prefer concise explanations.
- Show the command before explaining what it does.
EOF
```

### Week 1: Build the habit

5. **Create a per-repo instruction file**: Add project-specific context for the repo you work in most often.

```bash
mkdir -p .github
# Write a copilot-instructions.md with your project's conventions
# See Chapter 3 for a full worked example
```

6. **Install superpowers and gstack skills**: Add process skills and browser-based helpers so the AI can do more than one-shot prompting.

```bash
git clone git@github.com:DwainTR/superpowers-copilot.git ~/.copilot/skills/superpowers
git clone git@github.com:ridermw/gstack.git ~/.copilot/skills/gstack
```

7. **Try the brainstorming skill**: The next time you start a feature, automation flow, or runbook rewrite, ask the AI to design before it writes.

```text
I need to [describe your next task]. Use the brainstorming skill to help me think through the design before we write any code.
```

8. **Try the code-review skill**: Before your next PR or risky change, ask for a focused review that filters out style noise.

```text
Review the staged changes in this repo. Only flag bugs, security issues, and logic errors.
```

### Once comfortable: Level up

9. **Try multi-model review**: For your next important change, have both Claude and GPT review it independently, then compare where they agree and where they differ.

10. **Write your first custom skill**: Pick a team workflow that should be consistent, such as a deploy checklist, incident handoff, or rollback review, and encode it as a reusable skill. See Chapter 6.

### You are set up

If you have done these 10 things, you have a working AI-assisted workflow that covers safe execution, consistent style, structured problem-solving, and quality gates. The rest is practice and iteration. Revisit the prompt patterns in Chapter 4 and the workflow examples in Chapter 8 as you hit new scenarios.

## What's next

- **[Skills catalog](../../reference/skills-catalog.md)**: browse available skills across all tools
- **[Prompt patterns](../../reference/prompt-patterns.md)**: reusable patterns for common tasks
- **[Accessibility](../../accessibility/index.md)**: make your tools work with assistive technology
- **[General audience guide](../general/index.md)**: share with non-technical colleagues

---

[< Trust and safety](safety.md)
