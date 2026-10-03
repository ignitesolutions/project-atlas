## Testing

Public-facing site URL: {{site_url}}

Use this URL to generate and run agent-executed tests once something is deployed (see
`context/testing.md` if present). If the URL changes, update it here.

## Plan Tracking Protocol

`project-atlas/plans/` (plural) tracks execution/implementation plans — separate from `plan/`
(singular), which holds the initial product and architecture planning documents.

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
