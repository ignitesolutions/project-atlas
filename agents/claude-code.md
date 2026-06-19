# Project Atlas — Claude Code Agent Metadata

This file replaces the OpenAI-specific `openai.yaml` that shipped with the original skill.
Claude Code does not use interface metadata (display names, icons, brand colors).
The skill is driven entirely by `SKILL.md`.

## Identity

- **Skill name:** project-atlas
- **Short description:** Create and maintain an AI-readable `project-atlas/` folder for software repositories.
- **Invocation:** Claude reads `SKILL.md` and executes scripts via bash as needed.

## Notes for Claude Code

- Always read `SKILL.md` before acting.
- Run scripts from the **repository root** so that `project-atlas/scripts/` is a valid relative path.
- Use `--repo .` when the current working directory is already the repository root.
