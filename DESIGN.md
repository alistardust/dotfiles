# Design Rationale

Brief design decisions for the documentation site.

## Color

- **Deep purple** (primary): distinctive, high contrast on dark backgrounds
- **Teal** (accent): complementary to purple, used for links and interactive elements
- **Pink** (#e91e63): accessibility callouts only, draws attention to a11y content

## Theme

Material dark (slate) default. Terminal-first engineers prefer dark mode.
Light toggle available for readability in bright environments.

## Typography

Material defaults (Roboto) with system font fallback. No custom fonts loaded
to minimize page weight and support dyslexic readers who configure system fonts.

## Admonitions

| Type | Use for |
|------|---------|
| `info` | General notes |
| `tip` | Practical advice |
| `warning` | Pitfalls and gotchas |
| `danger` | Security risks |
| `accessibility` | Screen reader and AT guidance (custom, pink) |

## Cards

Semantic `<article>` elements with heading and description. Used only for
routing decisions: guide selector and landing page sections.

## Content Rules

- ASCII only (enforced by CI)
- No em-dashes or `--` prose separators
- Plain language throughout
- Max heading depth: H3 for general audience pages
- Every page gets a reading time estimate (via plugin)
- Last-updated date shown (via git-revision-date plugin)
