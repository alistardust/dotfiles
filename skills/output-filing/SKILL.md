---
name: output-filing
description: 'Naming and filing rules for agent-authored output under
  ~/Documents/copilot-output/. Use this skill whenever writing, saving, or
  revising any file in that tree: choosing a project directory, naming an
  output file, writing a new draft or revision of an existing document, or
  saving a ticket description.'
---

<!-- CROSS-TOOL NOTE: This skill applies identically in Copilot CLI and Claude
     Code. The tree at ~/Documents/copilot-output/ is shared by both tools;
     the name is historical, not tool-specific. -->

# Output Filing

The always-loaded instructions carry the placement invariants. This skill
carries the detail: how to pick a directory, how to name a file, and how to
handle drafts and ticket descriptions.

## The tree

    ~/Documents/copilot-output/
      work/
        tickets/<ticket-id>-<descriptor>/
        <project-slug>/
      personal/
        <project-slug>/

Work output goes under `work/`, personal-life output under `personal/`. If a
piece of work is not clearly one or the other, ask before writing rather than
guessing.

## Choosing a directory

**Reuse before creating.** Before making a new project directory, list what
already exists in that domain:

```bash
ls ~/Documents/copilot-output/work/
ls ~/Documents/copilot-output/personal/
```

If the work continues an existing project, write into that directory. Only
create a new slug when the work is genuinely new. This check is the rule that
keeps the tree from filling up with single-file directories.

**Never write a loose file at a domain root.** Not even for a one-off. A
one-off gets a directory containing one file. This is absolute; the previous
version of this rule allowed loose files and produced 122 of them.

**Ticket work always goes under `work/tickets/`.** Anything carrying a ticket
ID (OPS-1234, DEVEX-567, TACHI-060) belongs there, never in a bare project
slug at the `work/` root.

### Directory names

- Lowercase, hyphen-separated. No capitals, no underscores, no spaces.
- Ticket IDs are lowercased too: `ops-8520`, never `OPS-8520`.
- Descriptive of the actual subject, not the activity:
  `prod-iguana-cpu-spike`, not `investigation`, `analysis`, or `stuff`.
- Ticket directories take the form `<ticket-id>-<descriptor>`, for example
  `work/tickets/ops-8520-census/`. The descriptor exists so the ticket is
  recognizable at a glance without looking it up in Jira.

## Naming files

The filename must make the contents obvious when read in context of its
directory. It does not need to repeat the project name; the directory
already supplies that. What it must never be is generic.

| Write | Not |
|-------|-----|
| `cpu-spike-findings.md` | `notes.md` |
| `teams-message.md` | `output.md` |
| `thermal-enclosure-analysis.md` | `final.md` |
| `reconciliation-plan.md` | `untitled.md`, `temp.md` |

Do not repeat the directory name in the filename. In
`work/kafka-retention-tuning/`, write `followup-analysis.md`, not
`kafka-retention-tuning-followup-analysis.md`.

Do not repeat the ticket ID in the filename. The directory already carries
it.

Choose the extension that fits the content: `.md` for prose, `.txt` for plain
text, `.yaml` or `.json` for structured data.

### Dates

Include a date only when the file is inherently a point-in-time artifact:
incident findings, a captured snapshot, a meeting note. Use `YYYY-MM-DD`.

Do not date a file merely because it will be revised later. A document that
gets edited is not a point-in-time artifact; it is a living document, and
dating it produces a misleading timeline.

### Drafts

**The first version of a document is unsuffixed.** Do not start at `-v1`.
A file only enters a version chain when a second draft is actually written.

When creating `-v2`, rename the original to `-v1` in the same step, so the
chain is never implicit. Use `mv`, never `cp`:

```bash
mv appeal-letter.md appeal-letter-v1.md
# then write appeal-letter-v2.md
```

Copying instead of renaming is wrong: it leaves three files, including an
unsuffixed original that a reader cannot place in the chain. After creating
`-v2` there must be exactly two files, `-v1` and `-v2`.

Never write `.bak` files. A backup is a version bump.

## Ticket descriptions

When a ticket description is pasted into chat, save it to
`work/tickets/<ticket-id>-<descriptor>/description.md` before doing any other
work on that ticket.

This filename is fixed and exempt from the naming rules above, so that other
rules can reference it by name. All analysis and validation for that ticket
treats `description.md` as the source of truth when it exists.

## Retention

There is deliberately no retention or archival rule. Nothing in this tree is
swept, archived, or moved automatically. Do not propose cleanup of old
directories unless explicitly asked.
