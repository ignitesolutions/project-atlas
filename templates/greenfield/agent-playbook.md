# Agent Playbook

Resolve the criterion contracts in `plan/product-brief.md` and `plan/architecture-plan.md` with
the user. Use `complete` with supporting evidence, `unknown` with an impact note, or `pending`.
Do not invent product or implementation facts. Convert to existing-codebase mode after source
implementation exists.

This file is the operating contract for every agent working in this repository. Read it before writing any code or making any changes.

## Orientation

1. Read `project-atlas/status.md` for where work stands and what is next.
2. Read `project-atlas/README.md` for project overview and context links.
3. Read `project-atlas/plan/architecture-plan.md` and `project-atlas/plan/implementation-roadmap.md` for the intended design.
4. Read `project-atlas/context/conventions.md` before writing any code.
5. Check `project-atlas/context/known-risks.md` for fragile or sensitive areas.
6. Check `project-atlas/plan/open-questions.md` for unresolved decisions that may affect your work.

## Task Tracking Protocol

`project-atlas/tasks.md` is the canonical task list for this project. Tasks are grouped by phase so work can be picked up in order without re-deriving the roadmap.

**Before starting any work:**

1. Open `project-atlas/tasks.md`.
2. Find the relevant phase, or add a new phase section if none fits.
3. Add your task as an unchecked item with enough context for another agent to pick it up cold.

**While working:**

- Update the task description if scope or approach changes.
- If blocked, append `— BLOCKED: reason and what is needed to unblock` to the task line. Leave it unchecked.

**When done:**

- Mark the item `[x]`.
- Update the description paragraph at the top of `tasks.md` if the overall project state has shifted.
- When an entire phase is complete, you may archive it to `project-atlas/handoffs/` and note the archive date in the description.

**Format:**

```markdown
## Phase N: Phase Name

- [ ] Task description with enough context to pick up cold.
- [ ] Task description — BLOCKED: waiting on X before this can proceed.
- [x] Completed task description.
```

## Launch Checklist Protocol

`project-atlas/launch-checklist.md` tracks everything that must happen when this project moves to the LIVE environment. It is written during development, not at launch time.

Add an item **immediately** when work introduces anything that differs between dev, stage, and live:

- Environment variables, config values, application settings, feature flags, or debug settings
- API keys, credentials, certificates, or OAuth client IDs (names and locations only — never values)
- Folders, file permissions, scheduled tasks, or web server configuration the app requires
- SQL scripts or migrations that must be run against the live database
- Third-party service setup: sandbox-to-live switches, live keys, webhook/callback URLs, account configuration (Stripe, Authorize.net, mail providers, external APIs, etc.)

Each item states what must be done, which environment(s) it affects, where it is configured, and who does it. If you are unsure whether something differs per environment, add it as an item phrased as a question rather than omitting it.

## Atlas Maintenance

After completing any durable change, update the relevant Atlas files:

| Change type | Files to update |
| --- | --- |
| Any session that changed something | `status.md` |
| New feature or route | `context/feature-index.md`, `context/code-map.md` |
| Auth, sessions, permissions | `context/auth-and-access.md` |
| Schema or query patterns | `context/database.md` |
| New dependency or runtime change | `context/stack.md`, `context/dependency-map.md` |
| Build, deploy, or hosting change | `context/deployment.md` |
| Fragile or security-sensitive code | `context/known-risks.md` |
| New or changed `.sql` file | `sql/README.md` execution ledger |
| Env var, key, config, folder, SQL, or third-party setup that differs per environment | `launch-checklist.md` |
| Plan change or resolved question | `plan/open-questions.md`, `plan/implementation-roadmap.md` |
| Every meaningful Atlas run | `context/maintenance-log.md` (append; five lines at most) |
| Task added, completed, or blocked | `tasks.md` |
| Plan created, completed, or moved | `tasks.md`, `plans/in-flight/`, `plans/completed/` |

Do not update Atlas for formatting-only, comment-only, temporary debug, or reverted changes.

## Conventions

Follow `project-atlas/context/conventions.md` exactly. Do not introduce patterns not already present in the plan without raising the question in `plan/open-questions.md` first.

## Decisions

Architectural decisions are recorded in `project-atlas/decisions/`. Check that directory before reversing or replacing a planned pattern. Add a new decision record when you make a choice that diverges from the plan.
