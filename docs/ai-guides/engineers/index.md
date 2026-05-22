---
series: "Working with AI: A Field Guide"
subtitle: "For Engineers"
current_as_of: "2026-05"
---

# AI Workflow Guide for Engineers

## What changed

- **2026-05:** Initial public version. Covers GitHub Copilot CLI, Claude Code, and
  OpenAI Codex. Forked from platform engineer guide.
- **2026-05 (prior):** CLI commands verified, Chapter 5 trimmed, title casing normalized,
  front matter added.
- **2026-05 (initial):** Guide published.

> This guide was last reviewed against tools available in 2026-05. If you are
> reading this more than six months later, the tool-specific chapters may have
> drifted.

# AI-Assisted Workflow Guide for Infrastructure Engineers

## Table of contents

1. [Why this guide exists](#chapter-1-why-this-guide-exists)
2. [Getting started](#chapter-2-getting-started)
3. [The instruction system](#chapter-3-the-instruction-system)
4. [Writing effective prompts](#chapter-4-writing-effective-prompts)
5. [Skills: the force multiplier](#chapter-5-skills----the-force-multiplier)
6. [Writing your own skills](#chapter-6-writing-your-own-skills-advanced)
7. [Multi-model workflows](#chapter-7-multi-model-workflows)
8. [Real-world DevOps workflows](#chapter-8-real-world-devops-workflows)
9. [Trust, safety, and knowing when to verify](#chapter-9-trust-safety-and-knowing-when-to-verify)
10. [Quick start checklist](#chapter-10-quick-start-checklist)

# Why this guide exists


> **Impatient?** Jump to [Chapter 8: Real-world workflows](#chapter-8-real-world-workflows) for
> immediate practical examples, then come back here for the foundations.

AI coding assistants are not just faster autocomplete. They change how you break down work, how you investigate systems, and how you decide what to automate versus what to verify by hand. For infrastructure and DevOps engineers, that matters. A good assistant can help you trace a failing deployment, draft a safer rollback plan, explain a Terraform module, or turn a rough incident note into a clean runbook update. A bad workflow can waste the same afternoon by producing vague output, unsafe suggestions, and long review loops.

The difference between wasted time and saved hours is technique. You need to know when to ask for research instead of code, when to pin the tool to a specific model, when to provide operating context up front, and when to stop the assistant from going too far. This guide is tool-agnostic, but GitHub Copilot CLI is the primary example because it fits terminal-heavy engineering work well. The same patterns translate cleanly to Claude Code and Codex.

This guide is for engineers who work in terminals, write code, manage repositories, and operate infrastructure. If you are looking for guidance on using AI as a non-technical collaborator, see the companion guide for knowledge workers instead.

If you have used autocomplete in your editor but not the CLI, skills, custom instructions, or multi-model workflows: this guide is for you.

---

[Getting started >](getting-started.md)
