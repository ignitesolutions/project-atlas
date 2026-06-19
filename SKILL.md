---
name: project-atlas
description: create and maintain an ai-readable project-atlas folder for software repositories. use for existing codebase scans, greenfield project planning, repo context generation, architecture and code maps, cfc/cfml method inventories, database/auth/deployment summaries, durable maintenance updates, handoff notes, and verification that required atlas files exist exactly under project-atlas/. triggers on any mention of project-atlas, repo scan, codebase documentation, or atlas bootstrap.
compatibility: Claude Code, claude.ai, Claude Desktop, ChatGPT (Custom GPT / Code Interpreter)
license: see LICENSE.txt if present; otherwise treat as proprietary skill content
---

# Project Atlas

## Operating modes

Determine the mode before acting:

1. **Existing codebase bootstrap**: scan a repository and create `project-atlas/` documentation.
2. **Greenfield setup**: create planning and context scaffolding for a new project.
3. **Atlas maintenance**: update existing Atlas files after durable project changes.
4. **Verification/check**: inspect an existing `project-atlas/` folder and report exact problems.

## Hard boundaries

- Create and maintain generated Atlas output only inside `project-atlas/` at the repository root.
- Never write generated Atlas output to `.`, `htdocs/`, `.project-atlas/`, `altas/`, `Atlas.md`, or numbered Atlas folders.
- Never copy Skill-internal directories into the generated repository output.
- Treat Skill package files as internal guidance only: `references/`, `scripts/`, `templates/`, `agents/`, and `SKILL.md` must not be copied into `repo/project-atlas/`.
- Do not store real secrets. Document access patterns, config file paths, and environment variable names only.
- Do not overwrite existing Atlas files unless the user explicitly asks or passes `--force`.
- Keep generated docs compact, repo-specific, and useful for future agents.
- Leave `project-atlas/decisions/`, `project-atlas/handoffs/`, and `project-atlas/snapshots/` in place as intentional scaffold folders. Their README files may remain lightweight until needed.
- Do not leave root-level repo documentation files as generic scaffolds. Files such as `architecture.md`, `project-overview.md`, `stack.md`, `code-map.md`, `database.md`, and `auth-and-access.md` must contain repo-specific evidence, path lists, or explicitly marked unknowns.

## Required generated structure for existing codebases

When bootstrapping an existing codebase, create these exact files every time unless already present and overwrite was not requested:

```text
project-atlas/README.md
project-atlas/agent-playbook.md
project-atlas/project-overview.md
project-atlas/stack.md
project-atlas/architecture.md
project-atlas/code-map.md
project-atlas/feature-index.md
project-atlas/database.md
project-atlas/auth-and-access.md
project-atlas/conventions.md
project-atlas/dependency-map.md
project-atlas/testing.md
project-atlas/deployment.md
project-atlas/known-risks.md
project-atlas/glossary.md
project-atlas/open-questions.md
project-atlas/maintenance-log.md
project-atlas/.project-atlasignore
project-atlas/decisions/README.md
project-atlas/handoffs/README.md
project-atlas/snapshots/README.md
```

Create these directories every time:

```text
project-atlas/platforms/
project-atlas/decisions/
project-atlas/handoffs/
project-atlas/snapshots/
```

Create platform files only when detected or explicitly requested:

```text
project-atlas/platforms/cfml.md
project-atlas/platforms/php.md
project-atlas/platforms/node-js.md
project-atlas/platforms/python.md
project-atlas/platforms/mysql.md
project-atlas/platforms/mssql.md
project-atlas/platforms/docker.md
```

Do not create extra platform files such as `project-atlas/platforms/auth.md`, `project-atlas/platforms/testing.md`, `project-atlas/platforms/storage.md`, or `project-atlas/platforms/postgres.md` unless the user explicitly requests them. Put false-positive or secondary-platform notes in `stack.md`, `deployment.md`, `known-risks.md`, or `open-questions.md` instead.

Optional auxiliary files are allowed only when they support required files. For CFML repositories, `project-atlas/cfc-index.md` may be created as a generated full component index, but it must be linked from `code-map.md` or `platforms/cfml.md`; it does not replace the required CFC inventory coverage in those files.

Do not use aliases. `auth.md` does not satisfy `auth-and-access.md`; `application.md` does not satisfy `project-overview.md`, `stack.md`, or `architecture.md`; `api-catalog.md` does not satisfy `code-map.md` or `feature-index.md`; `project-atlas-index.md` does not satisfy `README.md`; `workflows.md` does not satisfy `agent-playbook.md`; `schema.md` does not satisfy `database.md`.

## Required generated structure for greenfield setup

Create:

```text
project-atlas/README.md
project-atlas/agent-playbook.md
project-atlas/.project-atlasignore
project-atlas/plan/README.md
project-atlas/plan/product-brief.md
project-atlas/plan/stack-proposal.md
project-atlas/plan/architecture-plan.md
project-atlas/plan/data-model-plan.md
project-atlas/plan/auth-plan.md
project-atlas/plan/feature-plan.md
project-atlas/plan/implementation-roadmap.md
project-atlas/plan/open-questions.md
project-atlas/context/project-overview.md
project-atlas/context/stack.md
project-atlas/context/architecture.md
project-atlas/context/code-map.md
project-atlas/context/feature-index.md
project-atlas/context/database.md
project-atlas/context/auth-and-access.md
project-atlas/context/conventions.md
project-atlas/context/dependency-map.md
project-atlas/context/testing.md
project-atlas/context/deployment.md
project-atlas/context/known-risks.md
project-atlas/context/glossary.md
project-atlas/context/open-questions.md
project-atlas/context/maintenance-log.md
project-atlas/platforms/
project-atlas/decisions/README.md
project-atlas/handoffs/README.md
project-atlas/snapshots/README.md
```

Greenfield context files may contain structured placeholders. Do not invent implementation details.

## Existing-codebase bootstrap workflow

Prefer deterministic scripts when filesystem access is available:

```bash
python scripts/bootstrap_atlas.py --repo /path/to/repo --mode existing
```

**Claude Code:** The Skill scripts are not present in the repository. Perform the bootstrap directly using file tools, guided by the steps below.

Use `--force` only when the user explicitly asks to overwrite existing Atlas files.

The bootstrap must:

1. Load `references/schemas/scan-and-creation-contract.md` and `references/schemas/output-manifest-and-verification.md` when needed.
2. Scan path metadata first; read limited text only from evidence files.
3. Detect stack and platform files to create.
4. Create the exact required manifest.
5. Populate concise repo-specific content. If an existing Atlas file is a known generic scaffold or placeholder, replace it even without `--force`; otherwise preserve hand-authored content unless `--force` is supplied.
6. Extract a CFML `.cfc` component inventory when `.cfc` files exist.
7. Run final verification after writing.
8. If required paths are missing or scaffold placeholders remain in repo-specific files, attempt one repair pass and verify again.
9. Fail clearly when verification still fails; never report success just because a check ran.

## CFML and CFC inventory rule

For repositories with `.cfc` files, every discovered `.cfc` must appear in `project-atlas/code-map.md` or `project-atlas/platforms/cfml.md`. A supplemental `project-atlas/cfc-index.md` may exist, but it is valid only when linked from `code-map.md` or `platforms/cfml.md`; it cannot be the only place the inventory is discoverable.

For each `.cfc`, list:

- relative path
- likely role when inferable
- methods/functions found using both tag syntax and script syntax
- extraction status: `extracted`, `no methods found`, `unreadable`, `ignored`, or `too large`

Recognize at least:

```cfml
<cffunction name="methodName">
public function methodName(...) {}
private any function methodName(...) {}
remote function methodName(...) {}
```

If extraction is not possible, still list the `.cfc` path with an explicit note. Missing `.cfc` entries are verification failures.

## Final verification rule

Before reporting completion, verify:

1. Every exact required file exists.
2. Every exact required directory exists.
3. Every detected or selected platform file exists under `project-atlas/platforms/`.
4. No alias file is counted as satisfying a required file.
5. No Skill-internal generated paths exist under the generated output: `project-atlas/references/`, `project-atlas/scripts/`, `project-atlas/templates/`, `project-atlas/agents/`, or `project-atlas/SKILL.md`.
6. No repo-specific required file is left as a generic scaffold or placeholder. The scaffold exception applies only to `decisions/README.md`, `handoffs/README.md`, `snapshots/README.md`, `.project-atlasignore`, and `maintenance-log.md`.
7. No unexpected platform files exist unless explicitly selected. For example, do not create `platforms/postgres.md` just to explain a Postgres false positive.
8. CFML repositories include complete `.cfc` inventory coverage.
9. `maintenance-log.md` records the run and verification result.

If verification fails, return exact missing paths and say Atlas generation is incomplete.

## Maintenance workflow

```bash
python scripts/maintain_atlas.py --repo /path/to/repo --mode update
python scripts/maintain_atlas.py --repo /path/to/repo --mode check
```

**Claude Code:** The Skill scripts are not present in the repository. Update the relevant Atlas files directly using file tools, following the rules in `project-atlas/agent-playbook.md`.

Maintenance must update only durable project knowledge. Do not update Atlas for formatting-only, comment-only, temporary debug, or reverted changes.

Update relevant files only:

- `feature-index.md` for feature movement/addition/removal
- `code-map.md` for routes, services, components, entry points, or major directories
- `auth-and-access.md` for auth, sessions, permissions, API auth, or gated access
- `database.md` for schema, migrations, query conventions, or data access
- `stack.md` and `dependency-map.md` for runtimes, frameworks, dependencies, or infrastructure
- `testing.md` for testing frameworks or key test locations
- `deployment.md` for build/deploy/hosting/Docker/CI changes
- `known-risks.md` for fragile, security-sensitive, or data-sensitive areas
- `maintenance-log.md` for every meaningful Atlas maintenance run

## References

Load only the relevant reference file:

- Existing bootstrap: `references/workflows/existing-codebase-bootstrap.md`
- Greenfield setup: `references/workflows/greenfield-bootstrap.md`
- Maintenance: `references/workflows/maintenance.md`
- Handoff: `references/workflows/handoff.md`
- Scan/create contract: `references/schemas/scan-and-creation-contract.md`
- Exact output manifest: `references/schemas/output-manifest-and-verification.md`
- Final verification checklist: `references/schemas/final-verification-checklist.md`
- Platform guidance: `references/platforms/*.md`

## Local script quick start

When the user wants the Skill run locally, tell them to unzip the Skill package and run:

```bash
python project-atlas/scripts/bootstrap_atlas.py --repo /path/to/repo --mode existing
python project-atlas/scripts/maintain_atlas.py --repo /path/to/repo --mode check
```
