---
name: conventional-commit
description: 'Generate conventional commit messages from staged changes. Formats type(scope): description with body and trailers per the Conventional Commits spec.'
---

# Conventional Commit

Generate a well-formed commit message from the current staged diff.

## Workflow

1. Run `git diff --cached` to inspect staged changes.
2. Determine the appropriate type, scope, and description.
3. Construct the commit message (see format below).
4. Present the message to the user for approval before committing.

Note: This skill generates the message. The commit itself follows the
repository's standard review workflow (hunk review, approval, then commit).
Do not auto-commit without user confirmation.

## Format

```
type(scope): description    (subject line, <=72 chars, imperative mood)

body                        (optional: what changed and why)

footer                      (optional: BREAKING CHANGE, ticket refs)
trailers                    (Co-authored-by, etc.)
```

### Types

`feat` `fix` `docs` `refactor` `test` `perf` `build` `ci` `chore` `revert`

### Rules

- Subject line: imperative mood ("add", not "added"), no period at end.
- Scope: optional but recommended for clarity (module, component, or area).
- Breaking changes: append `!` after type/scope and add `BREAKING CHANGE:` footer.
- Include `Co-authored-by` trailer when commits are AI-assisted.

## Examples

```
feat(parser): add ability to parse arrays
fix(ui): correct button alignment on mobile
docs: update README with usage instructions
feat!: send email on registration

BREAKING CHANGE: email service config required

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

## Validation

- Type must be one of the allowed types above.
- Description is required, imperative mood.
- Reference: https://www.conventionalcommits.org/en/v1.0.0/
