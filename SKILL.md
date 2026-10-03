---
name: project-atlas
description: Build and maintain compact, AI-readable repository context in project-atlas/. Use for existing-codebase bootstrap, greenfield planning, incremental Atlas maintenance, freshness checks, code maps, CFML inventories, deployment context, handoffs, or project-atlas verification.
---

# Project Atlas

Create durable repository context that future agents can trust without rescanning everything.

## Boundaries

- Write Atlas output only under repository-root `project-atlas/`, plus sentinel-managed sections in root `AGENTS.md` and `CLAUDE.md`.
- Never copy this Skill's `scripts/`, `templates/`, `references/`, `agents/`, or `SKILL.md` into a target repository.
- Never record secret values (passwords, keys, tokens, connection strings) — names, locations, and access patterns only. The one narrow exception is the opt-in database connection setup (see "Database connection setup" below): with explicit user consent, it may collect and store DB credentials in a gitignored local file outside version control — never inside `database.md` or any other tracked Atlas document.
- Never invent facts the source material doesn't support — product, stack, data, auth, deployment, environment, or design/UI convention facts alike. Put uncertain inferences in `open-questions.md` (or `design-rules.md`'s "Open questions" section) instead.
- Preserve hand-authored prose. Automated maintenance may replace only digest-owned generated files and `<!-- project-atlas:generated:* -->` blocks unless the user explicitly requests `--force`.
- `tasks.md` and `launch-checklist.md` are living documents: once created, they accumulate freeform hand-authored entries for the life of the project.
- Never whole-file regenerate either after creation — not via scaffold-detection, not even with `--force`.
- Only their managed sections (if any) sync automatically; to reset one, delete it and rerun bootstrap.
- Treat partial scans as failures unless the user explicitly accepts `--allow-partial-scan`.

## Choose a mode

1. Existing repository: bootstrap evidence and the compact core.
2. Greenfield: scaffold planning/context documents without inventing facts.
3. Maintenance: update generated evidence for durable changes.
4. Verification: check structure, evidence freshness, or semantic enrichment.

## Existing repository bootstrap

Before running bootstrap, ask the user for the public-facing site URL (so tests can later be
generated and run against it) and pass it through — it lands in `agent-playbook.md`. If none
exists yet, pass an empty string.

Also ask the user, as a separate question, whether there's a design system or set of design
docs/mockups to reference when building new pages, and if so, what folder holds them. Don't
assume none exists just because nothing was detected — this is a question to the user, not a
scan. See "Design reference setup" below for what to do with the answer.

If the user gave a non-empty site URL above, ask one more question: whether to scan that live
site to learn how it's designed and fold those findings into `design-rules.md` too. This is
opt-in — a URL being present only means it's worth asking, not that scanning is assumed.

Run:

```bash
python3 <skill-dir>/scripts/bootstrap_atlas.py --repo /path/to/repo --mode existing --site-url "https://example.com"
```

The compact core is `README.md`, `agent-playbook.md`, `project-overview.md`, `architecture.md`, `code-map.md`, `operations.md`, `open-questions.md`, `maintenance-log.md`, and `atlas.json`. Specialized documents are created only when matching evidence exists. Platform documents are detection-driven.

Bootstrap produces evidence and lifecycle state `enrichment-required`; it does not claim semantic completion. Read entry points, project docs, controllers/routes, primary services, and operational configuration. Complete each JSON criterion in the `project-atlas:contract` marker in `project-overview.md` and `architecture.md`: use `complete` with a supported note and valid evidence paths, `unknown` with an impact note, or leave it `pending`.

For CFML, the generated inventory includes every discovered `.cfc`, its inferred role, extracted tag/script methods, and extraction status. Small inventories live in the managed `code-map.md` section; inventories at or above `--cfc-index-threshold` live once in `cfc-index.md` and are linked from the map.

Once the presence and engine of a database is confirmed with the user (see "Database connection
setup" below — detected evidence is a hypothesis to confirm, not a fact to act on), `database.md`
(datasource names, query conventions, migration process) and `schema.md` (raw table/column/key/index
structure) are both created at bootstrap time as stubs for the agent to populate — never with
connection values.

### Database connection setup

Confirming a database's presence/engine with the user is mandatory before creating
`database.md`/`schema.md` stubs — see the bootstrap paragraph above. If the user opts into live
connection setup, stop and read `references/database-connection-setup.md` now; follow its gate
exactly (one question at a time, no silent skip). If the user declines, record the explicit skip
in `database.md` and continue without a connection.

### Design reference setup

Ask this as its own question, separate from any other prompt: "Is there a design system or set of
design docs/mockups to reference when building new pages? If so, what folder should I look in?"

- No / none → skip. No `design-rules.md` is written, unless the live-site scan below produces one
  on its own.
- A folder is named → confirm it exists, then read its contents (mockups, style guides, exported
  screens, design tokens, component libraries, brand/style guidelines — whatever is actually
  there) and write `project-atlas/design-rules.md` summarizing what can be gleaned: color
  palette, typography, spacing/layout conventions, component patterns, and any explicitly stated
  guidelines. Back each point with a repository-relative evidence path to the source file. Put
  anything inferred rather than directly stated under an "Open questions" section instead of
  asserting it as fact.

If the user opted in to scanning the live site (see the site-URL question above), fetch a small
representative sample of pages from it (e.g. home, a couple of interior pages) and add a
`## Live site` section to `design-rules.md` summarizing what the rendered site itself shows:
observed color palette, typography, layout/component patterns, and navigation conventions. Cite
the page URL as the evidence source for each point instead of a repository path, and put anything
uncertain under the same "Open questions" section rather than asserting it. This runs whether or
not a design folder was also named — if neither a folder nor a scan is opted into, no
`design-rules.md` is written at all.

`design-rules.md` is hand-authored prose, like `database.md` and `known-risks.md` — it is never
whole-file regenerated by automated maintenance. If the referenced design folder changes later,
refresh it manually (or re-run this step).

## Maintenance

Run a normal incremental update:

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode update
```

Focus work when the change surface is known:

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode update --changed-since HEAD~1
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode update --paths components/UserService.cfc --domain auth
```

Valid domains are `code`, `architecture`, `database`, `auth`, `deployment`, `operations`, and `all`. No-change updates are no-ops. Update only durable knowledge; ignore formatting-only, temporary debug, and reverted changes.

Git repositories use Git-native tracked/untracked discovery and exact `.gitignore` behavior. Non-Git repositories use the documented filesystem fallback. Parsed evidence is cached by content digest under `project-atlas/.cache/`; source excerpts are not cached.

## Plan/task cleanup

`project-atlas/plans/in-flight/` and `project-atlas/plans/completed/` hold saved implementation
plans (see the Plan Tracking Protocol in `agent-playbook.md`); `tasks.md` lines link to them and
track completion via checkbox state. To reconcile plan file location with `tasks.md` state:

```bash
python3 <skill-dir>/scripts/audit_plans.py --repo /path/to/repo --mode check   # read-only report
python3 <skill-dir>/scripts/audit_plans.py --repo /path/to/repo --mode apply   # auto-fix + report
```

`apply` moves plan files between `in-flight/` and `completed/` and rewrites stale link paths in
`tasks.md` when it can infer the right state confidently. It never invents task text, deletes
files, or guesses at orphaned plans or broken links — those are always reported for a human or
agent to resolve.

## Skill version reconciliation

The installed skill's version lives in `VERSION` at the skill root and is stamped into each
repo's `project-atlas/atlas.json` as `skill_version`. Whoever changes required structure or
skill-authored guidance content should bump `VERSION`.

When a repo's recorded `skill_version` doesn't match the installed skill, `check` reports
`SKILL_VERSION_STALE`. Bring it current with:

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode reconcile
```

A normal `--mode update` also self-heals this automatically the next time it runs, even without
`--mode reconcile` — no separate step is required as part of routine maintenance. Both modes
route through the same repair path already used for missing structure: wholly-missing
files/directories are backfilled, and skill-authored guidance sections (in `agent-playbook.md`
and `tasks.md`) are synced through the same digest-tracked managed-section mechanism as
`code-map.md`'s evidence block. Nothing is ever overwritten outside those tracked sections, and
a section stops syncing the moment a user hand-edits it — `--force` is required to resync it
after that.

## Verification and lifecycle

Run one of:

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode check --level structure
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode check --level evidence
python3 <skill-dir>/scripts/maintain_atlas.py --repo /path/to/repo --mode check --level semantic
```

- `structure`: required core, root sentinels, generated paths, slots, and platform files.
- `evidence`: structure plus source existence, repository fingerprint, scan completeness, and CFML coverage.
- `semantic`: evidence plus completed human interpretation contracts.

Lifecycle states are `scaffolded`, `evidence-generated`, `enrichment-required`, `verified`, and `stale`. Report diagnostic codes, paths, and suggested repairs exactly. Do not report full completion unless semantic verification returns `verified`.

`atlas.json` is the machine-readable source for schema version, lifecycle state, repository fingerprint/Git commit, platforms, generated-section ownership, source paths, file fingerprints, scan coverage, and extraction warnings.

Use `--generation-mode existing|greenfield|auto` when mode inference needs to be explicit. Migrate an older manifest with `--mode migrate` and convert an implemented greenfield project with `--mode convert`.

## Greenfield

Run `bootstrap_atlas.py --mode greenfield --site-url "..."`. Ask the user for a public-facing site URL here too — a staging URL may already exist even before implementation; pass an empty string if nothing is deployed yet. Ask the design-reference question here too (see "Design reference setup" above) — greenfield pages need conventions to build against just as much as an existing codebase does. Interview the user to resolve plan files and their criterion contracts. Greenfield verification uses its own manifest and required structure. Run `maintain_atlas.py --mode convert` once implementation evidence exists.

## Content standards

- Prefer compact tables, repository-relative paths, and explicit uncertainty.
- Keep complete inventories in one location and link to them from summaries.
- Put low-confidence inferences in `open-questions.md`.
- Create decisions, handoffs, tasks, launch checklists, and specialized domain documents only when useful evidence or active work warrants them.
- `maintenance-log.md` is a compact append-only index, not a changelog: a few lines per run (date, one-line summary, links to `decisions/`/paths). Narrate implementation detail in `decisions/` or leave it to git history. Once it grows past roughly 150 lines, summarize the oldest entries into a single "Earlier history" paragraph instead of letting it grow unbounded.
- Adding a routine entry to `maintenance-log.md` is an append: add it at the end without reading or rewriting the rest of the file. The `append_log()` helper does this at the file-I/O level for script-driven writes; the same rule applies when an agent adds an entry by hand — a full read-and-rewrite is reserved for the periodic history-summarization pass above, never for a single new entry.
- Generated or hand-authored `.sql` files (migrations, seeds, ad hoc queries) belong under `project-atlas/sql/`, never loose at the Atlas root.
- When one entity or module (a service, table, subsystem, etc.) is described in more than one document, designate a single primary/source-of-truth file for its full description and make every other mention a one-line pointer with a link back to it — never re-describe the same details in multiple places.
- Read `references/file-contracts.md` for semantic enrichment and `references/platform-guidance.md` for detection details.
