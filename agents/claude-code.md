# Project Atlas — Claude Code Agent Metadata

Claude Code does not use interface metadata (display names, icons, brand colors); no separate
interface-metadata file is shipped for it. The skill is driven entirely by `SKILL.md`.

## Identity

- **Skill name:** project-atlas
- **Short description:** Create and maintain an AI-readable `project-atlas/` folder for software repositories.

## Notes for Claude Code

- Always read `SKILL.md` before acting.
- The scripts live in this Skill's install directory (the directory containing `SKILL.md`), **not** in the target repository. Never copy them into the repo.
- Invoke them by absolute path, pointing at the repository with `--repo`:

  ```bash
  python3 <skill-dir>/scripts/bootstrap_atlas.py --repo /path/to/repo --mode existing
  python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode check
  ```

- After a successful bootstrap, perform the enrichment pass described in `SKILL.md` — the script output is scaffolding plus evidence, not finished documentation.
- Fall back to manual file tools only if Python is unavailable, using `templates/` as the content source.
