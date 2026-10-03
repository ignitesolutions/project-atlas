# Plans — In Flight

This is an intentional scaffold folder. Active execution/implementation plans live here, named
`YYYY-MM-DD-<slug>.md`. This is separate from `plan/` (singular), which holds the initial product
and architecture planning documents.

Every plan here must have a matching task line in `project-atlas/tasks.md` that links back to it —
see the Plan Tracking Protocol in `agent-playbook.md`. When a plan's work is complete, check the
task box and move the file to `../completed/` (or run `scripts/audit_plans.py --mode apply` to do
both automatically).
