# Model comparison matrix

Last verified: 2026-05-19. Model availability changes frequently.

| Tier | Example models | Best for | Limitations | Relative speed |
|------|---------------|----------|-------------|----------------|
| Reasoning | Claude Opus, GPT-5.x | Complex architecture, multi-step debugging, nuanced code review, security analysis | Expensive, slower, may overthink simple tasks | Slowest (10-60s typical) |
| Standard | Claude Sonnet, GPT-5.x | Day-to-day coding, code review, refactoring, documentation, most tasks | Occasionally misses subtle issues that reasoning tier catches | Medium (3-15s typical) |
| Fast/cheap | Claude Haiku, GPT-5.x mini | Quick lookups, simple generation, bulk operations, exploration agents | Lower accuracy on complex reasoning, may miss edge cases | Fastest (1-5s typical) |

### Choosing a tier

- **Default to Standard** for most work. It handles 80%+ of tasks well.
- **Escalate to Reasoning** for: security reviews, production incident debugging, architecture decisions, anything where being wrong is expensive.
- **Drop to Fast** for: grep-like searches, simple boilerplate, batch operations, exploration subagents.

### Multi-model patterns

| Pattern | How | When |
|---------|-----|------|
| Dual review | Same prompt to Reasoning + Standard, compare outputs | Important PRs, security-sensitive code |
| Draft + refine | Fast tier generates draft, Standard tier reviews and fixes | High-volume generation (tests, docs) |
| Consensus check | Same question to 2 different providers (Claude + GPT) | Ambiguous problems, conflicting docs |
| Escalation | Start with Standard, escalate to Reasoning only if stuck | Cost-conscious workflows |
