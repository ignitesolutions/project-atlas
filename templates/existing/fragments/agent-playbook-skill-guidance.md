## Session Protocol

**Start:** read `status.md`, then this playbook. Read other Atlas files only when the task touches
them (table below). With the skill installed, `python3 <skill-dir>/scripts/maintain_atlas.py --repo . --mode status`
reports drift since the Atlas was last updated; without it, compare `git_commit` in `atlas.json`
with `git rev-parse HEAD`.

**Close-out** (any session that changed code, schema, config, or plans):

1. Rewrite `status.md` in place (Now, Next, Blocked, Unverified, Pending environment actions; under 40 lines).
2. Update `tasks.md` checkboxes and plan locations (Plan Tracking Protocol below).
3. Update the files the Atlas Maintenance table names for the change.
4. Append one `maintenance-log.md` entry: date, one-line summary, links. Five lines at most;
   per-file narration and test detail belong in the plan or decision file.
5. With the skill installed, run `maintain_atlas.py --repo . --mode update`.

Close-out is done when `--mode status` reports `"status": "passed"`, or, without the skill, when
`status.md` shows today's date and every step above is accounted for.

## Read On Demand

| Task touches | Read first |
| --- | --- |
| Any code change | `code-map.md`, `architecture.md` |
| Login, sessions, roles, permissions | `auth-and-access.md`, `known-risks.md` |
| Queries, tables, migrations | `database.md`, `schema.md`, `sql/README.md` |
| New page or UI pattern | `design-rules.md` |
| Testing | `testing.md`, `operations.md` |
| Build, deploy, environments | `deployment.md`, `operations.md`, `launch-checklist.md` |
| Replacing an established pattern | `decisions/` |
| Product scope or user workflows | `project-overview.md`, `open-questions.md` |

Skip rows whose files do not exist.

## Testing

Public-facing site URL: {{site_url}}

Use this URL to generate and run agent-executed tests (see `testing.md` if present). If the URL
changes, update it here.

## Task Tracking Protocol

`tasks.md` is the canonical task list, grouped by phase. Write each task so another agent can pick
it up cold. Mark blocked work by appending `— BLOCKED: reason and what unblocks it` and leaving it
unchecked. Mark finished work `[x]`. Keep one task list: fold `todo.md`-style notes into `tasks.md`.

## Plan Tracking Protocol

When a planning skill produces an implementation plan for this repo, save it to
`project-atlas/plans/in-flight/<YYYY-MM-DD>-<slug>.md` and add a task line in `tasks.md` that links
to it:

    - [ ] Task description (plan: [<slug>](plans/in-flight/<YYYY-MM-DD>-<slug>.md))

When the plan's work is complete, check the task box. `maintain_atlas.py --mode update` then moves
the file to `plans/completed/` (or run `audit_plans.py --repo . --mode apply` directly) and reports
anything ambiguous (orphaned plans, broken links) for you to resolve by hand. Without the skill,
move the file and fix the link yourself.

## Launch Checklist Protocol

Add a `launch-checklist.md` item as soon as work introduces anything that differs between dev,
stage, and live: env vars, config values, keys or certificates (names and locations only), folders,
permissions, scheduled tasks, SQL to run, or third-party setup (sandbox-to-live switches, webhook
URLs). If unsure whether something differs, add it phrased as a question.

## Atlas Maintenance

| Change type | Files to update |
| --- | --- |
| Any session that changed something | `status.md` |
| New feature or route | `code-map.md`, `feature-index.md` (if present) |
| Auth, sessions, permissions | `auth-and-access.md` |
| Schema or query patterns | `database.md`, `schema.md` |
| New or changed `.sql` file | `sql/README.md` execution ledger |
| New page, component, or UI convention | `design-rules.md` (if present) |
| New dependency or runtime change | `dependency-map.md` (see `stack.md`, which links to it) |
| Build, deploy, or hosting change | `deployment.md` |
| Fragile or security-sensitive code | `known-risks.md` |
| Env var, key, config, folder, SQL, or third-party setup that differs per environment | `launch-checklist.md` |
| Every meaningful Atlas run | `maintenance-log.md` (append; five lines at most) |
| Task added, completed, or blocked | `tasks.md` |
| Plan created, completed, or moved | `tasks.md`, `plans/in-flight/`, `plans/completed/` |

Formatting-only, comment-only, temporary debug, and reverted changes need no Atlas update.
