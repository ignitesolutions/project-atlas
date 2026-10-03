## Session Protocol

**Start:** read `status.md`, then this playbook. Read plan and context files only when the task
touches them. With the skill installed, `python3 <skill-dir>/scripts/maintain_atlas.py --repo . --mode status`
reports drift since the Atlas was last updated.

**Close-out** (any session that changed code, schema, config, or plans):

1. Rewrite `status.md` in place (Now, Next, Blocked, Unverified, Pending environment actions; under 40 lines).
2. Update `tasks.md` checkboxes and plan locations (Plan Tracking Protocol below).
3. Update the files the Atlas Maintenance table names for the change; record new `.sql` files in
   the `sql/README.md` execution ledger.
4. Append one `context/maintenance-log.md` entry: date, one-line summary, links. Five lines at most.
5. With the skill installed, run `maintain_atlas.py --repo . --mode update`.

Close-out is done when `--mode status` reports `"status": "passed"`, or, without the skill, when
`status.md` shows today's date and every step above is accounted for.

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

When the plan's work is complete, check the task box. `maintain_atlas.py --mode update` then moves
the file to `plans/completed/` (or run `audit_plans.py --repo . --mode apply` directly) and reports
anything ambiguous (orphaned plans, broken links) for you to resolve by hand. Without the skill,
move the file and fix the link yourself.
