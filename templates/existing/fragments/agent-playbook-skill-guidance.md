## Testing

Public-facing site URL: {{site_url}}

Use this URL to generate and run agent-executed tests (see `testing.md` if present). If the URL
changes, update it here.

## Plan Tracking Protocol

When a planning skill produces an implementation plan for this repo, save it to
`project-atlas/plans/in-flight/<YYYY-MM-DD>-<slug>.md` and add a task line in `tasks.md` that links
to it:

    - [ ] Task description (plan: [<slug>](plans/in-flight/<YYYY-MM-DD>-<slug>.md))

When the plan's work is complete, check the task box and move the file to
`project-atlas/plans/completed/`. Or just run:

    python3 <skill-dir>/scripts/audit_plans.py --repo . --mode apply

which reconciles file location and task checkbox state automatically wherever it can, and reports
anything ambiguous (orphaned plans, broken links) for you to resolve by hand. A plan created,
completed, or moved is a durable change — keep `tasks.md` and `project-atlas/plans/` in sync with it.

## Atlas Maintenance

| Change type | Files to update |
| --- | --- |
| New feature or route | `code-map.md`, `feature-index.md` (if present) |
| Auth, sessions, permissions | `auth-and-access.md` |
| Schema or query patterns | `database.md`, `schema.md` |
| New dependency or runtime change | `dependency-map.md` (see `stack.md`, which links to it) |
| Build, deploy, or hosting change | `deployment.md` |
| Fragile or security-sensitive code | `known-risks.md` |
| Env var, key, config, folder, SQL, or third-party setup that differs per environment | `launch-checklist.md` |
| Every meaningful Atlas run | `maintenance-log.md` (keep entries compact — see its header) |
| Task added, completed, or blocked | `tasks.md` |
| Plan created, completed, or moved | `tasks.md`, `plans/in-flight/`, `plans/completed/` |

Do not update the Atlas for formatting-only, comment-only, temporary debug, or reverted changes.
