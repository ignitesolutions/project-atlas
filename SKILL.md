---
name: project-atlas
description: Maintain project-atlas/, a repository's durable current-state context that lets any agent or harness resume work. Invoked with no other request, brings an existing Atlas current (or bootstraps one). Use at session start to resume or check Atlas freshness, at session close-out to record state, after durable code, schema, or deploy changes, to bootstrap an existing or greenfield repo, to tidy plans, tasks, and logs, or to verify the Atlas.
---

# Project Atlas

Keep repository context current enough that the next agent, in any harness, can read
`project-atlas/status.md` and the playbook and pick up the work without rescanning.

Scripts live in this skill's directory (`<skill-dir>/scripts/`), never in the target repository.
Every script takes `--repo /path/to/repo` and prints a JSON envelope (`status`, `diagnostics`,
plus mode-specific fields). Report diagnostic codes, paths, and suggested repairs exactly.

## Default action: bring the Atlas current

When the skill is invoked with no more specific request, this is the job. The repository is the
current working directory unless the user names another.

- **No `project-atlas/atlas.json`:** go to "Existing repository bootstrap" (or "Greenfield" when
  there is no application source yet).
- **Atlas exists:** run

  ```bash
  python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode auto
  ```

  Auto mode records what changed since the last Atlas update, runs a full update (generated
  evidence, skill-version reconcile, missing structure, plan moves), and returns the post-update
  status. Then finish the hand-authored half, in order:

  1. **Changed files.** For each path in `changed_since_last_update`, read what changed
     (`git diff <previous_atlas_commit> -- <path>` in Git repos; the file itself otherwise) and
     update the documents the playbook's maintenance table maps it to. A change that is
     formatting-only, debug-only, or reverted needs no update. When `changed_count` exceeds the
     list, work from `git diff --stat <previous_atlas_commit>` by directory.
  2. **Mechanical repairs from `warnings`, without asking:** `LOG_OVERSIZE` → `--mode compact-log`,
     then summarize the archived entries in the Earlier history entry; `TASKS_OVERSIZE` →
     `audit_plans.py --mode apply --archive-completed`; stray `.sql` at the Atlas root → move it
     into `sql/` and add its ledger row. Contract findings (`ENRICHMENT_REQUIRED`, `CONTRACT_*`,
     `UNRESOLVED_SCAFFOLD`) → complete them as described under "Existing repository bootstrap",
     or mark the criterion `unknown` with an impact note.
  3. **Needs the user (ask, one question at a time):** `--mode convert`, `--force`, folding a
     duplicate task list (`todo.md`, `task-list.md`) into `tasks.md`, moving a plan back to
     `in-flight/`, and resolving orphaned plans or broken plan links.
  4. **`status.md`.** Rewrite it from evidence: `tasks.md`, `plans/in-flight/`, the changed files,
     and `git log <previous_atlas_commit>..HEAD`. Write only what that evidence supports; put
     anything uncertain under Blocked as a question for the user.
  5. **Log.** Append one maintenance-log entry of five lines or fewer.
  6. **Confirm.** Rerun `--mode status`. The job is done when it returns `"status": "passed"`, or
     when every remaining `next_actions` item is one from step 3 awaiting the user's answer.
     Report what changed in the Atlas and list those open items.

## Boundaries

- Write Atlas output only under repository-root `project-atlas/`, plus sentinel-managed sections in root `AGENTS.md` and `CLAUDE.md`.
- Keep this skill's `scripts/`, `templates/`, `references/`, `agents/`, and `SKILL.md` out of the target repository.
- Record names, locations, and access patterns of secrets, never values (passwords, keys, tokens, connection strings). The one exception is the opt-in database connection setup, which stores credentials only in the gitignored `project-atlas/local/`, never in a tracked Atlas document.
- Record only facts the source material supports. Put uncertain inferences in `open-questions.md` (or the "Open questions" section of `design-rules.md`).
- Preserve hand-authored prose. Automated maintenance replaces only digest-owned generated files and `<!-- project-atlas:generated:* -->` blocks unless the user explicitly requests `--force`.
- `status.md`, `tasks.md`, and `launch-checklist.md` are living documents: written once at creation, then hand-maintained for the life of the project. No script regenerates them, not even with `--force`; only their managed sections sync. To reset one, delete it and rerun bootstrap.
- Treat partial scans as failures unless the user explicitly accepts `--allow-partial-scan`.

## Every session

This is the branch that runs most often; the root `AGENTS.md`/`CLAUDE.md` section tells every
harness to follow it.

**Start:** read `status.md`, then `agent-playbook.md` (its "Read On Demand" table names the other
files to read for the task). Then check freshness:

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode status
```

Status mode hashes only files Git or mtimes say changed, so it is cheap. It reports
`lifecycle_state` as `<state> @ <commit>`, files changed since that commit, task and plan counts,
skill-version skew, hygiene `warnings`, and `next_actions`. `"status": "attention"` means
something in `next_actions` needs doing before the Atlas can be trusted.

**Close-out** (any session that changed code, schema, config, or plans):

1. Rewrite `status.md` in place: Now, Next (top 3, recommended first), Blocked, Unverified, Pending environment actions. Under 40 lines; link rather than restate.
2. Update `tasks.md` checkboxes; mark blocked tasks `— BLOCKED: reason`.
3. Update the Atlas files the playbook's maintenance table names for the change: `launch-checklist.md` for any dev/stage/live difference, the `sql/README.md` execution ledger for new SQL.
4. Append one maintenance-log entry of five lines or fewer (date, summary, links).
5. Run `maintain_atlas.py --mode update`.

Close-out is done when `--mode status` returns `"status": "passed"`.

## Choose a mode

1. **Existing repository:** bootstrap evidence and the compact core.
2. **Greenfield:** scaffold planning/context documents without inventing facts.
3. **Maintenance:** update generated evidence for durable changes.
4. **Verification:** check structure, evidence freshness, or semantic enrichment.

## Maintenance

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode update
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode update --changed-since HEAD~1
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode update --paths components/UserService.cfc --domain auth
```

Valid domains are `code`, `architecture`, `database`, `auth`, `deployment`, `operations`, and `all`; changed paths map to every domain they match, plus `code`. No-change updates are no-ops apart from recording the current commit. Update only durable knowledge; formatting-only, temporary debug, and reverted changes need no update.

Every update also reconciles plans with `tasks.md` (below) and returns `warnings` for hygiene drift.

Git repositories use Git-native tracked/untracked discovery and exact `.gitignore` behavior; non-Git repositories use a filesystem fallback. Parsed evidence is cached by content digest under `project-atlas/.cache/`; source excerpts are not cached.

## Plans, tasks, and logs

`plans/in-flight/` and `plans/completed/` hold saved implementation plans; `tasks.md` lines link to them. A task line with exactly one Markdown link into `plans/` is tracked wherever the link sits. `--mode update` moves the plan of a checked task to `completed/` and fixes its link. Moving a plan back to `in-flight/` for an unchecked task is reported, never done automatically.

```bash
python3 <skill-dir>/scripts/audit_plans.py --repo /path/to/repo --mode check
python3 <skill-dir>/scripts/audit_plans.py --repo /path/to/repo --mode apply [--archive-completed]
```

`apply` performs moves in both directions. `--archive-completed` moves `## ` phases whose boxes are all checked, verbatim, to `tasks-archive.md`. The script never invents task text, deletes files, or guesses at orphaned plans or broken links; it reports them.

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode compact-log
```

`compact-log` keeps the newest maintenance-log entries (by heading date, about 100 lines) and moves the rest verbatim to `maintenance-log-archive.md`, leaving an `## Earlier history` entry pointing there. Then summarize the archived entries in that entry in one paragraph.

Hygiene warnings never fail verification. They are `STATUS_UNFILLED`, `STATUS_STALE`, `LOG_OVERSIZE`, `TASKS_OVERSIZE`, `ATLAS_STRAY_FILE`, and plan-audit findings. A duplicate task list (`todo.md`, `task-list.md`) is an `INVALID_ALIAS` failure: fold it into `tasks.md`.

## Verification and lifecycle

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode check --level structure
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode check --level evidence
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode check --level semantic
```

- `structure`: required core, root sentinels, generated paths, slots, and platform files.
- `evidence`: structure plus source existence, repository fingerprint, scan completeness, and CFML coverage.
- `semantic`: evidence plus completed human interpretation contracts.

Lifecycle states are `scaffolded`, `evidence-generated`, `enrichment-required`, `verified`, and `stale`. A recorded state is only as current as its commit; read it from `--mode status`. Report full completion only when semantic verification returns `verified`.

`atlas.json` is the machine-readable source for schema version, lifecycle state, repository fingerprint/Git commit, platforms, generated-section ownership, source paths, file fingerprints, scan coverage, and extraction warnings.

Use `--generation-mode existing|greenfield|auto` when mode inference needs to be explicit. Migrate an older manifest with `--mode migrate`; convert an implemented greenfield project with `--mode convert`.

## Skill version reconciliation

`VERSION` at the skill root is stamped into each repo's `atlas.json` as `skill_version`. Bump it whenever required structure or skill-authored guidance changes. A mismatch reports `SKILL_VERSION_STALE`; `--mode reconcile` (or any normal `--mode update`) backfills missing files and resyncs skill-authored managed sections. Hand-edited sections stop syncing until `--force`. To bring several repositories current, run `--mode reconcile` once per repository.

## Existing repository bootstrap

First run the interview in `references/bootstrap-interview.md`: site URL, design reference, optional live-site scan, and database confirmation. Then:

```bash
python3 <skill-dir>/scripts/bootstrap_atlas.py --repo /path/to/repo --mode existing --site-url "https://example.com"
```

The compact core is `README.md`, `status.md`, `agent-playbook.md`, `project-overview.md`, `architecture.md`, `code-map.md`, `operations.md`, `open-questions.md`, `maintenance-log.md`, `sql/README.md`, and `atlas.json`. Specialized documents are created only when matching evidence exists; platform documents are detection-driven.

Bootstrap produces evidence and lifecycle state `enrichment-required`; it does not claim semantic completion. Read entry points, project docs, controllers/routes, primary services, and operational configuration. Complete each JSON criterion in the `project-atlas:contract` marker in `project-overview.md` and `architecture.md`: `complete` with a supported note and valid evidence paths, `unknown` with an impact note, or leave it `pending`. Finish by filling in `status.md`.

For CFML, the generated inventory covers every discovered `.cfc`: its inferred role, extracted tag/script methods, and extraction status. Small inventories live in the managed `code-map.md` section; inventories at or above `--cfc-index-threshold` live once in `cfc-index.md`, linked from the map.

## Greenfield

Run the same interview, then `bootstrap_atlas.py --mode greenfield --site-url "..."`. Interview the user to resolve plan files and their criterion contracts. Greenfield verification uses its own manifest and required structure. Once implementation evidence exists, run `maintain_atlas.py --mode convert`; `--mode status` suggests this.

## Content standards

- Prefer compact tables, repository-relative paths, and explicit uncertainty.
- Keep complete inventories in one location and link to them from summaries.
- Describe each entity or module (service, table, subsystem) fully in one primary document; every other mention is a one-line pointer to it.
- Create decisions, handoffs, tasks, launch checklists, and specialized domain documents only when evidence or active work warrants them. `status.md` is the resume path; a handoff is optional deep context for one piece of work.
- `maintenance-log.md` is a compact append-only index, not a changelog: at most five lines per entry. Narrate implementation detail in plans or `decisions/`. Add an entry by appending at the end without reading or rewriting the file; only `compact-log` and the Earlier history summary rewrite it.
- Keep `.sql` files in `project-atlas/sql/`, with a row in its execution ledger.
- Read `references/file-contracts.md` for semantic enrichment and `references/platform-guidance.md` for detection details.
- Without Python, use `templates/` as the content source and edit files by hand under the same rules.
