# Scan and Creation Contract

## Scan

Scan repository path metadata for file paths, directory names, extensions, marker files, dependency manifests, config names, test locations, migrations, deployment files, docs, and existing Atlas files.

Read limited text only from likely evidence files: manifests, framework config, route files, entry points, migrations/schema files, auth/session/permission files, database config, Docker/compose, CI/CD, README/docs, and existing Atlas files.

Never traverse heavy/generated/vendor paths by default: `.git/`, `node_modules/`, `vendor/`, `venv/`, `.venv/`, `__pycache__/`, `dist/`, `build/`, `coverage/`, `.cache/`, `.next/`, `.nuxt/`, `target/`, `bin/`, `obj/`, `WEB-INF/lucee/`, and `project-atlas/snapshots/generated/`.

Never read or store secret values from `.env`, `.env.*`, private keys, certificates, tokens, passwords, production connection strings, license keys, or customer data exports.

## Creation

For existing codebases, create only generated repository documentation under `project-atlas/`. Do not copy Skill-internal `references/`, `scripts/`, `templates/`, `agents/`, or `SKILL.md` into generated output.

## Scaffold policy

For existing-codebase bootstrap, `decisions/`, `handoffs/`, and `snapshots/` are intentional scaffold folders and must be created. Their README files may remain lightweight. Root repo docs must not remain generic scaffolds.

If an existing root Atlas file contains a known scaffold marker such as `atlas scaffold`, `Generated placeholder`, or `Update with confirmed project context`, replace it during bootstrap/update even without `--force`. Preserve hand-authored files unless `--force` is supplied.

## Platform file policy

Create `project-atlas/platforms/*.md` only for detected or explicitly selected platforms supported by the manifest. Do not create `platforms/postgres.md`, `platforms/auth.md`, `platforms/testing.md`, or `platforms/storage.md` merely to document false positives or secondary concerns. Put those notes in root Atlas files.
