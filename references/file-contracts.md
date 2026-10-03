# Atlas Content Contracts

Semantic verification requires human interpretation, not generated path lists. Each document has
one `project-atlas:contract` JSON marker. Every criterion uses `complete`, `unknown`, or `pending`.
Complete criteria require a substantive criterion note, hand-authored document prose, and at least one
existing repository-relative evidence path. Unknown criteria require an impact note; pending criteria
keep the Atlas unverified.

## Core documents

- `status.md`: the resume path — Now, Next (top 3, recommended first), Blocked, Unverified, Pending environment actions, and the last session. Rewritten in place each session, under 40 lines; no semantic contract, but `--mode status` flags it unfilled or stale.
- `project-overview.md`: purpose, primary users/roles, and three to five principal workflows.
- `architecture.md`: end-to-end request flow, layers, module boundaries, and external boundaries.
- `code-map.md`: concise navigation to entry points, routes/controllers, services, and data access. Keep complete generated inventories in one managed location.
- `operations.md`: test path, environments, deployment, configuration names/locations, monitoring, rollback, and recovery—or explicit unknowns.
- `open-questions.md`: every unconfirmed inference or unresolved decision, phrased as a question with impact.
- `sql/README.md`: an execution ledger row per `.sql` file, with the date it ran in each environment (blank = not yet run).

## Conditional documents

- `auth-and-access.md`: login flow, session behavior, roles/permissions, and gating paths.
- `database.md`: datasource names only, query locations/conventions, schema source, and migration process.
- `deployment.md`: build/deploy triggers, hosting, environment differences, and rollback.
- `testing.md`: automated or browser-driven execution path, test locations, and seed-data needs.
- `known-risks.md`: fragile, security-sensitive, or data-sensitive areas with paths and reasons.
- `launch-checklist.md`: actionable live-environment differences, owner, location, and target environment; never secret values (passwords, keys, tokens, connection strings).

Machine-generated sections supply evidence and freshness. They never satisfy semantic contracts
by themselves.

When the same entity appears in multiple documents, the contract's evidence path should point at
its single primary document; other documents may link to it but should not restate its detail.
