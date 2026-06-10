---
name: update-copilot-instructions
description: Procedure for updating Copilot instruction files. Use this skill when asked to add, modify, or remove content from any Copilot instructions file, including ~/.copilot/copilot-instructions.md or any repo-level .github/copilot-instructions.md.
---

## Process for updating instructions

Before writing any new or modified instruction to any Copilot instructions file:

1. Draft the proposed instruction text and display it for Ali to review.
2. Write instructions using precise, actionable language -- interpret Ali's intent
   and improve the phrasing rather than transcribing her words directly, unless
   Ali says otherwise.
3. Wait for explicit approval before writing to the file. Only skip approval if
   Ali explicitly says "no approval needed" or similar.

## Instruction file locations

- **Global (all projects)**: `~/.copilot/copilot-instructions.md`
- **Repo-level**: `.github/copilot-instructions.md` in the repo root
- **Skills**: `~/.copilot/skills/<name>/SKILL.md` (personal) or
  `.github/skills/<name>/SKILL.md` (repo-level)

## Evaluate: skill vs. instructions

Before adding content to an instructions file, ask: **is this content only
needed for specific task types, or does it need to be active on every turn?**

Use this heuristic:

| Fits in instructions | Fits in a skill |
|---|---|
| Behavioral rules (always apply) | Workflow with steps and format details |
| Identity, tone, output format | Reference tables and lookup content |
| Safety / security requirements | Procedures triggered by specific task types |
| Short (< ~5 lines) | Long or detailed (> ~10 lines) |

If content fits a skill:
1. Draft a `SKILL.md` for it with a precise `description:` field -- that
   description is how the model decides when to load it, so make it explicit
   about the trigger conditions.
2. If the content belongs to a specific repo (e.g., tachi command reference),
   create it there and symlink to `~/.copilot/skills/<name>`.
3. Replace the instructions section with a one-liner pointer or remove it
   entirely if the skill description is sufficient.
4. Show the draft `SKILL.md` and the proposed instructions diff to Ali for
   approval before writing either.

Skills can reference each other in their bodies but not load each other -- each
skill is an independent context injection.

## The tachi global skill

`skills/tachi/SKILL.md` (in the tachikoma repo) is the user-facing command
reference for tachi. It is symlinked to `~/.copilot/skills/tachi` so it loads
globally across all projects.

When updating instruction or skill content related to tachi:
- Command capability changes go in `skills/tachi/SKILL.md`
- Architecture/implementation details go in `.github/skills/tachi-architecture/SKILL.md`
- Character/voice/content rules go in `.github/skills/tachi-thought/SKILL.md`
- Do NOT reference the global `tachi` skill from repo instructions -- it is loaded
  by the system and referencing it would be redundant

### How to maintain skills/tachi/SKILL.md

**What belongs here:** what tachi can do and when to use it. Capability reference,
not implementation reference.

**Level of detail:** modules and their subcommands. Do not document individual flags
or options -- that belongs in `--help`. One or two words per subcommand is enough.

**Format:** follow the existing pattern exactly:

```markdown
### `tachi <module>` -- Short description
- `subcommand` -- what it does
- `subcommand` -- what it does
```

**When to add a module:** as soon as it has at least one working command. Do not
wait until complete.

**When to update:** any time a subcommand is added, removed, renamed, or its
purpose changes significantly.

**When to remove:** only when a module or subcommand is fully removed. Stub or
partial modules stay listed -- they communicate intent.

**What does NOT belong here:**
- Implementation status or caveats -- that goes in `tachi-architecture`
- Flag/option details -- that belongs in `--help`
- Architecture decisions or internals -- that goes in `tachi-architecture`
- Config file format or credential setup -- that goes in `tachi-architecture`

## Writing effective instructions

When drafting new instruction content, follow these principles:

- Put hard constraints (security, never-do-this) **first**; they must be seen before context limits
  cut in.
- Use bullets and discrete rules, not prose paragraphs; LLMs comply more reliably with explicit lists.
- Provide positive AND negative code examples for non-obvious rules.
- State the *why* for non-obvious constraints.
- Keep repo-level instruction files under 2000 words; longer files get deprioritized.
- Global rules belong in `~/.copilot/copilot-instructions.md`. Project-specific rules belong in
  `.github/copilot-instructions.md`.
- Never put secrets, PII, or project-sensitive content in instruction files.
