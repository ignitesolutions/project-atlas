# Project Atlas

**Durable, AI-readable project context that lets any coding agent pick up where the last one left off.**

Project Atlas is an [agent skill](https://docs.claude.com/en/docs/claude-code/skills) plus a set of
standard-library Python scripts. Together they keep a `project-atlas/` folder in your repository
current: what the application does, how it is built, where things live, what is in progress, what
is blocked, and what changed since anyone last looked. A new session can start cold in any harness
(Claude Code, Codex, Cursor, or a plain chat with file access), read two short files, and get to
work without rescanning the codebase or re-asking you for context.

```
you ──▶ /project-atlas ──▶ agent runs maintain_atlas.py --mode auto
                             │  1. lists files changed since the last Atlas update
                             │  2. refreshes generated evidence, plans, structure
                             │  3. reports status + next_actions
                             ▼
                        agent updates the hand-written docs, rewrites status.md,
                        appends one log line, re-checks ──▶ "status": "passed"
```

---

## Contents

- [Why](#why)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [The everyday loop](#the-everyday-loop)
- [What gets generated](#what-gets-generated)
- [Command reference](#command-reference)
- [JSON output](#json-output)
- [Verification and lifecycle](#verification-and-lifecycle)
- [Semantic contracts](#semantic-contracts)
- [Plans, tasks, and logs](#plans-tasks-and-logs)
- [Diagnostics and warnings reference](#diagnostics-and-warnings-reference)
- [Safety and ownership model](#safety-and-ownership-model)
- [Optional setup: database, design reference, site URL](#optional-setup-database-design-reference-site-url)
- [Platform detection and CFML support](#platform-detection-and-cfml-support)
- [Upgrading the skill](#upgrading-the-skill)
- [Using an Atlas without the skill](#using-an-atlas-without-the-skill)
- [Repository layout](#repository-layout)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)

---

## Why

Coding agents lose everything between sessions. The usual workarounds each fail in their own way:

- **Rescanning the repo every session** is slow and expensive, and the agent still can't recover
  *why* things are the way they are.
- **Handoff notes in chat** vanish with the conversation and never reach a different tool.
- **Ad-hoc files** (`todo.md`, `claude-handoff.md`, `notes.md`) multiply, contradict each other,
  and go stale silently.
- **Hand-written docs** drift from the code, and nothing tells you that they have.

Project Atlas replaces these with one structured folder plus scripts that can **prove** whether that
folder is current. Each document has a defined job. Machine-generated evidence sits in fenced
blocks the scripts own, and human or agent prose sits outside them and is never overwritten.
Freshness is checked against Git, so a stale Atlas reports `attention` instead of pretending to be
current.

## How it works

Project Atlas splits the work into two halves.

| Half | Who does it | What it covers |
| --- | --- | --- |
| **Evidence** | The scripts | Repository scan, stack and platform detection, code maps, CFML component inventories, file fingerprints, Git commit tracking, required structure, plan-file reconciliation, hygiene checks |
| **Interpretation** | The agent (or you) | What the app does and for whom, request flow and boundaries, risks, decisions, current work state, next steps |

The two meet in three places:

1. **`project-atlas/status.md`** is the "resume here" file: Now, Next, Blocked, Unverified, and
   Pending environment actions. It is rewritten at the end of every working session.
2. **`project-atlas/agent-playbook.md`** holds the rules, a "Read On Demand" routing table (task
   touches X → read Y), and a maintenance table (change type → files to update).
3. **A managed section in the root `AGENTS.md` and `CLAUDE.md`** tells every harness to read those
   two files first and to follow a session close-out checklist.

`project-atlas/atlas.json` is the machine-readable manifest. It records the Git commit, per-file
content fingerprints, lifecycle state, generated-section ownership digests, detected platforms, and
the skill version that last wrote the Atlas.

## Requirements

- **Python 3** with the standard library only; there are no third-party packages. Developed and
  tested on Python 3.12.
- **A POSIX system** (Linux or macOS). The scripts use `fcntl` file locking, so on Windows run them
  under WSL.
- **Git** (optional, recommended). Without Git, discovery and drift detection fall back to the
  filesystem and file modification times.
- **An agent harness that supports skills** (optional). The scripts run standalone, and an Atlas is
  plain Markdown that any tool can read.

## Installation

The skill is a directory containing `SKILL.md`, `scripts/`, `templates/`, and `references/`. Install
it wherever your harness looks for skills. It is never copied into your project repositories.

**Claude Code (user-level, available in every project):**

```bash
git clone https://github.com/<owner>/project-atlas.git ~/.claude/skills/project-atlas
```

**Claude Code (one project only):**

```bash
git clone https://github.com/<owner>/project-atlas.git .claude/skills/project-atlas
```

**Harnesses that read the shared `~/.agents/skills/` directory:**

```bash
git clone https://github.com/<owner>/project-atlas.git ~/.agents/skills/project-atlas
```

**No skill support at all:** clone it anywhere and call the scripts by path. Every script takes
`--repo /path/to/your/project`.

Check the install by running the test suite:

```bash
cd ~/.claude/skills/project-atlas
python3 -m unittest tests/test_project_atlas.py
```

> **Avoid duplicate installs.** If the same skill is installed twice (for example, once locally and
> once synced from claude.ai), the harness may load the older copy. Keep exactly one, and confirm
> with `cat VERSION`.

In the examples below, `<skill-dir>` means wherever you installed the skill.

## Quick start

### Existing codebase

In an agent session, from your project root:

```
/project-atlas
```

With no Atlas present, the skill starts the **bootstrap interview**. It asks one question at a time:

1. The public-facing site URL, which is recorded for agent-run tests later.
2. Whether a design system or mockup folder exists, and where.
3. Whether to scan the live site for design conventions (only asked if you gave a URL).
4. Whether the project uses a database, and which engine. If you opt in, it also helps set up a
   verified local connection.

It then runs the bootstrap script and does the **enrichment pass**: it reads entry points,
controllers, services, and configuration, and writes the interpretation the scripts can't.

Running the script by hand:

```bash
python3 <skill-dir>/scripts/bootstrap_atlas.py --repo . --mode existing --site-url "https://example.com"
```

Bootstrap leaves the Atlas in lifecycle state `enrichment-required`. That is intentional: a
generated file list is not understanding. The Atlas reaches `verified` only after the semantic
contracts in `project-overview.md` and `architecture.md` are completed with evidence.

### New (greenfield) project

```bash
python3 <skill-dir>/scripts/bootstrap_atlas.py --repo . --mode greenfield --site-url ""
```

Greenfield mode scaffolds planning documents (`plan/`) and future-context documents (`context/`)
without inventing facts. Work through the plan with the agent. Once real implementation exists,
convert the Atlas:

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo . --mode convert
```

`--mode status` tells you when it's time to convert.

### Bringing an Atlas current

```
/project-atlas
```

Invoked with no other request on a repository that already has an Atlas, the skill brings it current
(see [Auto mode](#auto-mode-what-a-bare-invocation-does)). This is the command to run whenever you
come back to a project.

## The everyday loop

### Session start

The root `AGENTS.md`/`CLAUDE.md` section instructs every harness to:

1. Read `project-atlas/status.md`.
2. Read `project-atlas/agent-playbook.md`, then only the files its "Read On Demand" table names for
   the task.
3. Check freshness:

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo . --mode status
```

Status mode is cheap (typically well under a second). It lists files without hashing them, then
hashes only the files Git or modification times say may have changed. Without the skill, an agent
can compare `git_commit` in `atlas.json` with `git rev-parse HEAD`.

### Session close-out

Before ending any session that changed code, schema, configuration, or plans:

1. Rewrite `status.md` in place (under 40 lines).
2. Update `tasks.md` checkboxes; mark blocked work `— BLOCKED: reason`.
3. Update the Atlas files the playbook's maintenance table names for the change, including
   `launch-checklist.md` for anything that differs between dev, stage, and live, and the
   `sql/README.md` execution ledger for new SQL.
4. Append **one** maintenance-log entry of at most five lines.
5. Run `maintain_atlas.py --mode update`.

Close-out is **done** when `--mode status` returns `"status": "passed"`. Formatting-only,
comment-only, debug, and reverted changes need no Atlas update.

### Auto mode: what a bare invocation does

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo . --mode auto
```

1. Records every application file changed since the last Atlas update (up to 300 paths, plus a
   total count), along with the previous Atlas commit.
2. Runs a full `update`: generated evidence, skill-version reconcile, missing structure, and plan
   moves.
3. Returns the post-update status with one consolidated `next_actions` list.

The skill then has the agent finish the hand-written half, in order:

| Step | Action | Asks first? |
| --- | --- | --- |
| 1 | For each changed file, read the diff and update the documents it maps to | No |
| 2 | Mechanical repairs: compact an oversized log, archive completed task phases, move stray `.sql` into `sql/`, complete pending contracts | No |
| 3 | Risky repairs: `--mode convert`, `--force`, folding `todo.md` into `tasks.md`, reopening a plan, resolving orphaned plans | **Yes** |
| 4 | Rewrite `status.md` from evidence (tasks, in-flight plans, changed files, `git log`) | No |
| 5 | Append one log entry | No |
| 6 | Re-run `--mode status` and report what changed and what is waiting on you | No |

## What gets generated

### Existing-codebase Atlas

```
your-repo/
├── AGENTS.md                      # managed section between <!-- project-atlas:start/end -->
├── CLAUDE.md                      # same section; your other content is preserved
└── project-atlas/
    ├── README.md                  # entry point for humans
    ├── status.md                  # ★ resume here (living document)
    ├── agent-playbook.md          # rules, routing table, maintenance table
    ├── project-overview.md        # purpose, users, workflows (semantic contract)
    ├── architecture.md            # request flow, boundaries (semantic contract)
    ├── code-map.md                # navigation + generated evidence block
    ├── operations.md              # test, deploy, config, monitoring, recovery
    ├── open-questions.md          # every unconfirmed inference, as a question
    ├── maintenance-log.md         # compact append-only index
    ├── atlas.json                 # manifest: commit, fingerprints, lifecycle, ownership
    ├── .project-atlasignore       # Atlas-specific scan exclusions
    ├── decisions/                 # architecture decision records (README + TEMPLATE)
    ├── sql/                       # all .sql files + execution ledger (README.md)
    ├── plans/
    │   ├── in-flight/             # active implementation plans
    │   └── completed/             # finished plans, moved verbatim
    ├── platforms/                 # one file per detected platform (cfml.md, mssql.md, …)
    └── (conditional, created when evidence warrants)
        auth-and-access.md  database.md  schema.md  deployment.md  testing.md
        known-risks.md  launch-checklist.md  cfc-index.md  design-rules.md  tasks.md
```

| File | Answers | Written by |
| --- | --- | --- |
| `status.md` | Where does work stand right now? What's next, blocked, or unverified? | Agent, every session |
| `agent-playbook.md` | What are the rules here, and what should I read for this task? | Template + managed skill section |
| `project-overview.md` | What does this app do, for whom, and through which workflows? | Agent (contract-checked) |
| `architecture.md` | How does a request flow, and where are the boundaries? | Agent (contract-checked) |
| `code-map.md` | Where are the entry points, routes, services, and data access? | Agent + generated block |
| `operations.md` | How is it tested, deployed, configured, monitored, and recovered? | Agent + generated block |
| `open-questions.md` | What don't we know yet, and why does it matter? | Agent |
| `tasks.md` | What is the task list, by phase? | Agent (living document) |
| `launch-checklist.md` | What differs between dev, stage, and live? | Agent (living document) |
| `sql/README.md` | Which SQL files exist, and where has each one run? | Agent |
| `design-rules.md` | What are the UI conventions for new pages? | Agent, from your design folder or live site |
| `decisions/NNNN-*.md` | Why was this lasting choice made, and what was rejected? | Agent |
| `cfc-index.md` | The complete CFML component inventory (25+ components) | Generated |
| `platforms/*.md` | Platform-specific evidence (datasources, syntax, files) | Generated |

Templates also exist for `stack.md`, `feature-index.md`, `conventions.md`, `dependency-map.md`, and
`glossary.md`. Agents create those when the project needs them.

### Greenfield Atlas

```
project-atlas/
├── README.md  status.md  agent-playbook.md  tasks.md  launch-checklist.md  atlas.json
├── plan/        product-brief, stack-proposal, architecture-plan, data-model-plan,
│                auth-plan, feature-plan, implementation-roadmap, open-questions
├── context/     project-overview, stack, architecture, code-map, feature-index, database,
│                schema, auth-and-access, conventions, dependency-map, testing, deployment,
│                known-risks, glossary, open-questions, maintenance-log
├── decisions/  handoffs/  snapshots/  sql/  plans/in-flight/  plans/completed/
```

`plan/` (singular) holds the up-front product and architecture plan. `plans/` (plural) holds
implementation plans, exactly as in existing mode.

### Living documents

`status.md`, `tasks.md`, and `launch-checklist.md` are written **once** and then belong to you. No
script regenerates them, not even with `--force`. Only clearly marked managed sections inside them
sync. To reset one, delete it and rerun bootstrap or update.

### Recommended `.gitignore` entries

Commit the Atlas so every clone and every agent shares it, but ignore its machine-local parts:

```gitignore
project-atlas/.cache/
project-atlas/.update.lock
project-atlas/local/
```

(The database connection setup flow adds `project-atlas/local/` to `.gitignore` for you.)

## Command reference

All scripts accept `--repo PATH` (default `.`) and print a single JSON document to stdout.

### `maintain_atlas.py`

| Mode | Writes? | Purpose |
| --- | --- | --- |
| `status` | No | Cheap drift report: changed files, commits behind, tasks, plans, warnings, next actions |
| `auto` | Yes | What a bare skill invocation runs: record changes → full update → post-update status |
| `update` | Yes | Refresh generated evidence, backfill structure, reconcile skill version, move finished plans |
| `reconcile` | Yes | Same repair path as `update`, forced even when no source changed (use after a skill upgrade) |
| `check` | No* | Verify at `--level structure`, `evidence`, or `semantic` (default) |
| `compact-log` | Yes | Archive old maintenance-log entries verbatim, keep the newest ~100 lines |
| `convert` | Yes | Convert a greenfield Atlas to existing-codebase mode once code exists |
| `migrate` | Yes | Upgrade an older `atlas.json` schema |

\* `check --log` appends the result to `maintenance-log.md`. Without `--log`, check mode never
touches the repository, so it is safe in CI and pre-commit hooks.

| Flag | Applies to | Meaning |
| --- | --- | --- |
| `--level structure\|evidence\|semantic` | `check` | Verification depth (default `semantic`) |
| `--changed-since REF` | `update` | Focus on paths changed since a Git ref |
| `--paths PATH` | `update` | Focus on specific changed paths (repeatable) |
| `--domain NAME` | `update` | `code`, `architecture`, `database`, `auth`, `deployment`, `operations`, `all` (repeatable) |
| `--force` | writing modes | Regenerate generated content even if hand-edited (never touches living documents) |
| `--backup` | writing modes | Save `.bak` copies of overwritten files |
| `--platform NAME` | writing modes, `check` | Force a platform file (for example `cfml`, `mssql`) (repeatable) |
| `--generation-mode auto\|existing\|greenfield` | all | Override mode inference |
| `--site-url URL` | `update`, `reconcile`, `convert` | Record or replace the site URL (omitted = keep existing) |
| `--max-files N` | all | Scan cap (default 20000) |
| `--allow-partial-scan` | scanning modes | Accept a truncated scan instead of failing |
| `--log` | `check` | Also append the result to the maintenance log |

Changed paths map to every domain whose keywords they contain (`auth`, `login`, `session`, …
→ `auth`; `sql`, `schema`, `migration`, … → `database`; `deploy`, `docker`, `config`, … →
`deployment`), and always to `code`.

### `bootstrap_atlas.py`

```bash
python3 <skill-dir>/scripts/bootstrap_atlas.py --repo . --mode existing|greenfield [options]
```

| Flag | Meaning |
| --- | --- |
| `--mode existing\|greenfield` | Atlas type (default `existing`) |
| `--site-url URL` | Public-facing site URL, recorded in the playbook (empty string if none) |
| `--cfc-index-threshold N` | Component count at which the CFML inventory moves to `cfc-index.md` (default 25) |
| `--platform NAME` | Force a platform file (repeatable) |
| `--force`, `--backup` | Overwrite existing Atlas files (living documents are still never overwritten) |
| `--max-files N`, `--allow-partial-scan` | Scan limits |

### `audit_plans.py`

```bash
python3 <skill-dir>/scripts/audit_plans.py --repo . --mode check|apply [--archive-completed]
```

| Flag | Meaning |
| --- | --- |
| `--mode check` | Report plan/task mismatches without changing anything |
| `--mode apply` | Move plan files to match task checkboxes (both directions) and fix links |
| `--archive-completed` | With `apply`: move `## ` phases whose tasks are all checked to `tasks-archive.md` |

### Lower-level helpers

| Script | Purpose |
| --- | --- |
| `scan_repo.py --repo . [--output FILE]` | Run the repository scan alone and print or save its JSON |
| `detect_stack.py --repo .` | Print path-based stack detection |
| `write_templates.py` | Template rendering engine used by the other scripts |

### Exit codes

`0` means success: `passed`, or for `status` and `auto`, also `attention`. `1` means a failure the
caller must report (`failed`). Status and auto exit 0 on `attention` because drift is information to
act on, not an error.

## JSON output

Every command returns an envelope with at least `status`, `mode`, and `diagnostics`. Example
`--mode status` output (values illustrative):

```json
{
  "status": "attention",
  "mode": "status",
  "generation_mode": "existing",
  "lifecycle_state": "verified @ 990709e",
  "atlas_commit": "990709ea6922101f7bfe36a8881d39291265cafb",
  "head_commit": "8a8575e…",
  "commits_since_atlas": 11,
  "changed_app_files": 81,
  "changed_app_files_sample": ["api/htdocs/Application.cfc", "…"],
  "skill_version": {"atlas": "1.3.0", "installed": "1.5.0"},
  "status_md_last_updated": "2026-10-01",
  "tasks": {"open": 10, "blocked": 0, "done": 3},
  "plans_in_flight": 0,
  "warnings": [
    {"code": "LOG_OVERSIZE", "paths": ["project-atlas/maintenance-log.md"],
     "message": "Maintenance log is 842 lines (limit 150).",
     "suggested_repair": "Run `maintain_atlas.py --mode compact-log`, then summarize …"}
  ],
  "next_actions": [
    "Run `maintain_atlas.py --repo . --mode update --changed-since 990709e`, then update the Atlas files the playbook maps those changes to.",
    "Run `maintain_atlas.py --repo . --mode reconcile` to bring the Atlas to the installed skill version."
  ],
  "diagnostics": []
}
```

Note `lifecycle_state`: a recorded state is reported **with the commit it was recorded at**. A
"verified" Atlas that is 11 commits behind no longer looks trustworthy, because it isn't.

Every diagnostic and warning has the same shape: `code`, `paths`, `message`, `suggested_repair`.

## Verification and lifecycle

| Level | Checks |
| --- | --- |
| `structure` | Required files and directories, root sentinels, manifest validity, forbidden or alias paths, unresolved `{{slots}}`, platform files |
| `evidence` | `structure` plus source paths exist, repository fingerprint matches, scan complete, CFML coverage |
| `semantic` | `evidence` plus every semantic contract criterion completed or explained |

| Lifecycle state | Meaning |
| --- | --- |
| `scaffolded` | Structure exists; no manifest-backed evidence yet |
| `evidence-generated` | Evidence written; structure-level checks have run |
| `enrichment-required` | Semantic contracts still `pending` or invalid |
| `verified` | Semantic verification passed |
| `stale` | Source changed, or evidence points at missing paths, since the last update |

Treat an Atlas as complete only when `check --level semantic` returns `verified`.

## Semantic contracts

`project-overview.md` and `architecture.md` (or, in greenfield mode, `plan/product-brief.md` and
`plan/architecture-plan.md`) each carry one JSON marker:

```markdown
<!-- project-atlas:contract {"purpose":{"status":"complete","evidence":["README.md","Application.cfc"],"note":"README and Application.cfc confirm a multi-tenant billing app for small firms."},"users":{"status":"unknown","evidence":[],"note":"Role model unconfirmed; affects every permission check."},"workflows":{"status":"pending","evidence":[],"note":""}} -->
```

| Status | Requirement |
| --- | --- |
| `complete` | A note of 20+ characters, at least one existing repository-relative evidence path, and substantive hand-written prose in the document |
| `unknown` | A note explaining why the gap matters |
| `pending` | Nothing; but the Atlas stays `enrichment-required` |

Generated sections never satisfy a contract on their own. See
[`references/file-contracts.md`](references/file-contracts.md) for what each document must answer.

## Plans, tasks, and logs

### Plan tracking

Implementation plans live in `project-atlas/plans/in-flight/YYYY-MM-DD-slug.md`. Each one has a
task line in `tasks.md` that links to it:

```markdown
- [ ] Build the invoice export (plan: [invoice-export](plans/in-flight/2026-10-02-invoice-export.md))
```

When the task is checked, `update`, `auto`, or `audit_plans.py --mode apply` moves the plan to
`plans/completed/` and rewrites the link. Rules:

- Any task line with **exactly one** Markdown link into `plans/` is tracked, wherever the link sits
  in the line. Plain `[text](plans/…)` links work as well as `(plan: …)`.
- Any mention of a plan filename in `tasks.md` or `tasks-archive.md`, including a backticked path,
  counts as a reference, so the plan is not reported as orphaned.
- The automatic pass inside `update` only moves plans **forward**. An unchecked task whose plan sits
  in `completed/` is reported (`PLAN_MOVED_TO_IN_FLIGHT`), never moved back automatically.
- Orphaned plans, broken links, and duplicate filenames are always reported, never guessed at.

### Task list hygiene

`tasks.md` is the single task list. Duplicates such as `todo.md`, `task-list.md`, and `todo-list.md`
fail verification (`INVALID_ALIAS`) until they are folded in. When `tasks.md` passes 150 lines and
has fully completed phases, a `TASKS_OVERSIZE` warning suggests
`audit_plans.py --mode apply --archive-completed`. That moves those phases verbatim to
`tasks-archive.md`.

### Maintenance log

`maintenance-log.md` is a compact index, not a changelog: one entry per session, five lines at most
(date, summary, links). Implementation narration belongs in the plan or decision file. Entries are
appended, never rewritten, except by compaction:

```bash
python3 <skill-dir>/scripts/maintain_atlas.py --repo . --mode compact-log
```

Compaction orders entries by the date in each `## YYYY-MM-DD` heading, not by file position,
because real logs mix prepended and appended entries. It keeps the newest entries (about 100 lines,
always at least one), moves the rest verbatim to `maintenance-log-archive.md`, and adds an
`## Earlier history` entry pointing there for the agent to summarize. Running it again is safe.

### SQL execution ledger

All `.sql` files live in `project-atlas/sql/`. Its `README.md` keeps a ledger so the next agent knows
what has actually run:

```markdown
| File | Purpose | Dev | Stage | Live |
| --- | --- | --- | --- | --- |
| 006_customer_mailing_address.sql | Mailing address columns | 2026-08-14 | | |
```

A blank cell means not yet run. Older Atlases get the ledger section appended automatically, and
existing content is never touched.

## Diagnostics and warnings reference

**Diagnostics** fail verification. **Warnings** never fail verification. They flag drift the next
agent should fix, and they appear in `status`, `auto`, `check`, and `update` output.

### Warnings (hygiene)

| Code | Trigger | Repair |
| --- | --- | --- |
| `STATUS_UNFILLED` | `status.md` still says `Last updated: never` | Fill it in |
| `STATUS_STALE` | Application code was committed after `status.md` last changed | Rewrite it |
| `LOG_OVERSIZE` | Maintenance log over 150 lines | `--mode compact-log` |
| `TASKS_OVERSIZE` | `tasks.md` over 150 lines with completed phases | `audit_plans.py --mode apply --archive-completed` |
| `ATLAS_STRAY_FILE` | Non-Markdown file at the Atlas root (`.sql`, `.csv`, …) | Move to `sql/`, `snapshots/`, or out of the Atlas |
| `PLAN_MOVED_TO_COMPLETED` / `PLAN_MOVED_TO_IN_FLIGHT` | Plan location disagrees with its task checkbox | `audit_plans.py --mode apply`, or confirm intent |
| `PLAN_LINK_STALE_PATH` | Task link path doesn't match the file's location | `audit_plans.py --mode apply` |
| `ORPHANED_PLAN` | Plan file not referenced from `tasks.md` | Add a task line or remove the plan |
| `BROKEN_PLAN_LINK` | Task links to a missing plan | Restore or repoint |
| `PLAN_DUPLICATE_FILENAME` | Same plan name in both folders | Rename or remove one |

### Diagnostics (failures)

| Code | Meaning |
| --- | --- |
| `STRUCTURE_MISSING` | Required files, directories, platform files, or root files are missing; run `update` |
| `MANAGED_SENTINEL_INVALID` | A managed block's start/end markers are missing, duplicated, or reversed |
| `MANIFEST_INVALID_JSON`, `MANIFEST_FIELD_MISSING`, `MANIFEST_FIELD_INVALID`, `MANIFEST_SCHEMA_UNSUPPORTED` | `atlas.json` is unreadable or malformed; repair or `--mode migrate` |
| `SKILL_VERSION_STALE` | Atlas was written by a different skill version; `--mode reconcile` |
| `FORBIDDEN_PATH` | Skill internals (`scripts/`, `templates/`, …) were copied into the repo |
| `INVALID_ALIAS` | A duplicate of a canonical document exists (`todo.md`, `auth.md`, `go-live-checklist.md`, …) |
| `UNRESOLVED_SCAFFOLD` | Template placeholders or `{{slots}}` remain |
| `UNEXPECTED_PLATFORM` | A platform file exists for a platform that wasn't detected or selected |
| `GENERATED_CONTENT_MODIFIED` | A generated block was hand-edited; move the prose out, or regenerate with `--force` |
| `GENERATED_OWNERSHIP_UNKNOWN` | A generated file exists with no recorded digest; review, then `--force` |
| `GENERATED_DRIFT` | Repository contents changed since the last update |
| `STALE_SOURCE` | Evidence points at paths that no longer exist |
| `CFC_INVENTORY_GAP` / `CFC_INVENTORY_DUPLICATED` | CFML inventory incomplete, or present in two places |
| `PARTIAL_SCAN` | Scan hit `--max-files` |
| `CONTRACT_INVALID`, `CONTRACT_CRITERION_INVALID`, `CONTRACT_EVIDENCE_INVALID`, `CONTRACT_UNKNOWN_INCOMPLETE`, `ENRICHMENT_REQUIRED` | Semantic contract problems; see [Semantic contracts](#semantic-contracts) |
| `SCAN_STALE_CONCURRENT_UPDATE` | The Atlas changed while a scan was running; retry |
| `INVALID_GIT_REF` | `--changed-since` named a ref Git doesn't know |

## Safety and ownership model

Project Atlas writes into your repository, so its write rules are strict:

- **Scope.** It writes only under `project-atlas/`, plus one sentinel-delimited section in root
  `AGENTS.md` and `CLAUDE.md`. Everything else in those two files is preserved. Skill internals are
  never copied into your repo, and `FORBIDDEN_PATH` catches it if they are.
- **Ownership by digest.** Generated blocks
  (`<!-- project-atlas:generated:NAME:start/end -->`) and generated files are recorded in
  `atlas.json` with a SHA-256 digest. If you edit one, maintenance stops syncing it and reports
  `GENERATED_CONTENT_MODIFIED` instead of overwriting your change. Only `--force` overrides that.
- **Hand-written prose wins.** Content outside generated blocks is never rewritten. Existing files
  are skipped on bootstrap unless they still contain known scaffold-placeholder text.
- **Living documents are write-once** (see [Living documents](#living-documents)).
- **Atomic and locked.** Writes go to a temp file, then `fsync` and rename. Concurrent runs
  serialize on `project-atlas/.update.lock`. A scan that races a concurrent update is rejected
  (`SCAN_STALE_CONCURRENT_UPDATE`).
- **Secrets stay out.**
  - Files matching `.env*`, `*.pem`, `*.key`, `*.p12`, and `*.pfx` are never read.
  - Values that look like passwords, tokens, keys, or connection strings are redacted from any
    evidence excerpt.
  - Atlas documents record secret names and locations, never values. The single exception is the
    opt-in database setup, which stores credentials only in the gitignored `project-atlas/local/`
    with `chmod 600`.
- **Ignore rules.** In Git repositories, discovery uses `git ls-files`, so `.gitignore` applies
  exactly. `.project-atlasignore` (at the repo root or in `project-atlas/`) adds Atlas-specific
  exclusions. Non-Git repositories use a filesystem walk with the same patterns.
- **Caching.** Parsed evidence is cached by content digest in `project-atlas/.cache/scan-v3.json`.
  Source excerpts are not cached.

## Optional setup: database, design reference, site URL

These run during the bootstrap interview, and each one is opt-in.

**Site URL.** Recorded in `agent-playbook.md` so agents can generate and run tests against it.
`--site-url` on `update`, `reconcile`, or `convert` replaces it; omitting the flag keeps the
existing value.

**Design reference.** Point the skill at a folder of mockups, style guides, tokens, or component
libraries, and it writes `design-rules.md`: palette, typography, spacing, component patterns, and
stated guidelines, each backed by an evidence path. With a site URL, it can also sample the live
site and add a `## Live site` section citing page URLs. Inferences go under "Open questions", never
in as facts.

**Database connection.** A gated, one-question-at-a-time flow
([`references/database-connection-setup.md`](references/database-connection-setup.md)):

1. Confirm the engine. Detection is treated as a hypothesis, and you confirm it.
2. Locate the native CLI: `sqlcmd`, `mysql`, `psql`, `mongosh`, `sqlplus`, `sqlite3`, or `redis-cli`.
3. Collect the connection fields one at a time.
4. Test with a trivial read. Passwords are passed through the client's environment variable where
   one exists, so they never appear in shell history.
5. On success, write `project-atlas/local/db/<profile>.env` (`chmod 600`) and an
   `agent-<tool>` wrapper (`chmod 700`), and add `project-atlas/local/` to `.gitignore`.

`database.md` records only the profile name and the command for invoking it. If you decline, the
skip is recorded in `database.md`.

## Platform detection and CFML support

Platform files under `project-atlas/platforms/` are created only for detected (or explicitly
selected) platforms:

| Platform | Detected from |
| --- | --- |
| `cfml` | `.cfm`/`.cfc` files, `Application.cfc`/`.cfm`, `box.json`, `server.json` |
| `php` | `.php`, `composer.json`, `artisan`, `wp-config.php` |
| `node-js` | `package.json`, lockfiles, Vite/Next/Nuxt/Webpack config |
| `python` | `pyproject.toml`, `requirements.txt`, `Pipfile`, `manage.py`, `wsgi.py`, … |
| `docker` | `Dockerfile`, compose files, `docker/` |
| `mysql`, `mssql`, `postgresql`, `mongodb`, `redis`, `oracle-db` | Whole-token path matches, plus engine names inside config and database code |
| `ci_cd` | GitHub Actions, GitLab CI, Jenkins, CircleCI, Azure Pipelines |
| `testing` | Jest, Playwright, Cypress, Vitest, Mocha |

Path matching uses whole path tokens, so `latest.txt` doesn't trigger a database. Full rules are in
[`references/platform-guidance.md`](references/platform-guidance.md), and the implementation is in
`scripts/detect_stack.py`.

**CFML repositories** additionally get:

- an inventory of every `.cfc`: inferred role, methods extracted from both `<cffunction>` tags and
  script `function` declarations, and extraction status;
- a `.cfm` page list;
- datasource names (names only);
- tag-versus-script syntax counts.

Inventories under 25 components live in `code-map.md`'s generated block. Larger ones live once in
`cfc-index.md`, linked from the map, and the threshold is configurable with `--cfc-index-threshold`.

## Upgrading the skill

`VERSION` is stamped into every Atlas as `skill_version`. After you upgrade the skill (`git pull` in
the skill directory):

- `--mode status` and `check` report `SKILL_VERSION_STALE` on older Atlases.
- The next `update`, `auto`, or explicit `reconcile` backfills newly required files, appends new
  sections such as the SQL ledger, and resyncs skill-authored managed sections in
  `agent-playbook.md`, `tasks.md`, and the root `AGENTS.md`/`CLAUDE.md`.
- Sections you have hand-edited stop syncing and are reported. Your prose is never overwritten
  without `--force`.

To upgrade many repositories, run `--mode reconcile` once in each.

## Using an Atlas without the skill

An Atlas is plain Markdown plus one JSON file, so any agent or human can use it:

- **Start:** read `project-atlas/status.md`, then `project-atlas/agent-playbook.md`.
- **Freshness:** compare `git_commit` in `project-atlas/atlas.json` with `git rev-parse HEAD`.
- **Close-out:** follow the checklist in the root `AGENTS.md` section by hand. It is "done" when
  `status.md` shows today's date and every step is accounted for.
- **Without Python:** use the files in `templates/` as the starting content and follow the same
  rules by hand.

## Repository layout

```
project-atlas/                     (this skill)
├── SKILL.md                       # agent instructions; the skill's entry point
├── VERSION                        # stamped into every Atlas as skill_version
├── README.md                      # this file
├── agents/claude-code.md          # harness notes
├── references/
│   ├── bootstrap-interview.md     # site URL, design, live-site scan, database questions
│   ├── database-connection-setup.md
│   ├── file-contracts.md          # what each Atlas document must answer
│   └── platform-guidance.md       # detection markers
├── scripts/
│   ├── bootstrap_atlas.py         # create an Atlas
│   ├── maintain_atlas.py          # status, auto, update, reconcile, check, compact-log, convert, migrate
│   ├── audit_plans.py             # plan/task reconciliation and phase archiving
│   ├── scan_repo.py               # discovery, fingerprints, evidence, CFML extraction, cache
│   ├── detect_stack.py            # path-based platform detection
│   ├── write_templates.py         # rendering, managed sections, root files
│   └── utils.py                   # constants, verification, warnings, atomic I/O, locking
├── templates/
│   ├── existing/                  # existing-codebase documents, platforms/, fragments/
│   └── greenfield/                # plan/, context/, fragments/, living documents
└── tests/test_project_atlas.py
```

Templates are the source of truth for generated content. Files under `templates/*/fragments/` are
synced into existing Atlases as digest-tracked managed sections. That is how guidance changes
reach repositories bootstrapped by older versions.

## Development

Run the tests:

```bash
python3 -m unittest tests/test_project_atlas.py
```

The suite builds throwaway repositories in temporary directories (some with real Git history). It
covers:

- bootstrap and update idempotence, and preservation of hand-written content;
- living-document protection;
- managed sections and sentinels;
- manifest migration, semantic contracts, and stale and concurrent-update detection;
- secret redaction, ignore rules, and the scan cache;
- CFML extraction;
- status, auto, and compact-log modes;
- plan reconciliation (including mid-line and plain links) and phase archiving;
- the SQL ledger backfill and greenfield conversion.

Conventions for contributors:

- **Bump `VERSION`** whenever you change required structure or skill-authored guidance (templates,
  fragments, root sections). That is what triggers `SKILL_VERSION_STALE` and the reconcile path in
  existing Atlases.
- **Changing what gets written:** edit the template in `templates/`, not a string in a script.
- **New required file:** add it to `EXISTING_REQUIRED_FILES` / `GREENFIELD_REQUIRED_FILES` in
  `scripts/utils.py`. Add it to `LIVING_DOCUMENT_FILES` too if its content will belong to the user
  after creation. `update` then backfills it into older Atlases.
- **Shared guidance:** text that must reach existing Atlases belongs in a fragment (managed
  section), not in a whole-file template, which is only written once.
- **Fragments:** the existing and greenfield fragments are intentionally near-identical. The
  comment above `SKILL_MANAGED_SECTIONS` in `write_templates.py` lists which parts may differ.
- **Keep it dependency-free:** standard library only.

## Troubleshooting

**`status` says `attention` right after I updated.** Read `warnings` and `next_actions`. Drift is
only one cause. An unfilled `status.md`, an oversized log, or a skill-version mismatch also produce
`attention`.

**`GENERATED_CONTENT_MODIFIED` on every update.** Someone edited inside a
`project-atlas:generated` block. Move that prose outside the block, then run `update --force` once
to re-establish ownership.

**`INVALID_ALIAS` for `todo.md`.** Fold its items into `tasks.md` (as tasks under a phase) and
delete it.

**`PARTIAL_SCAN`.** The repository has more than `--max-files` eligible files. Add vendored or
generated directories to `.project-atlasignore`, or raise `--max-files`.

**A plan keeps getting reported as `ORPHANED_PLAN`.** Mention its filename anywhere in `tasks.md`
(a task-line link is best) or remove the file.

**Lifecycle stuck at `enrichment-required`.** Complete or explain each criterion in the contract
markers. `check --level semantic` lists exactly which ones are left.

**The agent loads an old version of the skill.** Check for duplicate installs (local versus synced
or plugin copies) and keep one.

## Limitations

- POSIX only, because of `fcntl` locking. Use WSL on Windows.
- Interpretation is only as good as the agent writing it. The scripts verify structure, evidence,
  and contract completeness, not the truth of the prose.
- Domain routing for `--paths` and `--changed-since` uses keyword matching on paths.
- Without Git, drift detection relies on modification times, so a file restored with an old
  timestamp can be missed.
- Code-map evidence is path- and bucket-based for most stacks. Deep method extraction exists only
  for CFML today.
- `compact-log` moves entries verbatim. Summarizing the archived history is left to the agent.
