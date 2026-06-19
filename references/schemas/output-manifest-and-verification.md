# Output Manifest and Verification

Existing-codebase bootstrap must create the exact existing manifest listed in `SKILL.md` and the required directories `platforms/`, `decisions/`, `handoffs/`, and `snapshots/`.

Intentional scaffold folders:
- `decisions/README.md`
- `handoffs/README.md`
- `snapshots/README.md`

These are expected to remain lightweight until needed. Do not remove them.

Repo-specific required files such as `architecture.md`, `project-overview.md`, `stack.md`, `code-map.md`, `database.md`, and `auth-and-access.md` must not remain as generic scaffolds. If a known placeholder is found, repair it before reporting success.

Optional generated support file:
- `cfc-index.md` may be created for CFML repositories, but it must be referenced from `code-map.md` or `platforms/cfml.md` and does not replace those files.

Unexpected platform files are verification failures unless explicitly selected.
